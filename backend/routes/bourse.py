# -*- coding: utf-8 -*-
"""
Module Bourse — achats, ventes, dividendes, frais de compte, positions, gains,
et mouvements d'argent entre la banque et le compte Bourse (apports / retraits).

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
      cession de valeurs mobilières).

Les droits de garde ne sont plus estimés automatiquement : à saisir
manuellement dans le journal des frais de compte (montant réel facturé par
l'intermédiaire), comme n'importe quel autre frais.

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
    PrixMaj, PositionBourse, GainRealise, DashboardBourse, TitreBourse, TitreBourseIn,
    DividendeCreate, DividendeOut, FraisBourseCreate, FraisBourseOut,
    MouvementBourseCreate, MouvementBourseOut,
)

router = APIRouter(prefix="/api/bourse", tags=["bourse"],
                    dependencies=[Depends(utilisateur_courant)])

Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")


def _r(x) -> float:
    """Arrondi 2 décimales puis conversion en float pour la réponse JSON (montants en DH)."""
    return float(Decimal(x).quantize(Q2, rounding=ROUND_HALF_UP))


def _r4(x) -> float:
    """Arrondi 4 décimales : pour les ratios (performance) affichés ensuite en %.
    Arrondir un ratio à 2 décimales (ex : 0,0534) tronquerait le pourcentage
    affiché (5,34 % deviendrait 5,00 %)."""
    return float(Decimal(x).quantize(Q4, rounding=ROUND_HALF_UP))


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


def _clause_periode(mois: Optional[str], annee: Optional[int]) -> tuple:
    """Clause SQL (+ paramètres) pour filtrer `date_operation` par mois/année — évite de
    charger toutes les lignes pour les filtrer ensuite en Python. Non utilisable pour les
    positions/gains, qui doivent toujours parcourir tout l'historique (PRU chronologique) :
    là, le filtre reste appliqué en Python sur le résultat déjà calculé."""
    if mois:
        return " AND date_operation >= %s AND date_operation < (%s::date + INTERVAL '1 month')", (mois + "-01", mois + "-01")
    if annee:
        return " AND date_operation >= %s AND date_operation < %s", (f"{annee}-01-01", f"{annee + 1}-01-01")
    return "", ()


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
        conn.execute("UPDATE bourse_parametres SET taux_tpcvm = %s", (p.taux_tpcvm,))
        return _parametres_dict(conn)


@router.get("/titres", response_model=List[TitreBourse])
def lister_titres():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, code, nom, secteur FROM bourse_titres WHERE actif = 1 ORDER BY nom"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/titres", response_model=TitreBourse, status_code=201)
def ajouter_titre(t: TitreBourseIn):
    with db() as conn:
        row = conn.execute(
            """INSERT INTO bourse_titres (code, nom, secteur) VALUES (%s,%s,%s)
               ON CONFLICT (code) DO UPDATE SET nom = EXCLUDED.nom, secteur = EXCLUDED.secteur, actif = 1
               RETURNING id, code, nom, secteur""",
            (t.code.strip().upper(), t.nom.strip(), t.secteur.strip()),
        ).fetchone()
    return dict(row)


@router.put("/titres/{titre_id}", response_model=TitreBourse)
def modifier_titre(titre_id: int, t: TitreBourseIn):
    nouveau_code = t.code.strip().upper()
    with db() as conn:
        ancien = conn.execute("SELECT code FROM bourse_titres WHERE id = %s", (titre_id,)).fetchone()
        if not ancien:
            raise HTTPException(404, "Titre introuvable")
        row = conn.execute(
            """UPDATE bourse_titres SET code = %s, nom = %s, secteur = %s WHERE id = %s
               RETURNING id, code, nom, secteur""",
            (nouveau_code, t.nom.strip(), t.secteur.strip(), titre_id),
        ).fetchone()
        if nouveau_code != ancien["code"]:
            # Le code sert de clé de rapprochement (texte libre) dans les transactions,
            # dividendes et cours actuels — le renommer les détacherait sinon.
            conn.execute("UPDATE bourse_transactions SET titre = %s WHERE titre = %s", (nouveau_code, ancien["code"]))
            conn.execute("UPDATE bourse_dividendes SET titre = %s WHERE titre = %s", (nouveau_code, ancien["code"]))
            conn.execute("UPDATE bourse_prix SET titre = %s WHERE titre = %s", (nouveau_code, ancien["code"]))
    return dict(row)


@router.delete("/titres/{titre_id}", status_code=204)
def desactiver_titre(titre_id: int):
    with db() as conn:
        res = conn.execute("UPDATE bourse_titres SET actif = 0 WHERE id = %s", (titre_id,))
        if res.rowcount == 0:
            raise HTTPException(404, "Titre introuvable")


# ---------------------------------------------------------------- transactions
TX_COLONNES = "id, date_operation, titre, isin, type_instrument, type_operation, quantite, cours_unitaire, autres_frais"


@router.get("/transactions", response_model=List[TransactionBourseOut])
def lister_transactions(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    clause, params = _clause_periode(mois, annee)
    with db() as conn:
        rows = conn.execute(
            f"SELECT {TX_COLONNES} FROM bourse_transactions WHERE true{clause} ORDER BY date_operation DESC, id DESC",
            params,
        ).fetchall()
    return [_calc_transaction(dict(r)) for r in rows]


def _valider_vente(conn, titre: str, date_operation, quantite: Decimal, exclude_id: Optional[int] = None):
    """Refuse une vente qui ferait passer la quantité détenue sous zéro, à quelque
    moment de l'historique que ce soit (utile aussi pour une vente antidatée insérée
    entre deux transactions existantes)."""
    rows = conn.execute(
        "SELECT id, date_operation, type_operation, quantite FROM bourse_transactions WHERE titre = %s",
        (titre,),
    ).fetchall()
    evenements = [(r["date_operation"], r["id"], r["type_operation"], _d(r["quantite"]))
                  for r in rows if r["id"] != exclude_id]
    # La nouvelle vente : id=+inf pour être triée après les transactions existantes de la même date
    evenements.append((date_operation, float("inf"), "Vente", quantite))
    evenements.sort(key=lambda e: (e[0], e[1]))

    qte = Decimal(0)
    for _, _, type_operation, q in evenements:
        qte += q if type_operation == "Achat" else -q
        if qte < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Vente refusée : quantité détenue insuffisante pour {titre} à cette date",
            )


@router.post("/transactions", response_model=TransactionBourseOut, status_code=201)
def creer_transaction(t: TransactionBourseCreate):
    with db() as conn:
        if t.type_operation == "Vente":
            _valider_vente(conn, t.titre.strip().upper(), t.date_operation, _d(t.quantite))
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


def _dividendes(mois: Optional[str] = None, annee: Optional[int] = None) -> list:
    clause, params = _clause_periode(mois, annee)
    with db() as conn:
        rows = conn.execute(
            f"SELECT {DIV_COLONNES} FROM bourse_dividendes WHERE true{clause} ORDER BY date_operation DESC, id DESC",
            params,
        ).fetchall()
    return [{**dict(r), "montant": _r(r["montant"])} for r in rows]


@router.get("/dividendes", response_model=List[DividendeOut])
def lister_dividendes(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    return _dividendes(mois, annee)


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


def _frais_compte(mois: Optional[str] = None, annee: Optional[int] = None) -> list:
    clause, params = _clause_periode(mois, annee)
    with db() as conn:
        rows = conn.execute(
            f"SELECT {FRAIS_COLONNES} FROM bourse_frais WHERE true{clause} ORDER BY date_operation DESC, id DESC",
            params,
        ).fetchall()
    return [{**dict(r), "montant": _r(r["montant"])} for r in rows]


@router.get("/frais", response_model=List[FraisBourseOut])
def lister_frais(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    return _frais_compte(mois, annee)


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


# ---------------------------------------------------------------- mouvements banque <-> compte Bourse
MVT_COLONNES = "id, date_operation, type_mouvement, montant, libelle"


def _mouvements(mois: Optional[str] = None, annee: Optional[int] = None) -> list:
    clause, params = _clause_periode(mois, annee)
    with db() as conn:
        rows = conn.execute(
            f"SELECT {MVT_COLONNES} FROM bourse_mouvements WHERE true{clause} ORDER BY date_operation DESC, id DESC",
            params,
        ).fetchall()
    return [{**dict(r), "montant": _r(r["montant"])} for r in rows]


@router.get("/mouvements", response_model=List[MouvementBourseOut])
def lister_mouvements(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    return _mouvements(mois, annee)


@router.post("/mouvements", response_model=MouvementBourseOut, status_code=201)
def creer_mouvement(m: MouvementBourseCreate):
    with db() as conn:
        row = conn.execute(
            f"""INSERT INTO bourse_mouvements (date_operation, type_mouvement, montant, libelle)
                VALUES (%s,%s,%s,%s)
                RETURNING {MVT_COLONNES}""",
            (m.date_operation, m.type_mouvement, m.montant, m.libelle.strip()),
        ).fetchone()
    return {**dict(row), "montant": _r(row["montant"])}


@router.delete("/mouvements/{mouvement_id}", status_code=204)
def supprimer_mouvement(mouvement_id: int):
    with db() as conn:
        res = conn.execute("DELETE FROM bourse_mouvements WHERE id = %s", (mouvement_id,))
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mouvement introuvable")


# ---------------------------------------------------------------- calcul positions / gains (logique commune)
def _positions_et_gains():
    """Coût moyen pondéré (mobile) par titre + gain/perte et TPCVM par vente.

    Chaque titre est traité indépendamment, dans l'ordre chronologique de SES
    transactions : le PRU courant sert à calculer le gain d'une vente, puis le
    coût restant est réduit de `pru_courant × quantité vendue`. Un achat
    ultérieur ne doit jamais influencer le PRU utilisé pour une vente qui a eu
    lieu avant lui (contrairement à une simple moyenne pondérée sur tout
    l'historique, qui mélangerait les cycles achat→vente→rachat).

    Simplification fiscale assumée : la TPCVM est calculée vente par vente
    (15 % du gain si positif, 0 si la vente est en perte) — les pertes d'une
    vente ne viennent PAS compenser les gains d'une autre vente sur la même
    année, contrairement à la compensation annuelle que prévoit la
    réglementation marocaine sur les profits de cession de valeurs mobilières.
    À vérifier/ajuster auprès d'un professionnel si tu as plusieurs ventes
    (gagnantes et perdantes) sur la même année fiscale : le total affiché ici
    peut alors surestimer l'impôt réellement dû."""
    with db() as conn:
        params = _parametres_dict(conn)
        txs = [dict(r) for r in conn.execute(
            f"SELECT {TX_COLONNES} FROM bourse_transactions ORDER BY date_operation ASC, id ASC"
        ).fetchall()]
        prix = {r["titre"]: _d(r["cours_actuel"]) for r in conn.execute("SELECT titre, cours_actuel FROM bourse_prix").fetchall()}
        secteurs = {r["code"]: r["secteur"] for r in conn.execute("SELECT code, secteur FROM bourse_titres").fetchall()}
        tpcvm_rate = _d(params["taux_tpcvm"])

    calc = [_calc_transaction(t) for t in txs]

    par_titre = {}
    for t in calc:
        par_titre.setdefault(t["titre"], []).append(t)

    positions = []
    gains = []
    for titre, txs_titre in par_titre.items():
        qte_achat_total = Decimal(0)
        qte_vente_total = Decimal(0)
        qte_detenue = Decimal(0)
        cout_restant = Decimal(0)   # coût total (au PRU courant) du stock actuellement détenu

        for t in txs_titre:
            qte = _d(t["quantite"])
            if t["type_operation"] == "Achat":
                qte_achat_total += qte
                qte_detenue += qte
                cout_restant += t["_net_decimal"]
            else:
                qte_vente_total += qte
                pru_courant = cout_restant / qte_detenue if qte_detenue > 0 else Decimal(0)
                net = t["_net_decimal"]
                gain_brut = net - (pru_courant * qte)
                tpcvm = gain_brut * tpcvm_rate if gain_brut > 0 else Decimal(0)
                gain_net = gain_brut - tpcvm
                gains.append(GainRealise(
                    id=t["id"], date_operation=t["date_operation"], titre=titre, type_instrument=t["type_instrument"],
                    quantite=_r(qte), cours_vente=_r(_d(t["cours_unitaire"])), pru=_r(pru_courant), montant_net=_r(net),
                    gain_brut=_r(gain_brut), taux_tpcvm=_r(tpcvm_rate), tpcvm=_r(tpcvm), gain_net=_r(gain_net),
                ))
                cout_restant -= pru_courant * qte
                qte_detenue -= qte

        pru_final = cout_restant / qte_detenue if qte_detenue > 0 else Decimal(0)
        cours = prix.get(titre, Decimal(0))
        valeur_comptable = pru_final * qte_detenue
        valeur_marche = cours * qte_detenue
        plus_value = valeur_marche - valeur_comptable
        perf = (plus_value / valeur_comptable) if valeur_comptable != 0 else Decimal(0)
        positions.append(PositionBourse(
            titre=titre, secteur=secteurs.get(titre) or "Non classé",
            quantite_achetee=_r(qte_achat_total), quantite_vendue=_r(qte_vente_total),
            quantite_detenue=_r(qte_detenue), pru=_r(pru_final), cours_actuel=_r(cours),
            valeur_comptable=_r(valeur_comptable), valeur_marche=_r(valeur_marche),
            plus_value_latente=_r(plus_value), performance_latente=_r4(perf),
        ))

    return positions, gains, calc


@router.get("/positions", response_model=List[PositionBourse])
def obtenir_positions():
    positions, _, _ = _positions_et_gains()
    return positions


@router.get("/gains", response_model=List[GainRealise])
def obtenir_gains(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    _, gains, _ = _positions_et_gains()
    gains = [g for g in gains if _dans_periode(g.date_operation, mois, annee)]
    return sorted(gains, key=lambda g: g.date_operation, reverse=True)


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard", response_model=DashboardBourse)
def obtenir_dashboard(mois: Optional[str] = None, annee: Optional[int] = None):
    """`mois` (AAAA-MM) ou `annee` filtrent les flux réalisés (gains, dividendes, frais) sur
    la période choisie. Sans filtre : tout l'historique. La valorisation du portefeuille
    (coût d'acquisition, valeur de marché, plus-value latente) reste toujours celle
    d'aujourd'hui, indépendamment du filtre — il n'y a pas d'historique de cours enregistré."""
    _valider_periode(mois, annee)
    positions, gains, calc = _positions_et_gains()

    cout_acquisition = sum(_d(p.valeur_comptable) for p in positions)
    valeur_marche = sum(_d(p.valeur_marche) for p in positions)
    plus_value_latente = valeur_marche - cout_acquisition
    perf = (plus_value_latente / cout_acquisition) if cout_acquisition != 0 else Decimal(0)

    gains_periode = [g for g in gains if _dans_periode(g.date_operation, mois, annee)]
    gains_bruts = sum(_d(g.gain_brut) for g in gains_periode)
    tpcvm_total = sum(_d(g.tpcvm) for g in gains_periode)
    gains_nets = sum(_d(g.gain_net) for g in gains_periode)

    dividendes_nets = sum(_d(x["montant"]) for x in _dividendes(mois, annee))

    # Informatif uniquement : les frais de transaction sont déjà comptés dans gains_nets
    # (soustraits du montant net de chaque vente) et dans le PRU des achats — les resoustraire
    # ici doublerait leur effet sur le résultat de la période.
    # Filtré en Python (et non en SQL) car `calc` provient de _positions_et_gains(), qui doit
    # nécessairement charger tout l'historique pour un PRU chronologique correct — la ligne
    # est déjà en mémoire, la filtrer ici n'ajoute aucune requête.
    frais_transactions = sum(_d(t["total_frais"]) for t in calc if _dans_periode(t["date_operation"], mois, annee))
    frais_compte = sum(_d(f["montant"]) for f in _frais_compte(mois, annee))

    resultat_periode = gains_nets + dividendes_nets - frais_compte

    # ---- Compte Bourse dans son ensemble (tout l'historique, indépendant du filtre)
    # Espèces = apports − retraits − achats + ventes − TPCVM + dividendes − frais de compte.
    # La TPCVM est retenue à la source par l'intermédiaire sur le produit de la vente :
    # l'argent réellement crédité sur le compte est donc montant_net − tpcvm.
    mouvements = _mouvements()
    apports = sum(_d(m["montant"]) for m in mouvements if m["type_mouvement"] == "Apport")
    retraits = sum(_d(m["montant"]) for m in mouvements if m["type_mouvement"] == "Retrait")
    tpcvm_par_vente = {g.id: _d(g.tpcvm) for g in gains}
    achats = sum(t["_net_decimal"] for t in calc if t["type_operation"] == "Achat")
    ventes = sum(t["_net_decimal"] - tpcvm_par_vente.get(t["id"], Decimal(0))
                 for t in calc if t["type_operation"] == "Vente")
    dividendes_tout = sum(_d(x["montant"]) for x in _dividendes())
    frais_tout = sum(_d(f["montant"]) for f in _frais_compte())
    especes = apports - retraits - achats + ventes + dividendes_tout - frais_tout

    apports_nets = apports - retraits
    patrimoine = valeur_marche + especes
    perf_globale = patrimoine - apports_nets
    perf_globale_pct = (perf_globale / apports_nets) if apports_nets > 0 else Decimal(0)

    mvts_periode = [m for m in mouvements if _dans_periode(m["date_operation"], mois, annee)]
    apports_periode = sum(_d(m["montant"]) for m in mvts_periode if m["type_mouvement"] == "Apport")
    retraits_periode = sum(_d(m["montant"]) for m in mvts_periode if m["type_mouvement"] == "Retrait")

    return DashboardBourse(
        cout_acquisition=_r(cout_acquisition), valeur_marche=_r(valeur_marche),
        plus_value_latente=_r(plus_value_latente), performance_latente=_r4(perf),
        gains_bruts_realises=_r(gains_bruts), tpcvm_total=_r(tpcvm_total),
        gains_nets_realises=_r(gains_nets), dividendes_nets=_r(dividendes_nets),
        frais_transactions_totaux=_r(frais_transactions), frais_compte_totaux=_r(frais_compte),
        resultat_net_periode=_r(resultat_periode),
        apports_periode=_r(apports_periode), retraits_periode=_r(retraits_periode),
        especes_disponibles=_r(especes), apports_nets=_r(apports_nets),
        patrimoine_total=_r(patrimoine), performance_globale=_r(perf_globale),
        performance_globale_pct=_r4(perf_globale_pct),
    )
