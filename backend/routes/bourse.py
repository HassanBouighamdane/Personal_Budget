# -*- coding: utf-8 -*-
"""
Module Bourse — achats, ventes, commissions, TPCVM, positions, gains.
Mêmes conventions que routes/transactions.py et routes/rapports.py :
    - authentification déclarée une fois au niveau du router
    - connexion via le context manager db() de database.py
    - calculs en Decimal, conversion en float uniquement à la sortie
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from database import db
from securite import utilisateur_courant
from schemas import (
    ParametresBourse, TransactionBourseCreate, TransactionBourseOut,
    PrixMaj, PositionBourse, GainRealise, DashboardBourse,
)

router = APIRouter(prefix="/api/bourse", tags=["bourse"],
                    dependencies=[Depends(utilisateur_courant)])

Q2 = Decimal("0.01")


def _r(x) -> float:
    """Arrondi 2 décimales puis conversion en float pour la réponse JSON."""
    return float(Decimal(x).quantize(Q2, rounding=ROUND_HALF_UP))


def _calc_transaction(t: dict) -> dict:
    """Recalcule brut / commission / TVA / frais / net à partir d'une ligne DB (Decimal)."""
    qte, cours = Decimal(t["quantite"]), Decimal(t["cours_unitaire"])
    taux_comm, taux_tva = Decimal(t["taux_commission"]), Decimal(t["taux_tva"])
    autres = Decimal(t["autres_frais"])

    brut = qte * cours
    commission = brut * taux_comm
    tva = commission * taux_tva
    total_frais = commission + tva + autres
    net = brut + total_frais if t["type_operation"] == "Achat" else brut - total_frais

    return {
        **t,
        "montant_brut": _r(brut), "commission": _r(commission),
        "tva_commission": _r(tva), "total_frais": _r(total_frais),
        "montant_net": _r(net),
        "_net_decimal": net,  # gardé en interne pour les calculs de position/gains
    }


# ---------------------------------------------------------------- paramètres
@router.get("/parametres", response_model=ParametresBourse)
def obtenir_parametres():
    with db() as conn:
        row = conn.execute("SELECT taux_commission, taux_tva, taux_tpcvm FROM bourse_parametres LIMIT 1").fetchone()
    return row


@router.put("/parametres", response_model=ParametresBourse)
def maj_parametres(p: ParametresBourse):
    with db() as conn:
        conn.execute(
            """UPDATE bourse_parametres
               SET taux_commission = %s, taux_tva = %s, taux_tpcvm = %s""",
            (p.taux_commission, p.taux_tva, p.taux_tpcvm),
        )
        row = conn.execute("SELECT taux_commission, taux_tva, taux_tpcvm FROM bourse_parametres LIMIT 1").fetchone()
    return row


# ---------------------------------------------------------------- transactions
@router.get("/transactions", response_model=List[TransactionBourseOut])
def lister_transactions():
    with db() as conn:
        rows = conn.execute(
            """SELECT id, date_operation, titre, isin, type_operation, quantite,
                      cours_unitaire, taux_commission, taux_tva, autres_frais
               FROM bourse_transactions ORDER BY date_operation DESC, id DESC"""
        ).fetchall()
    return [_calc_transaction(dict(r)) for r in rows]


@router.post("/transactions", response_model=TransactionBourseOut, status_code=201)
def creer_transaction(t: TransactionBourseCreate):
    with db() as conn:
        params = conn.execute("SELECT taux_commission, taux_tva FROM bourse_parametres LIMIT 1").fetchone()
        taux_commission = t.taux_commission if t.taux_commission is not None else float(params["taux_commission"])
        taux_tva = t.taux_tva if t.taux_tva is not None else float(params["taux_tva"])

        row = conn.execute(
            """INSERT INTO bourse_transactions
                   (date_operation, titre, isin, type_operation, quantite,
                    cours_unitaire, taux_commission, taux_tva, autres_frais)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id, date_operation, titre, isin, type_operation, quantite,
                         cours_unitaire, taux_commission, taux_tva, autres_frais""",
            (t.date_operation, t.titre.strip().upper(), t.isin, t.type_operation,
             t.quantite, t.cours_unitaire, taux_commission, taux_tva, t.autres_frais),
        ).fetchone()
    return _calc_transaction(dict(row))


@router.delete("/transactions/{transaction_id}", status_code=204)
def supprimer_transaction(transaction_id: int):
    with db() as conn:
        res = conn.execute("DELETE FROM bourse_transactions WHERE id = %s", (transaction_id,))
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transaction introuvable")


# ---------------------------------------------------------------- prix courants
@router.put("/prix/{titre}")
def maj_prix(titre: str, p: PrixMaj):
    with db() as conn:
        conn.execute(
            """INSERT INTO bourse_prix (titre, cours_actuel, maj_le)
               VALUES (%s, %s, now())
               ON CONFLICT (titre) DO UPDATE SET cours_actuel = EXCLUDED.cours_actuel, maj_le = now()""",
            (titre.strip().upper(), p.cours_actuel),
        )
    return {"titre": titre.strip().upper(), "cours_actuel": p.cours_actuel}


# ---------------------------------------------------------------- calcul positions / gains (logique commune)
def _positions_et_gains():
    """Coût moyen pondéré par titre + gain/perte + TPCVM pour chaque vente."""
    with db() as conn:
        txs = [dict(r) for r in conn.execute(
            """SELECT id, date_operation, titre, isin, type_operation, quantite,
                      cours_unitaire, taux_commission, taux_tva, autres_frais
               FROM bourse_transactions ORDER BY date_operation ASC, id ASC"""
        ).fetchall()]
        prix = {r["titre"]: Decimal(r["cours_actuel"]) for r in conn.execute("SELECT titre, cours_actuel FROM bourse_prix").fetchall()}
        tpcvm_rate = Decimal(conn.execute("SELECT taux_tpcvm FROM bourse_parametres LIMIT 1").fetchone()["taux_tpcvm"])

    calc = [_calc_transaction(t) for t in txs]

    par_titre = {}
    for t in calc:
        p = par_titre.setdefault(t["titre"], {"titre": t["titre"], "qte_achat": Decimal(0), "qte_vente": Decimal(0), "cout_achat": Decimal(0)})
        if t["type_operation"] == "Achat":
            p["qte_achat"] += Decimal(t["quantite"])
            p["cout_achat"] += t["_net_decimal"]
        else:
            p["qte_vente"] += Decimal(t["quantite"])

    positions = []
    pru_par_titre = {}
    for p in par_titre.values():
        qte_detenue = p["qte_achat"] - p["qte_vente"]
        pru = p["cout_achat"] / p["qte_achat"] if p["qte_achat"] > 0 else Decimal(0)
        pru_par_titre[p["titre"]] = pru  # non arrondi, utilisé pour le calcul des gains
        cours = prix.get(p["titre"], Decimal(0))
        valeur_comptable = pru * qte_detenue
        valeur_marche = cours * qte_detenue
        plus_value = valeur_marche - valeur_comptable
        perf = (plus_value / valeur_comptable) if valeur_comptable != 0 else Decimal(0)
        positions.append(PositionBourse(
            titre=p["titre"], quantite_achetee=_r(p["qte_achat"]), quantite_vendue=_r(p["qte_vente"]),
            quantite_detenue=_r(qte_detenue), pru=_r(pru), cours_actuel=_r(cours),
            valeur_comptable=_r(valeur_comptable), valeur_marche=_r(valeur_marche),
            plus_value_latente=_r(plus_value), performance_latente=_r(perf),
        ))

    gains = []
    for t in calc:
        if t["type_operation"] != "Vente":
            continue
        pru = pru_par_titre.get(t["titre"], Decimal(0))
        qte = Decimal(t["quantite"])
        net = t["_net_decimal"]
        gain_brut = net - (pru * qte)
        tpcvm = gain_brut * tpcvm_rate if gain_brut > 0 else Decimal(0)
        gain_net = gain_brut - tpcvm
        gains.append(GainRealise(
            id=t["id"], date_operation=t["date_operation"], titre=t["titre"], quantite=_r(qte),
            cours_vente=_r(Decimal(t["cours_unitaire"])), pru=_r(pru), montant_net=_r(net),
            gain_brut=_r(gain_brut), taux_tpcvm=_r(tpcvm_rate), tpcvm=_r(tpcvm), gain_net=_r(gain_net),
        ))

    return positions, gains, calc


@router.get("/positions", response_model=List[PositionBourse])
def obtenir_positions():
    positions, _, _ = _positions_et_gains()
    return positions


@router.get("/gains", response_model=List[GainRealise])
def obtenir_gains():
    _, gains, _ = _positions_et_gains()
    return sorted(gains, key=lambda g: g.date_operation, reverse=True)


@router.get("/dashboard", response_model=DashboardBourse)
def obtenir_dashboard():
    positions, gains, calc = _positions_et_gains()

    cout_acquisition = sum(Decimal(str(p.valeur_comptable)) for p in positions)
    valeur_marche = sum(Decimal(str(p.valeur_marche)) for p in positions)
    plus_value_latente = valeur_marche - cout_acquisition
    perf = (plus_value_latente / cout_acquisition) if cout_acquisition != 0 else Decimal(0)

    gains_bruts = sum(Decimal(str(g.gain_brut)) for g in gains)
    tpcvm_total = sum(Decimal(str(g.tpcvm)) for g in gains)
    gains_nets = sum(Decimal(str(g.gain_net)) for g in gains)

    commissions = sum(Decimal(str(t["commission"])) for t in calc)
    tva = sum(Decimal(str(t["tva_commission"])) for t in calc)
    frais = sum(Decimal(str(t["total_frais"])) for t in calc)

    resultat_global = plus_value_latente + gains_nets - frais

    return DashboardBourse(
        cout_acquisition=_r(cout_acquisition), valeur_marche=_r(valeur_marche),
        plus_value_latente=_r(plus_value_latente), performance_latente=_r(perf),
        gains_bruts_realises=_r(gains_bruts), tpcvm_total=_r(tpcvm_total),
        gains_nets_realises=_r(gains_nets), commissions_totales=_r(commissions),
        tva_totale=_r(tva), frais_totaux=_r(frais), resultat_net_global=_r(resultat_global),
    )