# -*- coding: utf-8 -*-
"""
Module Bourse v2 — achats, ventes, commissions, TPCVM, positions, gains.
Distingue 4 types d'instruments, chacun avec sa propre structure de frais
(grille Attijariwafa bank en vigueur au 01/08/2024) :

    Action      commission de courtage + règlement/livraison + impôt de bourse + TVA (sur courtage uniquement)
    Obligation  commission fixe + impôt de bourse réduit, pas de courtage ni de TVA
    OPCVM       droits d'entrée (achat) ou de sortie (vente), taux propre à chaque fonds
    IPO         commission de souscription proportionnelle avec un minimum (introduction en bourse,
                augmentation de capital)

Les droits de garde (frais trimestriels sur encours, indépendants des transactions)
sont exposés séparément via /droits_garde et intégrés au dashboard à titre indicatif.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from database import db
from securite import utilisateur_courant
from schemas import (
    ParametresBourse, TransactionBourseCreate, TransactionBourseOut,
    PrixMaj, PositionBourse, GainRealise, DashboardBourse, DroitsGarde, TitreBourse,
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


def _frais_type_action(brut: Decimal, t: dict, params: dict) -> tuple:
    """Structure de frais 'Action' : courtage + règlement/livraison + impôt de bourse,
    puis TVA appliquée sur la somme des trois (confirmé sur relevé réel de courtage :
    chaque ligne TTC = ligne HT nominale × 1,10, taux HT = 0.60% / 0.20% / 0.10%)."""
    taux_courtage = _d(t.get("taux_courtage")) if t.get("taux_courtage") is not None else _d(params["taux_courtage_action"])
    taux_rl = _d(t.get("taux_reglement_livraison")) if t.get("taux_reglement_livraison") is not None else _d(params["taux_reglement_livraison"])
    taux_impot = _d(t.get("taux_impot_bourse")) if t.get("taux_impot_bourse") is not None else _d(params["taux_impot_bourse_action"])
    taux_tva = _d(t.get("taux_tva")) if t.get("taux_tva") is not None else _d(params["taux_tva"])
    courtage = brut * taux_courtage
    reglement_livraison = brut * taux_rl
    impot_bourse = brut * taux_impot
    sous_total_ht = courtage + reglement_livraison + impot_bourse
    tva = sous_total_ht * taux_tva
    detail = {"courtage": _r(courtage), "reglement_livraison": _r(reglement_livraison),
               "impot_bourse": _r(impot_bourse), "tva": _r(tva)}
    return detail, sous_total_ht + tva


def _calc_transaction(t: dict, params: dict) -> dict:
    """Recalcule le détail des frais et le montant net à partir d'une ligne DB (+ params courants
    en repli pour les colonnes non renseignées sur d'anciennes lignes)."""
    qte, cours = _d(t["quantite"]), _d(t["cours_unitaire"])
    autres = _d(t["autres_frais"])
    brut = qte * cours
    instrument = t["type_instrument"]
    detail = {}

    if instrument == "Action":
        detail, total_frais = _frais_type_action(brut, t, params)

    elif instrument == "Obligation":
        commission_fixe = _d(t.get("commission_fixe")) if t.get("commission_fixe") is not None else _d(params["commission_fixe_obligation"])
        taux_impot = _d(t.get("taux_impot_bourse")) if t.get("taux_impot_bourse") is not None else _d(params["taux_impot_bourse_obligation"])
        impot_bourse = brut * taux_impot
        detail = {"commission_fixe": _r(commission_fixe), "impot_bourse": _r(impot_bourse)}
        total_frais = commission_fixe + impot_bourse

    elif instrument == "OPCVM":
        defaut = params["droits_entree_opcvm_defaut"] if t["type_operation"] == "Achat" else params["droits_sortie_opcvm_defaut"]
        taux_droits = _d(t.get("taux_droits_opcvm")) if t.get("taux_droits_opcvm") is not None else _d(defaut)
        droits = brut * taux_droits
        label = "droits_entree" if t["type_operation"] == "Achat" else "droits_sortie"
        detail = {label: _r(droits)}
        total_frais = droits

    elif instrument == "IPO":
        if (t.get("structure_ipo") or "souscription") == "action":
            detail, total_frais = _frais_type_action(brut, t, params)
        else:
            taux_souscription = _d(t.get("taux_souscription")) if t.get("taux_souscription") is not None else _d(params["taux_souscription_ipo"])
            minimum = _d(t.get("min_souscription")) if t.get("min_souscription") is not None else _d(params["min_souscription_ipo"])
            commission = max(brut * taux_souscription, minimum)
            detail = {"commission_souscription": _r(commission)}
            total_frais = commission

    else:
        raise HTTPException(status_code=400, detail=f"Type d'instrument inconnu : {instrument}")

    total_frais += autres
    net = brut + total_frais if t["type_operation"] == "Achat" else brut - total_frais

    return {
        **t,
        "montant_brut": _r(brut), "detail_frais": detail,
        "total_frais": _r(total_frais), "montant_net": _r(net),
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
                   taux_courtage_action = %s, taux_reglement_livraison = %s,
                   taux_impot_bourse_action = %s, taux_tva = %s,
                   commission_fixe_obligation = %s, taux_impot_bourse_obligation = %s,
                   taux_droit_garde_annuel = %s, droit_garde_min_trimestriel = %s,
                   taux_souscription_ipo = %s, min_souscription_ipo = %s,
                   droits_entree_opcvm_defaut = %s, droits_sortie_opcvm_defaut = %s,
                   taux_tpcvm = %s""",
            (p.taux_courtage_action, p.taux_reglement_livraison,
             p.taux_impot_bourse_action, p.taux_tva,
             p.commission_fixe_obligation, p.taux_impot_bourse_obligation,
             p.taux_droit_garde_annuel, p.droit_garde_min_trimestriel,
             p.taux_souscription_ipo, p.min_souscription_ipo,
             p.droits_entree_opcvm_defaut, p.droits_sortie_opcvm_defaut,
             p.taux_tpcvm),
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
TX_COLONNES = """id, date_operation, titre, isin, type_instrument, structure_ipo, type_operation, quantite,
                 cours_unitaire, taux_courtage, taux_reglement_livraison, taux_impot_bourse,
                 taux_tva, commission_fixe, taux_droits_opcvm, taux_souscription,
                 min_souscription, autres_frais"""


@router.get("/transactions", response_model=List[TransactionBourseOut])
def lister_transactions():
    with db() as conn:
        params = _parametres_dict(conn)
        rows = conn.execute(
            f"SELECT {TX_COLONNES} FROM bourse_transactions ORDER BY date_operation DESC, id DESC"
        ).fetchall()
    return [_calc_transaction(dict(r), params) for r in rows]


@router.post("/transactions", response_model=TransactionBourseOut, status_code=201)
def creer_transaction(t: TransactionBourseCreate):
    with db() as conn:
        p = _parametres_dict(conn)

        taux_courtage = taux_reglement_livraison = taux_impot_bourse = taux_tva = None
        commission_fixe = taux_droits_opcvm = taux_souscription = min_souscription = None

        if t.type_instrument == "Action" or (t.type_instrument == "IPO" and t.structure_ipo == "action"):
            taux_courtage = t.taux_courtage if t.taux_courtage is not None else float(p["taux_courtage_action"])
            taux_reglement_livraison = t.taux_reglement_livraison if t.taux_reglement_livraison is not None else float(p["taux_reglement_livraison"])
            taux_impot_bourse = t.taux_impot_bourse if t.taux_impot_bourse is not None else float(p["taux_impot_bourse_action"])
            taux_tva = t.taux_tva if t.taux_tva is not None else float(p["taux_tva"])
        elif t.type_instrument == "Obligation":
            commission_fixe = t.commission_fixe if t.commission_fixe is not None else float(p["commission_fixe_obligation"])
            taux_impot_bourse = t.taux_impot_bourse if t.taux_impot_bourse is not None else float(p["taux_impot_bourse_obligation"])
        elif t.type_instrument == "OPCVM":
            defaut = p["droits_entree_opcvm_defaut"] if t.type_operation == "Achat" else p["droits_sortie_opcvm_defaut"]
            taux_droits_opcvm = t.taux_droits_opcvm if t.taux_droits_opcvm is not None else float(defaut)
        elif t.type_instrument == "IPO":  # structure_ipo == "souscription"
            taux_souscription = t.taux_souscription if t.taux_souscription is not None else float(p["taux_souscription_ipo"])
            min_souscription = t.min_souscription if t.min_souscription is not None else float(p["min_souscription_ipo"])

        row = conn.execute(
            f"""INSERT INTO bourse_transactions
                    (date_operation, titre, isin, type_instrument, structure_ipo, type_operation, quantite,
                     cours_unitaire, taux_courtage, taux_reglement_livraison, taux_impot_bourse,
                     taux_tva, commission_fixe, taux_droits_opcvm, taux_souscription,
                     min_souscription, autres_frais)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING {TX_COLONNES}""",
            (t.date_operation, t.titre.strip().upper(), t.isin, t.type_instrument,
             t.structure_ipo if t.type_instrument == "IPO" else None, t.type_operation,
             t.quantite, t.cours_unitaire, taux_courtage, taux_reglement_livraison, taux_impot_bourse,
             taux_tva, commission_fixe, taux_droits_opcvm, taux_souscription, min_souscription,
             t.autres_frais),
        ).fetchone()
    return _calc_transaction(dict(row), p)


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
    """Coût moyen pondéré par titre (tous instruments confondus) + gain/perte et TPCVM par vente."""
    with db() as conn:
        params = _parametres_dict(conn)
        txs = [dict(r) for r in conn.execute(
            f"SELECT {TX_COLONNES} FROM bourse_transactions ORDER BY date_operation ASC, id ASC"
        ).fetchall()]
        prix = {r["titre"]: _d(r["cours_actuel"]) for r in conn.execute("SELECT titre, cours_actuel FROM bourse_prix").fetchall()}
        tpcvm_rate = _d(params["taux_tpcvm"])

    calc = [_calc_transaction(t, params) for t in txs]

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
def obtenir_gains():
    _, gains, _, _ = _positions_et_gains()
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
def obtenir_dashboard():
    positions, gains, calc, params = _positions_et_gains()

    cout_acquisition = sum(_d(p.valeur_comptable) for p in positions)
    valeur_marche = sum(_d(p.valeur_marche) for p in positions)
    plus_value_latente = valeur_marche - cout_acquisition
    perf = (plus_value_latente / cout_acquisition) if cout_acquisition != 0 else Decimal(0)

    gains_bruts = sum(_d(g.gain_brut) for g in gains)
    tpcvm_total = sum(_d(g.tpcvm) for g in gains)
    gains_nets = sum(_d(g.gain_net) for g in gains)

    commissions = sum(sum(_d(v) for k, v in t["detail_frais"].items()
                           if k in ("courtage", "commission_fixe", "commission_souscription")) for t in calc)
    tva = sum(_d(t["detail_frais"].get("tva", 0)) for t in calc)
    frais = sum(_d(t["total_frais"]) for t in calc)

    droits_garde = _calcul_droits_garde(positions, params)
    resultat_global = plus_value_latente + gains_nets - frais

    return DashboardBourse(
        cout_acquisition=_r(cout_acquisition), valeur_marche=_r(valeur_marche),
        plus_value_latente=_r(plus_value_latente), performance_latente=_r(perf),
        gains_bruts_realises=_r(gains_bruts), tpcvm_total=_r(tpcvm_total),
        gains_nets_realises=_r(gains_nets), commissions_totales=_r(commissions),
        tva_totale=_r(tva), frais_totaux=_r(frais),
        droits_garde_trimestriel_estime=droits_garde.montant_trimestriel_du,
        resultat_net_global=_r(resultat_global),
    )