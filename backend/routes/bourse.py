# -*- coding: utf-8 -*-
"""
Module Bourse — achats, ventes, dividendes, frais de compte, positions, gains.

Simplifié : aucun frais n'est calculé automatiquement sur les transactions ni
sur les dividendes. L'utilisateur saisit directement le prix net (achat/vente)
et le montant net des dividendes déjà reçus ; les frais de courtage éventuels
se saisissent manuellement, soit ponctuellement sur une transaction (« Autres
frais »), soit via le journal séparé des frais de compte (abonnement courtier,
tenue de compte...).

Restent calculés automatiquement (ce sont des calculs indépendants des frais
de transaction, qu'on ne peut pas simplement « lire » sur un relevé) :
    - le PRU (coût moyen pondéré) et les plus/moins-values latentes ;
    - le gain/perte réalisé à la vente et la TPCVM (taxe sur les profits de
      cession de valeurs mobilières) ;
    - les droits de garde (estimation indicative sur l'encours actuel).

Le dashboard accepte des filtres optionnels `mois` (AAAA-MM) ou `annee` pour
les flux réalisés sur la période (gains, dividendes, frais). La valeur du
portefeuille (coût d'acquisition, valeur de marché, plus-value latente) reste
toujours celle d'aujourd'hui : l'application ne conserve pas d'historique de
cours, donc une valorisation « à une date passée » n'est pas calculable.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from database import db
from securite import utilisateur_courant
from schemas import (
    ParametresBourse, TransactionBourseCreate, TransactionBourseOut,
    PrixMaj, PositionBourse, GainRealise, DashboardBourse, DroitsGarde, TitreBourse,
    DividendeCreate, DividendeOut, FraisBourseCreate, FraisBourseOut,
)

router = APIRouter(prefix="/api/bourse", tags=["bourse"],
                    dependencies=[Depends(utilisateur_courant)])

Q2 = Decimal("0.01")


def _r(x) -> float:
    """Arrondi 2 décimales puis conversion en float pour la réponse JSON."""
    return float(Decimal(x).quantize(Q2, rounding=ROUND_HALF_UP))


def _d(v) -> Decimal:
    """Decimal sûr, que la valeur vienne de psycopg (Decimal/None) ou d'un float Python."""
    return Decimal(str(v)) if v is not None else Decimal(0)


def _parametres_dict(conn) -> dict:
    return dict(conn.execute("SELECT * FROM bourse_parametres LIMIT 1").fetchone())


# ------------------------------------------------------------------ filtre mois/année (commun)
def _valider_periode(mois: Optional[str], annee: Optional[int]):
    if mois:
        try:
            datetime.strptime(mois, "%Y-%m")
        except ValueError:
            raise HTTPException(400, "Format de mois attendu : AAAA-MM")


def _dans_periode(d, mois: Optional[str], annee: Optional[int]) -> bool:
    if not mois and not annee:
        return True
    s = d.isoformat()
    if mois:
        return s[:7] == mois
    return s[:4] == str(annee)


def _calc_transaction(t: dict) -> dict:
    """Prix déjà net (aucun frais calculé automatiquement) : montant_net = brut ± autres_frais."""
    qte, cours = _d(t["quantite"]), _d(t["cours_unitaire"])
    autres = _d(t["autres_frais"])
    brut = qte * cours
    net = brut + autres if t["type_operation"] == "Achat" else brut - autres
    return {
        **t, "montant_brut": _r(brut), "autres_frais": _r(autres),
        "total_frais": _r(autres), "montant_net": _r(net),
        "_net_decimal": net,   # gardé en interne pour les calculs de position/gains
    }


# ---------------------------------------------------------------- paramètres
@router.get("/parametres", response_model=ParametresBourse)
def obtenir_parametres():
    with db() as conn:
        return _parametres_dict(conn)


@router.put("/parametres", response_model=ParametresBourse)
def maj_parametres(p: ParametresBourse):
    with db() as conn:
        conn.execute(
            """UPDATE bourse_parametres SET
                   taux_droit_garde_annuel = %s, droit_garde_min_trimestriel = %s,
                   taux_tpcvm = %s""",
            (p.taux_droit_garde_annuel, p.droit_garde_min_trimestriel, p.taux_tpcvm),
        )
        return _parametres_dict(conn)


@router.get("/titres", response_model=List[TitreBourse])
def lister_titres():
    with db() as conn:
        rows = conn.execute(
            "SELECT code, nom, secteur FROM bourse_titres WHERE actif = 1 ORDER BY nom"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- transactions
TX_COLONNES = "id, date_operation, titre, isin, type_instrument, type_operation, quantite, cours_unitaire, autres_frais"


@router.get("/transactions", response_model=List[TransactionBourseOut])
def lister_transactions(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    with db() as conn:
        rows = conn.execute(
            f"SELECT {TX_COLONNES} FROM bourse_transactions ORDER BY date_operation DESC, id DESC"
        ).fetchall()
    calc = [_calc_transaction(dict(r)) for r in rows]
    return [t for t in calc if _dans_periode(t["date_operation"], mois, annee)]


@router.post("/transactions", response_model=TransactionBourseOut, status_code=201)
def creer_transaction(t: TransactionBourseCreate):
    with db() as conn:
        row = conn.execute(
            f"""INSERT INTO bourse_transactions
                    (date_operation, titre, isin, type_instrument, type_operation, quantite, cours_unitaire, autres_frais)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING {TX_COLONNES}""",
            (t.date_operation, t.titre.strip().upper(), t.isin, t.type_instrument,
             t.type_operation, t.quantite, t.cours_unitaire, t.autres_frais),
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


# ---------------------------------------------------------------- dividendes
DIV_COLONNES = "id, date_operation, titre, montant"


def _dividendes() -> list:
    with db() as conn:
        rows = conn.execute(
            f"SELECT {DIV_COLONNES} FROM bourse_dividendes ORDER BY date_operation DESC, id DESC"
        ).fetchall()
    return [{**dict(r), "montant": _r(r["montant"])} for r in rows]


@router.get("/dividendes", response_model=List[DividendeOut])
def lister_dividendes(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    return [d for d in _dividendes() if _dans_periode(d["date_operation"], mois, annee)]


@router.post("/dividendes", response_model=DividendeOut, status_code=201)
def creer_dividende(d: DividendeCreate):
    with db() as conn:
        row = conn.execute(
            f"""INSERT INTO bourse_dividendes (date_operation, titre, montant)
                VALUES (%s,%s,%s)
                RETURNING {DIV_COLONNES}""",
            (d.date_operation, d.titre.strip().upper(), d.montant),
        ).fetchone()
    return {**dict(row), "montant": _r(row["montant"])}


@router.delete("/dividendes/{dividende_id}", status_code=204)
def supprimer_dividende(dividende_id: int):
    with db() as conn:
        res = conn.execute("DELETE FROM bourse_dividendes WHERE id = %s", (dividende_id,))
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Dividende introuvable")


# ---------------------------------------------------------------- frais de compte
FRAIS_COLONNES = "id, date_operation, libelle, montant"


def _frais_compte() -> list:
    with db() as conn:
        rows = conn.execute(
            f"SELECT {FRAIS_COLONNES} FROM bourse_frais ORDER BY date_operation DESC, id DESC"
        ).fetchall()
    return [{**dict(r), "montant": _r(r["montant"])} for r in rows]


@router.get("/frais", response_model=List[FraisBourseOut])
def lister_frais(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    return [f for f in _frais_compte() if _dans_periode(f["date_operation"], mois, annee)]


@router.post("/frais", response_model=FraisBourseOut, status_code=201)
def creer_frais(f: FraisBourseCreate):
    with db() as conn:
        row = conn.execute(
            f"""INSERT INTO bourse_frais (date_operation, libelle, montant)
                VALUES (%s,%s,%s)
                RETURNING {FRAIS_COLONNES}""",
            (f.date_operation, f.libelle.strip(), f.montant),
        ).fetchone()
    return {**dict(row), "montant": _r(row["montant"])}


@router.delete("/frais/{frais_id}", status_code=204)
def supprimer_frais(frais_id: int):
    with db() as conn:
        res = conn.execute("DELETE FROM bourse_frais WHERE id = %s", (frais_id,))
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Frais introuvable")


# ---------------------------------------------------------------- calcul positions / gains (logique commune)
def _positions_et_gains():
    """Coût moyen pondéré par titre (tous instruments confondus) + gain/perte et TPCVM par vente.
    Toujours calculé sur l'historique complet des transactions (le PRU actuel dépend de tout
    l'historique d'achat, quelle que soit la période affichée par ailleurs)."""
    with db() as conn:
        params = _parametres_dict(conn)
        txs = [dict(r) for r in conn.execute(
            f"SELECT {TX_COLONNES} FROM bourse_transactions ORDER BY date_operation ASC, id ASC"
        ).fetchall()]
        prix = {r["titre"]: _d(r["cours_actuel"]) for r in conn.execute("SELECT titre, cours_actuel FROM bourse_prix").fetchall()}
        tpcvm_rate = _d(params["taux_tpcvm"])

    calc = [_calc_transaction(t) for t in txs]

    par_titre = {}
    for t in calc:
        p = par_titre.setdefault(t["titre"], {"titre": t["titre"], "qte_achat": Decimal(0), "qte_vente": Decimal(0), "cout_achat": Decimal(0)})
        if t["type_operation"] == "Achat":
            p["qte_achat"] += _d(t["quantite"])
            p["cout_achat"] += t["_net_decimal"]
        else:
            p["qte_vente"] += _d(t["quantite"])

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
        qte = _d(t["quantite"])
        net = t["_net_decimal"]
        gain_brut = net - (pru * qte)
        tpcvm = gain_brut * tpcvm_rate if gain_brut > 0 else Decimal(0)
        gain_net = gain_brut - tpcvm
        gains.append(GainRealise(
            id=t["id"], date_operation=t["date_operation"], titre=t["titre"], type_instrument=t["type_instrument"],
            quantite=_r(qte), cours_vente=_r(_d(t["cours_unitaire"])), pru=_r(pru), montant_net=_r(net),
            gain_brut=_r(gain_brut), taux_tpcvm=_r(tpcvm_rate), tpcvm=_r(tpcvm), gain_net=_r(gain_net),
        ))

    return positions, gains, calc, params


@router.get("/positions", response_model=List[PositionBourse])
def obtenir_positions():
    positions, _, _, _ = _positions_et_gains()
    return positions


@router.get("/gains", response_model=List[GainRealise])
def obtenir_gains(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    _, gains, _, _ = _positions_et_gains()
    gains = [g for g in gains if _dans_periode(g.date_operation, mois, annee)]
    return sorted(gains, key=lambda g: g.date_operation, reverse=True)


# ---------------------------------------------------------------- droits de garde (frais périodiques)
def _calcul_droits_garde(positions, params) -> DroitsGarde:
    base = sum(_d(pos.valeur_marche) for pos in positions)
    taux = _d(params["taux_droit_garde_annuel"])
    minimum = _d(params["droit_garde_min_trimestriel"])
    estime = base * taux / 4
    du = estime if estime > minimum else minimum
    return DroitsGarde(base_calcul=_r(base), taux_annuel=_r(taux), montant_trimestriel_estime=_r(estime),
                        minimum_trimestriel=_r(minimum), montant_trimestriel_du=_r(du))


@router.get("/droits_garde", response_model=DroitsGarde)
def obtenir_droits_garde():
    positions, _, _, params = _positions_et_gains()
    return _calcul_droits_garde(positions, params)


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard", response_model=DashboardBourse)
def obtenir_dashboard(mois: Optional[str] = None, annee: Optional[int] = None):
    """`mois` (AAAA-MM) ou `annee` filtrent les flux réalisés (gains, dividendes, frais) sur
    la période choisie. Sans filtre : tout l'historique. La valorisation du portefeuille
    (coût d'acquisition, valeur de marché, plus-value latente) reste toujours celle
    d'aujourd'hui, indépendamment du filtre — il n'y a pas d'historique de cours enregistré."""
    _valider_periode(mois, annee)
    positions, gains, calc, params = _positions_et_gains()

    cout_acquisition = sum(_d(p.valeur_comptable) for p in positions)
    valeur_marche = sum(_d(p.valeur_marche) for p in positions)
    plus_value_latente = valeur_marche - cout_acquisition
    perf = (plus_value_latente / cout_acquisition) if cout_acquisition != 0 else Decimal(0)

    gains_periode = [g for g in gains if _dans_periode(g.date_operation, mois, annee)]
    gains_bruts = sum(_d(g.gain_brut) for g in gains_periode)
    tpcvm_total = sum(_d(g.tpcvm) for g in gains_periode)
    gains_nets = sum(_d(g.gain_net) for g in gains_periode)

    dividendes_nets = sum(_d(x["montant"]) for x in _dividendes() if _dans_periode(x["date_operation"], mois, annee))

    frais_transactions = sum(_d(t["total_frais"]) for t in calc if _dans_periode(t["date_operation"], mois, annee))
    frais_compte = sum(_d(f["montant"]) for f in _frais_compte() if _dans_periode(f["date_operation"], mois, annee))

    droits_garde = _calcul_droits_garde(positions, params)
    resultat_periode = gains_nets + dividendes_nets - frais_transactions - frais_compte

    return DashboardBourse(
        cout_acquisition=_r(cout_acquisition), valeur_marche=_r(valeur_marche),
        plus_value_latente=_r(plus_value_latente), performance_latente=_r(perf),
        gains_bruts_realises=_r(gains_bruts), tpcvm_total=_r(tpcvm_total),
        gains_nets_realises=_r(gains_nets), dividendes_nets=_r(dividendes_nets),
        frais_transactions_totaux=_r(frais_transactions), frais_compte_totaux=_r(frais_compte),
        resultat_net_periode=_r(resultat_periode),
        droits_garde_trimestriel_estime=droits_garde.montant_trimestriel_du,
    )
