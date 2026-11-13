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

La TPCVM (taxe sur les profits de cession) est elle aussi saisie
manuellement sur chaque vente, telle qu'elle figure sur l'avis d'opéré.

Restent calculés automatiquement (on ne peut pas les « lire » sur un relevé) :
    - le PRU (coût moyen pondéré) et les plus/moins-values latentes ;
    - le gain/perte réalisé à la vente (gain net = gain brut − TPCVM saisie).

Les droits de garde ne sont plus estimés automatiquement : à saisir
manuellement dans le journal des frais de compte (montant réel facturé par
l'intermédiaire), comme n'importe quel autre frais.

Le dashboard accepte des filtres optionnels `mois` (AAAA-MM) ou `annee` pour
les flux réalisés sur la période (gains, dividendes, frais). La valeur du
portefeuille (coût d'acquisition, valeur de marché, plus-value latente) reste
toujours celle d'aujourd'hui. Les cours sont notés chaque jour depuis la mise en
place de bourse_prix_historique : la courbe de valeur (GET /historique) commence là.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from config import aujourdhui
from cours_bvc import telecharger_cours
from database import db, references_valides
from securite import utilisateur_courant
from routes.carnet import ajouter_mois
from schemas import (
    ParametresBourse, TransactionBourseCreate, TransactionBourseOut,
    PrixMaj, PositionBourse, GainRealise, DashboardBourse, TitreBourse, TitreBourseIn, CoursActualisation,
    DividendeCreate, DividendeOut, FraisBourseCreate, FraisBourseOut,
    MouvementBourseCreate, MouvementBourseOut, CiblesIn, CiblesTitresIn, JourFerieIn, ImportIndiceIn,
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
    """Prix déjà net (aucun frais calculé automatiquement) : montant_net = brut ± autres_frais.
    La TPCVM saisie n'est pas incluse dans montant_net : elle est retirée du gain (gain net)
    et des espèces encaissées, pas du produit de cession qui sert au calcul du gain brut."""
    qte, cours = _d(t["quantite"]), _d(t["cours_unitaire"])
    autres = _d(t["autres_frais"])
    brut = qte * cours
    net = brut + autres if t["type_operation"] == "Achat" else brut - autres
    return {
        **t, "montant_brut": _r(brut), "autres_frais": _r(autres),
        "total_frais": _r(autres), "tpcvm": _r(_d(t["tpcvm"])), "montant_net": _r(net),
        "_net_decimal": net,   # gardé en interne pour les calculs de position/gains
        "_tpcvm_saisie": t["tpcvm"],   # None = vente ancienne pas encore remplie (cf. remplir_tpcvm_manquantes)
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


def _isin(v: Optional[str]) -> Optional[str]:
    """ISIN normalisé (majuscules, sans espaces) ; None si vide."""
    return (v or "").strip().upper() or None


@router.get("/titres", response_model=List[TitreBourse])
def lister_titres():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, code, nom, secteur, isin FROM bourse_titres WHERE actif = 1 ORDER BY nom"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/titres", response_model=TitreBourse, status_code=201)
def ajouter_titre(t: TitreBourseIn):
    with db() as conn:
        row = conn.execute(
            """INSERT INTO bourse_titres (code, nom, secteur, isin) VALUES (%s,%s,%s,%s)
               ON CONFLICT (code) DO UPDATE SET nom = EXCLUDED.nom, secteur = EXCLUDED.secteur,
                                                isin = EXCLUDED.isin, actif = 1
               RETURNING id, code, nom, secteur, isin""",
            (t.code.strip().upper(), t.nom.strip(), t.secteur.strip(), _isin(t.isin)),
        ).fetchone()
    return dict(row)


@router.put("/titres/{titre_id}", response_model=TitreBourse)
def modifier_titre(titre_id: int, t: TitreBourseIn):
    nouveau_code = t.code.strip().upper()
    try:
        with db() as conn:
            ancien = conn.execute("SELECT code FROM bourse_titres WHERE id = %s", (titre_id,)).fetchone()
            if not ancien:
                raise HTTPException(404, "Titre introuvable")
            row = conn.execute(
                """UPDATE bourse_titres SET code = %s, nom = %s, secteur = %s, isin = %s WHERE id = %s
                   RETURNING id, code, nom, secteur, isin""",
                (nouveau_code, t.nom.strip(), t.secteur.strip(), _isin(t.isin), titre_id),
            ).fetchone()
            # Transactions, dividendes et cours suivent le nouveau code : clés étrangères
            # ON UPDATE CASCADE (database.CLES_ETRANGERES)
    except UniqueViolation:
        # Code déjà pris par un autre titre (ou cours déjà enregistré sous ce code)
        raise HTTPException(409, f"Le code « {nouveau_code} » est déjà utilisé par un autre titre")
    return dict(row)


@router.delete("/titres/{titre_id}", status_code=204)
def desactiver_titre(titre_id: int):
    with db() as conn:
        res = conn.execute("UPDATE bourse_titres SET actif = 0 WHERE id = %s", (titre_id,))
        if res.rowcount == 0:
            raise HTTPException(404, "Titre introuvable")


# ---------------------------------------------------------------- transactions
TX_COLONNES = "id, date_operation, titre, isin, type_instrument, type_operation, quantite, cours_unitaire, autres_frais, tpcvm, note"


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


def _historique_negatif(conn, titre: str, exclude_id: Optional[int] = None, ajout: Optional[tuple] = None) -> bool:
    """Rejoue l'historique de `titre` dans l'ordre chronologique et indique si la quantité
    détenue passe sous zéro à un moment quelconque. `exclude_id` retire une transaction
    (suppression ou modification), `ajout` = (date, type_operation, quantité) en ajoute une."""
    rows = conn.execute(
        "SELECT id, date_operation, type_operation, quantite FROM bourse_transactions WHERE titre = %s",
        (titre,),
    ).fetchall()
    evenements = [(r["date_operation"], r["id"], r["type_operation"], _d(r["quantite"]))
                  for r in rows if r["id"] != exclude_id]
    if ajout:
        # La nouvelle opération : id=+inf pour être triée après les transactions existantes de la même date
        evenements.append((ajout[0], float("inf"), ajout[1], ajout[2]))
    evenements.sort(key=lambda e: (e[0], e[1]))

    qte = Decimal(0)
    for _, _, type_operation, q in evenements:
        qte += q if type_operation == "Achat" else -q
        if qte < 0:
            return True
    return False


def _valider_vente(conn, titre: str, date_operation, quantite: Decimal, exclude_id: Optional[int] = None):
    """Refuse une vente qui ferait passer la quantité détenue sous zéro, à quelque
    moment de l'historique que ce soit (utile aussi pour une vente antidatée insérée
    entre deux transactions existantes)."""
    if _historique_negatif(conn, titre, exclude_id, ajout=(date_operation, "Vente", quantite)):
        raise HTTPException(
            status_code=400,
            detail=f"Vente refusée : quantité détenue insuffisante pour {titre} à cette date",
        )


@router.post("/transactions", response_model=TransactionBourseOut, status_code=201)
def creer_transaction(t: TransactionBourseCreate):
    # Le code doit être un titre de la liste (Paramètres > Titres), même retiré : clé étrangère
    with references_valides(), db() as conn:
        if t.type_operation == "Vente":
            _valider_vente(conn, t.titre.strip().upper(), t.date_operation, _d(t.quantite))
        row = conn.execute(
            f"""INSERT INTO bourse_transactions
                    (date_operation, titre, isin, type_instrument, type_operation, quantite, cours_unitaire, autres_frais, tpcvm, note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING {TX_COLONNES}""",
            (t.date_operation, t.titre.strip().upper(), t.isin, t.type_instrument,
             t.type_operation, t.quantite, t.cours_unitaire, t.autres_frais,
             t.tpcvm if t.type_operation == "Vente" else 0, t.note.strip()),
        ).fetchone()
    return _calc_transaction(dict(row))


@router.put("/transactions/{transaction_id}", response_model=TransactionBourseOut)
def modifier_transaction(transaction_id: int, t: TransactionBourseCreate):
    """Modifie une transaction, à condition que l'historique reste cohérent : ni l'ancien titre
    (si elle en change) ni le nouveau ne doivent avoir une quantité détenue négative."""
    titre = t.titre.strip().upper()
    with references_valides(), db() as conn:
        ancienne = conn.execute("SELECT titre, type_operation FROM bourse_transactions WHERE id = %s",
                                (transaction_id,)).fetchone()
        if not ancienne:
            raise HTTPException(status_code=404, detail="Transaction introuvable")
        if ancienne["titre"] != titre and _historique_negatif(conn, ancienne["titre"], exclude_id=transaction_id):
            raise HTTPException(400, f"Modification refusée : des ventes de {ancienne['titre']} reposent sur cet achat.")
        if _historique_negatif(conn, titre, exclude_id=transaction_id,
                               ajout=(t.date_operation, t.type_operation, _d(t.quantite))):
            raise HTTPException(400, f"Modification refusée : la quantité détenue de {titre} deviendrait négative.")
        row = conn.execute(
            f"""UPDATE bourse_transactions SET date_operation=%s, titre=%s, isin=%s, type_instrument=%s,
                       type_operation=%s, quantite=%s, cours_unitaire=%s, autres_frais=%s, tpcvm=%s, note=%s
                WHERE id=%s RETURNING {TX_COLONNES}""",
            (t.date_operation, titre, t.isin, t.type_instrument, t.type_operation, t.quantite,
             t.cours_unitaire, t.autres_frais, t.tpcvm if t.type_operation == "Vente" else 0, t.note.strip(), transaction_id),
        ).fetchone()
    return _calc_transaction(dict(row))


@router.delete("/transactions/{transaction_id}", status_code=204)
def supprimer_transaction(transaction_id: int):
    with db() as conn:
        tx = conn.execute("SELECT titre, type_operation FROM bourse_transactions WHERE id = %s",
                          (transaction_id,)).fetchone()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction introuvable")
        # Sans cet achat, une vente postérieure porterait sur des titres jamais détenus
        # (quantité négative, PRU et gains faux)
        if tx["type_operation"] == "Achat" and _historique_negatif(conn, tx["titre"], exclude_id=transaction_id):
            raise HTTPException(
                status_code=400,
                detail=f"Suppression refusée : des ventes de {tx['titre']} reposent sur cet achat. Supprime d'abord ces ventes.",
            )
        conn.execute("DELETE FROM bourse_transactions WHERE id = %s", (transaction_id,))


# ---------------------------------------------------------------- prix courants
@router.put("/prix/{titre}")
def maj_prix(titre: str, p: PrixMaj):
    """Saisie manuelle : le cours est verrouillé (les cours automatiques ne l'écrasent plus)
    jusqu'à sa remise en automatique."""
    with references_valides(), db() as conn:
        conn.execute(
            """INSERT INTO bourse_prix (titre, cours_actuel, maj_le, manuel)
               VALUES (%s, %s, now(), true)
               ON CONFLICT (titre) DO UPDATE SET cours_actuel = EXCLUDED.cours_actuel, maj_le = now(), manuel = true""",
            (titre.strip().upper(), p.cours_actuel),
        )
    return {"titre": titre.strip().upper(), "cours_actuel": p.cours_actuel}


# ---------------------------------------------------------------- cours automatiques
DELAI_COURS_MIN = 15   # pas plus d'une récupération automatique par quart d'heure


def _actualiser_cours(force: bool) -> CoursActualisation:
    """Écrit le dernier cours des titres détenus qui ne sont pas en saisie manuelle (rapprochés
    par leur code BVC sur la source officielle, par leur ISIN sur la source de secours). Déclenché
    par la tâche du matin et à l'ouverture de l'application (force=False), ou par le bouton
    « Actualiser » et la tâche du soir (force=True).
    Si les sources sont injoignables, rien n'est modifié et les derniers cours connus restent affichés."""
    return _recuperer_cours(force)[0]


def _recuperer_cours(force: bool) -> tuple:
    """(résultat, titres dont le cours vient d'être récupéré) : cf. _actualiser_cours."""
    with db() as conn:
        if not force and conn.execute(
            "SELECT 1 FROM bourse_parametres WHERE cours_auto_le > now() - make_interval(mins => %s)",
            (DELAI_COURS_MIN,),
        ).fetchone():
            return CoursActualisation(etat="recent"), []
        cibles = conn.execute(
            """SELECT d.titre, t.isin
               FROM (SELECT titre FROM bourse_transactions GROUP BY titre
                     HAVING SUM(CASE WHEN type_operation = 'Achat' THEN quantite ELSE -quantite END) > 0) d
               LEFT JOIN bourse_titres t ON t.code = d.titre
               LEFT JOIN bourse_prix p ON p.titre = d.titre
               WHERE NOT COALESCE(p.manuel, false)"""
        ).fetchall()
    if not cibles:
        return CoursActualisation(etat="rien", message="Aucun titre détenu en cours automatique"), []

    # Appel réseau fait hors de la connexion à la base, pour ne pas la retenir pendant l'attente
    try:
        cours = telecharger_cours()
    except Exception as e:
        print(f"[cours] récupération échouée — {e}", flush=True)   # détail visible dans les logs du serveur
        return CoursActualisation(etat="erreur", message="Sources des cours injoignables : derniers cours conservés"), []

    valeurs = {c["titre"]: cours.de(c["titre"], c["isin"]) for c in cibles}
    trouves = [(titre, valeur) for titre, valeur in valeurs.items() if valeur]
    with db() as conn:
        for titre, valeur in trouves:
            # `manuel = false` dans le WHERE : une saisie manuelle faite pendant le téléchargement est respectée
            conn.execute(
                """INSERT INTO bourse_prix (titre, cours_actuel, maj_le, manuel)
                   VALUES (%s, %s, now(), false)
                   ON CONFLICT (titre) DO UPDATE SET cours_actuel = EXCLUDED.cours_actuel, maj_le = now()
                   WHERE bourse_prix.manuel = false""",
                (titre, valeur),
            )
        conn.execute("UPDATE bourse_parametres SET cours_auto_le = now()")
    return CoursActualisation(
        etat="maj", nb_maj=len(trouves),
        introuvables=[titre for titre, valeur in valeurs.items() if not valeur],
        message=f"{len(trouves)} cours mis à jour ({cours.source})",
    ), [titre for titre, _ in trouves]


@router.post("/cours/actualiser", response_model=CoursActualisation)
def actualiser_cours(force: bool = False):
    return _actualiser_cours(force)


@router.put("/prix/{titre}/auto", response_model=CoursActualisation)
def remettre_cours_auto(titre: str):
    """Déverrouille un cours saisi à la main, puis récupère tout de suite les cours."""
    with db() as conn:
        conn.execute("UPDATE bourse_prix SET manuel = false WHERE titre = %s", (titre.strip().upper(),))
    return _actualiser_cours(force=True)


# ---------------------------------------------------------------- historique des cours (clôture du jour)
# Titres détenus aujourd'hui (achats − ventes > 0) : seuls leurs cours sont notés
TITRES_DETENUS = """SELECT titre FROM bourse_transactions GROUP BY titre
                    HAVING SUM(CASE WHEN type_operation = 'Achat' THEN quantite ELSE -quantite END) > 0"""

# Jours fériés à date fixe (mois, jour) : Bourse de Casablanca fermée. Les fêtes religieuses, à date
# variable, se saisissent dans Bourse → Paramètres (table bourse_jours_feries).
FERIES_FIXES = {
    (1, 1): "Nouvel an", (1, 11): "Manifeste de l'indépendance", (1, 14): "Nouvel an amazigh",
    (5, 1): "Fête du travail", (7, 30): "Fête du Trône", (8, 14): "Allégeance Oued Eddahab",
    (8, 20): "Révolution du Roi et du Peuple", (8, 21): "Fête de la jeunesse", (10, 31): "Fête de l'unité",
    (11, 6): "Marche verte", (11, 18): "Fête de l'indépendance",
}


def raison_fermeture(jour: date, feries: dict) -> Optional[str]:
    """Pourquoi la Bourse est fermée ce jour-là (week-end, jour férié), None si c'est un jour de
    bourse. `feries` : {date: libellé} des jours fériés à date variable."""
    if jour.weekday() >= 5:
        return "week-end"
    return FERIES_FIXES.get((jour.month, jour.day)) or feries.get(jour)


def _feries_variables(conn) -> dict:
    return {r["date"]: r["libelle"] or "jour férié"
            for r in conn.execute("SELECT date, libelle FROM bourse_jours_feries").fetchall()}


def noter_cours_du_jour(auj: date, recuperes: list) -> int:
    """Note la clôture du jour dans bourse_prix_historique, une ligne par titre détenu : son cours
    s'il vient d'être récupéré (`recuperes`), ou le cours saisi à la main s'il est en manuel. Un
    titre en automatique dont le cours n'a pas pu être récupéré n'est pas noté (pas d'ancien cours
    déguisé en clôture du jour). Rien un week-end ou un jour férié. Renvoie le nombre de cours notés."""
    with db() as conn:
        if raison_fermeture(auj, _feries_variables(conn)):
            return 0
        return conn.execute(
            f"""INSERT INTO bourse_prix_historique (titre, date, cours, manuel)
                SELECT p.titre, %s, p.cours_actuel, p.manuel FROM bourse_prix p
                WHERE p.cours_actuel > 0 AND p.titre IN ({TITRES_DETENUS}) AND (p.manuel OR p.titre = ANY(%s))
                ON CONFLICT (titre, date) DO UPDATE SET cours = EXCLUDED.cours, manuel = EXCLUDED.manuel, source = 'auto'""",
            (auj, list(recuperes)),
        ).rowcount


def cours_du_soir(auj: date) -> dict:
    """Tâche du soir (après la clôture) : récupère les cours, puis note la clôture du jour. Un
    week-end ou un jour férié, rien n'est fait."""
    with db() as conn:
        ferme = raison_fermeture(auj, _feries_variables(conn))
    if ferme:
        return {"etat": "ferme", "raison": ferme}
    resultat, recuperes = _recuperer_cours(force=True)
    notes = noter_cours_du_jour(auj, recuperes)
    return {"etat": resultat.etat, "notes": notes, "introuvables": resultat.introuvables, "message": resultat.message}


# ---------------------------------------------------------------- cours en retard
JOURS_RETARD_AUTO = 2      # clôtures manquées (jours de bourse) avant de prévenir, titre automatique
JOURS_RETARD_MANUEL = 5    # jours de bourse depuis un cours saisi à la main avant de prévenir


def jours_de_bourse_entre(debut: date, fin: date, feries: dict) -> int:
    """Nombre de jours de bourse de `debut` à `fin` inclus (0 si fin < debut)."""
    n, jour = 0, debut
    while jour <= fin:
        if not raison_fermeture(jour, feries):
            n += 1
        jour += timedelta(days=1)
    return n


def detecter_retards(titres: list, auj: date, feries: dict, debut_historique: Optional[date]) -> list:
    """Titres détenus dont le cours n'est plus à jour (fonction pure). `titres` : [{titre, manuel,
    maj_le (date), derniere_cloture (date|None), achete_le (date)}] ; `debut_historique` : premier jour
    noté dans l'historique (None : la tâche du soir n'a encore jamais tourné).

    - en manuel : saisi depuis plus de JOURS_RETARD_MANUEL jours de bourse ;
    - en automatique : au moins JOURS_RETARD_AUTO jours de bourse sans clôture notée, jusqu'à hier
      (la clôture d'aujourd'hui n'est notée que le soir). On ne compte qu'à partir du début de
      l'historique et de l'achat du titre : un titre acheté hier, ou l'historique tout juste lancé,
      ne sont pas en retard."""
    hier = auj - timedelta(days=1)
    retards = []
    for t in titres:
        if t["manuel"]:
            jours = jours_de_bourse_entre(t["maj_le"] + timedelta(days=1), auj, feries)
            if jours > JOURS_RETARD_MANUEL:
                retards.append({"titre": t["titre"], "manuel": True, "depuis": t["maj_le"], "jours": jours})
            continue
        if debut_historique is None:
            continue
        depuis = t["derniere_cloture"] or max(debut_historique, t["achete_le"]) - timedelta(days=1)
        jours = jours_de_bourse_entre(depuis + timedelta(days=1), hier, feries)
        if jours >= JOURS_RETARD_AUTO:
            retards.append({"titre": t["titre"], "manuel": False, "depuis": t["derniere_cloture"], "jours": jours})
    return sorted(retards, key=lambda r: (-r["jours"], r["titre"]))


def cours_en_retard(auj: date) -> list:
    """Titres détenus au cours périmé : [{titre, manuel, depuis, jours}] (cf. detecter_retards)."""
    with db() as conn:
        feries = _feries_variables(conn)
        debut = conn.execute("SELECT min(date) d FROM bourse_prix_historique").fetchone()["d"]
        rows = conn.execute(f"""
            SELECT d.titre, COALESCE(p.manuel, false) manuel, p.maj_le,
                   (SELECT max(h.date) FROM bourse_prix_historique h WHERE h.titre = d.titre) derniere_cloture,
                   (SELECT min(t.date_operation) FROM bourse_transactions t
                    WHERE t.titre = d.titre AND t.type_operation = 'Achat') achete_le
            FROM ({TITRES_DETENUS}) d LEFT JOIN bourse_prix p ON p.titre = d.titre""").fetchall()
    titres = [{**r, "maj_le": r["maj_le"].date() if r["maj_le"] else auj} for r in rows]
    return detecter_retards(titres, auj, feries, debut)


@router.get("/cours-en-retard")
def lire_cours_en_retard():
    return cours_en_retard(aujourdhui())


@router.get("/jours-feries")
def lister_jours_feries():
    """Jours fériés à date variable saisis (du plus récent au plus ancien) et ceux à date fixe."""
    with db() as conn:
        variables = conn.execute("SELECT date, libelle FROM bourse_jours_feries ORDER BY date DESC").fetchall()
    return {"variables": variables,
            "fixes": [{"mois": m, "jour": j, "libelle": l} for (m, j), l in sorted(FERIES_FIXES.items())]}


@router.post("/jours-feries", status_code=201)
def ajouter_jour_ferie(f: JourFerieIn):
    with db() as conn:
        conn.execute("""INSERT INTO bourse_jours_feries (date, libelle) VALUES (%s, %s)
                        ON CONFLICT (date) DO UPDATE SET libelle = EXCLUDED.libelle""", (f.date, f.libelle))
        # Un cours noté ce jour-là par erreur (jour férié saisi après coup) est retiré
        conn.execute("DELETE FROM bourse_prix_historique WHERE date = %s", (f.date,))
    return {"date": f.date, "libelle": f.libelle}


@router.delete("/jours-feries/{jour}", status_code=204)
def supprimer_jour_ferie(jour: date):
    with db() as conn:
        if conn.execute("DELETE FROM bourse_jours_feries WHERE date = %s", (jour,)).rowcount == 0:
            raise HTTPException(404, "Jour férié introuvable")


def valeur_aux_dates(transactions: list, cours: dict, jours: list) -> list:
    """Valeur de marché et coût (PRU × quantité) des titres détenus à la fin de chaque jour de
    `jours` (triés). `transactions` : [{date, titre, achat, quantite, net}] triées par date ;
    `cours` : {titre: [(date, cours)] triée}. Un titre sans cours relevé à cette date prend le
    prix de sa dernière transaction. Ne lit pas la base."""
    qte, cout, dernier_prix = {}, {}, {}
    points, i = [], 0
    for jour in jours:
        while i < len(transactions) and transactions[i]["date"] <= jour:
            t = transactions[i]
            q, n = qte.get(t["titre"], 0.0), t["quantite"]
            if t["achat"]:
                qte[t["titre"]], cout[t["titre"]] = q + n, cout.get(t["titre"], 0.0) + t["net"]
            else:
                pru = cout.get(t["titre"], 0.0) / q if q > 0 else 0.0
                qte[t["titre"]], cout[t["titre"]] = q - n, cout.get(t["titre"], 0.0) - pru * n
            dernier_prix[t["titre"]] = t["cours"]
            i += 1
        valeur = total_cout = 0.0
        for titre, q in qte.items():
            if q <= 1e-9:
                continue
            releves = [c for d, c in cours.get(titre, []) if d <= jour]
            valeur += q * (releves[-1] if releves else dernier_prix.get(titre, 0.0))
            total_cout += cout.get(titre, 0.0)
        points.append({"date": jour, "valeur": round(valeur, 2), "cout": round(total_cout, 2)})
    return points


@router.get("/historique")
def historique_cours(titre: Optional[str] = None, jours: Optional[int] = None):
    """Sans `titre` : valeur des titres détenus (et leur coût) chaque jour noté. Avec `titre` :
    les cours notés de ce titre. `jours` : seulement les N derniers jours."""
    depuis = aujourdhui() - timedelta(days=jours) if jours else date.min
    with db() as conn:
        if titre:
            rows = conn.execute("""SELECT date, cours, manuel, source FROM bourse_prix_historique
                                   WHERE titre = %s AND date > %s ORDER BY date""",
                                (titre.strip().upper(), depuis)).fetchall()
            return {"titre": titre.strip().upper(),
                    "points": [{"date": r["date"], "cours": float(r["cours"]), "manuel": r["manuel"],
                                "importe": r["source"] == "import"} for r in rows]}
        releves = conn.execute("SELECT titre, date, cours FROM bourse_prix_historique ORDER BY date").fetchall()
    _, _, calc = _positions_et_gains()
    # Pas de point avant le premier achat : des cours importés peuvent remonter plus loin
    premier_achat = min((t["date_operation"] for t in calc), default=date.max)
    dates = {r["date"] for r in releves if r["date"] > depuis and r["date"] >= premier_achat}
    titres = sorted({r["titre"] for r in releves})
    return {"titres": titres, "points": valeur_aux_dates(_transactions_courbe(calc), _cours_notes(releves), sorted(dates))}


def _cours_notes(releves: list) -> dict:
    """{titre: [(date, cours)] triée} à partir des lignes de bourse_prix_historique triées par date."""
    cours = {}
    for r in releves:
        cours.setdefault(r["titre"], []).append((r["date"], float(r["cours"])))
    return cours


def _transactions_courbe(calc: list) -> list:
    return [{"date": t["date_operation"], "titre": t["titre"], "achat": t["type_operation"] == "Achat",
             "quantite": float(t["quantite"]), "net": float(t["_net_decimal"]), "cours": float(t["cours_unitaire"])}
            for t in calc]


def valeur_marche_aux_dates(jours: list) -> list:
    """Valeur de marché des titres détenus à la fin de chaque jour de `jours` (triés), au dernier
    cours noté ou importé, sinon au prix de leur dernière transaction."""
    with db() as conn:
        releves = conn.execute("SELECT titre, date, cours FROM bourse_prix_historique ORDER BY date").fetchall()
    _, _, calc = _positions_et_gains()
    return [p["valeur"] for p in valeur_aux_dates(_transactions_courbe(calc), _cours_notes(releves), jours)]


def flux_titres() -> list:
    """L'argent qui entre dans les titres et qui en sort, vu des titres : [(date, montant)], achat
    positif (prix net, frais compris), vente négative (montant crédité, TPCVM retenue) et dividende
    négatif (net reçu). Sert à comparer le seul choix des titres à l'indice : les espèces du compte
    et les frais de tenue de compte n'y entrent pas."""
    _, gains, calc = _positions_et_gains()
    tpcvm = {g.id: float(g.tpcvm) for g in gains}
    flux = [(t["date_operation"], float(t["_net_decimal"]) if t["type_operation"] == "Achat"
             else -(float(t["_net_decimal"]) - tpcvm.get(t["id"], 0.0))) for t in calc]
    flux += [(x["date_operation"], -float(x["montant"])) for x in _dividendes()]
    return flux


# ---------------------------------------------------------------- cours passés importés
ECART_IMPORT_COURS_MAX = 0.10    # au-delà, le fichier est sans doute celui d'un autre titre


def premier_ecart(importees: dict, notees: dict, seuil: float) -> Optional[tuple]:
    """Première date commune où une valeur importée s'écarte de plus de `seuil` (part) de la valeur
    déjà notée le soir : (date, importée, notée), None sinon. Sert à refuser un fichier qui n'est pas
    celui du titre (ou de l'indice) choisi."""
    for d in sorted(set(importees) & set(notees)):
        if abs(importees[d] - notees[d]) > seuil * notees[d]:
            return d, importees[d], notees[d]
    return None


def _nombre_fr(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


@router.get("/historique/couverture")
def couverture_historique():
    """Pour chaque titre déjà acheté : les cours connus (notés le soir ou importés) et la date du
    premier achat, que l'import doit couvrir pour une courbe juste depuis le début."""
    with db() as conn:
        rows = conn.execute(f"""
            SELECT t.titre, MIN(t.date_operation) premier_achat, t.titre IN ({TITRES_DETENUS}) detenu,
                   h.nb, h.nb_import, h.debut, h.fin
            FROM bourse_transactions t
            LEFT JOIN (SELECT titre, COUNT(*) nb, COUNT(*) FILTER (WHERE source = 'import') nb_import,
                              MIN(date) debut, MAX(date) fin
                       FROM bourse_prix_historique GROUP BY titre) h ON h.titre = t.titre
            GROUP BY t.titre, h.nb, h.nb_import, h.debut, h.fin
            ORDER BY detenu DESC, t.titre""").fetchall()
    return [{**r, "nb": r["nb"] or 0, "nb_import": r["nb_import"] or 0} for r in rows]


@router.post("/historique/{titre}/import")
def importer_cours_passes(titre: str, i: ImportIndiceIn):
    """Cours de clôture passés d'un titre (fichier « Market Data → Cours » de la Bourse de Casablanca).
    Une clôture notée le soir est gardée ; si le fichier s'en écarte de plus de 10 % un même jour,
    c'est sans doute le fichier d'un autre titre : tout est refusé."""
    titre = titre.strip().upper()
    auj = aujourdhui()
    importees = {v.date: v.valeur for v in i.valeurs if v.date <= auj}
    if not importees:
        raise HTTPException(400, "Aucun cours daté d'aujourd'hui ou avant")
    with references_valides(), db() as conn:
        if not conn.execute("SELECT 1 FROM bourse_titres WHERE code = %s", (titre,)).fetchone():
            raise HTTPException(404, f"Titre inconnu : {titre}")
        notees = {r["date"]: float(r["cours"]) for r in conn.execute(
            "SELECT date, cours FROM bourse_prix_historique WHERE titre = %s AND source = 'auto'", (titre,)).fetchall()}
        ecart = premier_ecart(importees, notees, ECART_IMPORT_COURS_MAX)
        if ecart:
            d, importee, notee = ecart
            raise HTTPException(400, f"Le {d.strftime('%d/%m/%Y')}, le fichier donne {_nombre_fr(importee)} mais la clôture "
                                     f"notée de {titre} était {_nombre_fr(notee)} : ce fichier n'est sans doute pas celui de ce titre.")
        nouvelles = {d: v for d, v in importees.items() if d not in notees}
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO bourse_prix_historique (titre, date, cours, manuel, source)
                               VALUES (%s, %s, %s, false, 'import')
                               ON CONFLICT (titre, date) DO UPDATE SET cours = EXCLUDED.cours
                               WHERE bourse_prix_historique.source = 'import'""",
                            [(titre, d, v) for d, v in nouvelles.items()])
    return {"importees": len(nouvelles), "deja_notees": len(importees) - len(nouvelles),
            "debut": min(importees), "fin": max(importees)}


@router.delete("/historique/{titre}/import", status_code=204)
def supprimer_cours_importes(titre: str):
    """Retire les cours importés d'un titre (mauvais fichier) ; les clôtures notées le soir restent."""
    with db() as conn:
        conn.execute("DELETE FROM bourse_prix_historique WHERE titre = %s AND source = 'import'", (titre.strip().upper(),))


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


def quantite_detenue_le(mouvements: list, titre: str, jour) -> Decimal:
    """Quantité d'un titre détenue à la fin du jour `jour`, d'après les achats et ventes."""
    return sum(((_d(m["quantite"]) if m["type_operation"] == "Achat" else -_d(m["quantite"]))
                for m in mouvements if m["titre"] == titre and m["date_operation"] <= jour), Decimal(0))


def dividendes_par_action(auj) -> list:
    """Dividendes reçus sur les 12 derniers mois, avec le dividende PAR ACTION : montant reçu ÷
    quantité détenue le jour du versement. `par_action` vaut None si la quantité de ce jour-là
    est nulle (dividende saisi sans achat correspondant). Sert au rendement des positions et
    aux dividendes attendus, qui doivent ramener chaque versement à la quantité détenue
    AUJOURD'HUI : après une vente partielle, le dividende total reçu surestimerait la position."""
    with db() as conn:
        dividendes = conn.execute(
            "SELECT titre, date_operation, montant FROM bourse_dividendes WHERE date_operation > %s AND date_operation <= %s",
            (auj - timedelta(days=365), auj)).fetchall()
        mouvements = conn.execute(
            "SELECT titre, date_operation, type_operation, quantite FROM bourse_transactions").fetchall()
    resultat = []
    for d in dividendes:
        qte = quantite_detenue_le(mouvements, d["titre"], d["date_operation"])
        resultat.append({**d, "par_action": _d(d["montant"]) / qte if qte > 0 else None})
    return resultat


def calculer_calendrier_dividendes(auj) -> dict:
    """Dividendes attendus sur les 12 mois à venir : chaque dividende reçu depuis un an sur un
    titre encore détenu est supposé revenir un an plus tard, au même montant PAR ACTION, sur la
    quantité détenue aujourd'hui. C'est une estimation : la société peut changer son dividende."""
    positions, _, _ = _positions_et_gains()
    detenues = {p.titre: _d(p.quantite_detenue) for p in positions if p.quantite_detenue > 0}
    with db() as conn:
        noms = {r["code"]: r["nom"] for r in conn.execute("SELECT code, nom FROM bourse_titres").fetchall()}

    lignes = []
    for d in dividendes_par_action(auj):
        if d["titre"] not in detenues or d["par_action"] is None:
            continue
        par_action = d["par_action"]
        lignes.append({
            "titre": d["titre"], "nom": noms.get(d["titre"], ""),
            "date_prevue": ajouter_mois(d["date_operation"], 12),
            "montant_prevu": _r(par_action * detenues[d["titre"]]), "par_action": _r4(par_action),
            "quantite": _r(detenues[d["titre"]]),
            "dernier_montant": _r(d["montant"]), "derniere_date": d["date_operation"],
        })
    lignes.sort(key=lambda l: (l["date_prevue"], l["titre"]))
    return {"total": round(sum(l["montant_prevu"] for l in lignes), 2), "lignes": lignes}


@router.get("/dividendes/calendrier")
def calendrier_dividendes():
    return calculer_calendrier_dividendes(aujourdhui())


def _valider_dividende(conn, titre: str, date_operation):
    """Un dividende n'est versé que sur un titre acheté au plus tard à cette date."""
    if not conn.execute(
        "SELECT 1 FROM bourse_transactions WHERE titre = %s AND type_operation = 'Achat' AND date_operation <= %s LIMIT 1",
        (titre, date_operation),
    ).fetchone():
        raise HTTPException(400, f"Aucun achat de « {titre} » à cette date ou avant : vérifie le titre et la date.")


@router.post("/dividendes", response_model=DividendeOut, status_code=201)
def creer_dividende(d: DividendeCreate):
    titre = d.titre.strip().upper()
    with references_valides(), db() as conn:
        _valider_dividende(conn, titre, d.date_operation)
        row = conn.execute(
            f"""INSERT INTO bourse_dividendes (date_operation, titre, montant)
                VALUES (%s,%s,%s)
                RETURNING {DIV_COLONNES}""",
            (d.date_operation, titre, d.montant),
        ).fetchone()
    return {**dict(row), "montant": _r(row["montant"])}


@router.put("/dividendes/{dividende_id}", response_model=DividendeOut)
def modifier_dividende(dividende_id: int, d: DividendeCreate):
    titre = d.titre.strip().upper()
    with references_valides(), db() as conn:
        _valider_dividende(conn, titre, d.date_operation)
        row = conn.execute(
            f"UPDATE bourse_dividendes SET date_operation=%s, titre=%s, montant=%s WHERE id=%s RETURNING {DIV_COLONNES}",
            (d.date_operation, titre, d.montant, dividende_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Dividende introuvable")
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


@router.put("/frais/{frais_id}", response_model=FraisBourseOut)
def modifier_frais(frais_id: int, f: FraisBourseCreate):
    with db() as conn:
        row = conn.execute(
            f"UPDATE bourse_frais SET date_operation=%s, libelle=%s, montant=%s WHERE id=%s RETURNING {FRAIS_COLONNES}",
            (f.date_operation, f.libelle.strip(), f.montant, frais_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Frais introuvable")
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


@router.put("/mouvements/{mouvement_id}", response_model=MouvementBourseOut)
def modifier_mouvement(mouvement_id: int, m: MouvementBourseCreate):
    with db() as conn:
        row = conn.execute(
            f"""UPDATE bourse_mouvements SET date_operation=%s, type_mouvement=%s, montant=%s, libelle=%s
                WHERE id=%s RETURNING {MVT_COLONNES}""",
            (m.date_operation, m.type_mouvement, m.montant, m.libelle.strip(), mouvement_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Mouvement introuvable")
    return {**dict(row), "montant": _r(row["montant"])}


@router.delete("/mouvements/{mouvement_id}", status_code=204)
def supprimer_mouvement(mouvement_id: int):
    with db() as conn:
        res = conn.execute("DELETE FROM bourse_mouvements WHERE id = %s", (mouvement_id,))
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mouvement introuvable")


# ---------------------------------------------------------------- calcul positions / gains (logique commune)
def _positions_et_gains():
    """Coût moyen pondéré (mobile) par titre + gain/perte par vente (TPCVM saisie).

    Chaque titre est traité indépendamment, dans l'ordre chronologique de SES
    transactions : le PRU courant sert à calculer le gain d'une vente, puis le
    coût restant est réduit de `pru_courant × quantité vendue`. Un achat
    ultérieur ne doit jamais influencer le PRU utilisé pour une vente qui a eu
    lieu avant lui (contrairement à une simple moyenne pondérée sur tout
    l'historique, qui mélangerait les cycles achat→vente→rachat).

    La TPCVM de chaque vente est celle saisie sur la transaction. Seules les ventes
    antérieures à cette saisie (tpcvm NULL) utilisent encore l'ancien calcul
    (taux_tpcvm × gain brut si positif), le temps que remplir_tpcvm_manquantes()
    enregistre cette valeur en base au démarrage."""
    with db() as conn:
        params = _parametres_dict(conn)
        txs = [dict(r) for r in conn.execute(
            f"SELECT {TX_COLONNES} FROM bourse_transactions ORDER BY date_operation ASC, id ASC"
        ).fetchall()]
        # maj_le est stocké sans fuseau (heure de la session) : renvoyé avec fuseau pour un affichage juste
        prix_rows = {r["titre"]: r for r in conn.execute(
            "SELECT titre, cours_actuel, manuel, maj_le AT TIME ZONE current_setting('TimeZone') AS maj_le FROM bourse_prix"
        ).fetchall()}
        prix = {titre: _d(r["cours_actuel"]) for titre, r in prix_rows.items()}
        titres_rows = conn.execute("SELECT code, secteur, isin FROM bourse_titres").fetchall()
        secteurs = {r["code"]: r["secteur"] for r in titres_rows}
        isins = {r["code"]: r["isin"] for r in titres_rows}
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
                if t["_tpcvm_saisie"] is not None:
                    tpcvm = _d(t["_tpcvm_saisie"])
                else:
                    tpcvm = gain_brut * tpcvm_rate if gain_brut > 0 else Decimal(0)
                taux_effectif = tpcvm / gain_brut if gain_brut > 0 else Decimal(0)
                gain_net = gain_brut - tpcvm
                gains.append(GainRealise(
                    id=t["id"], date_operation=t["date_operation"], titre=titre, type_instrument=t["type_instrument"],
                    quantite=_r(qte), cours_vente=_r(_d(t["cours_unitaire"])), pru=_r(pru_courant), montant_net=_r(net),
                    gain_brut=_r(gain_brut), taux_tpcvm=_r4(taux_effectif), tpcvm=_r(tpcvm), gain_net=_r(gain_net),
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
            isin=isins.get(titre),
            cours_manuel=bool(prix_rows[titre]["manuel"]) if titre in prix_rows else False,
            cours_maj_le=prix_rows[titre]["maj_le"] if titre in prix_rows else None,
        ))

    return positions, gains, calc


def remplir_tpcvm_manquantes():
    """Migration ponctuelle, appelée au démarrage : enregistre sur chaque vente ancienne
    (tpcvm NULL) la TPCVM que l'application calculait jusque-là, pour que les totaux
    restent identiques. Sans effet une fois toutes les ventes remplies."""
    with db() as conn:
        if not conn.execute("SELECT 1 FROM bourse_transactions "
                            "WHERE type_operation = 'Vente' AND tpcvm IS NULL LIMIT 1").fetchone():
            return
    _, gains, calc = _positions_et_gains()
    manquantes = {t["id"] for t in calc if t["type_operation"] == "Vente" and t["_tpcvm_saisie"] is None}
    with db() as conn:
        for g in gains:
            if g.id in manquantes:
                conn.execute("UPDATE bourse_transactions SET tpcvm = %s WHERE id = %s", (g.tpcvm, g.id))


@router.get("/positions", response_model=List[PositionBourse])
def obtenir_positions():
    return calculer_positions(aujourdhui())


def calculer_positions(auj) -> List[PositionBourse]:
    """Positions + rendement des dividendes. Les dividendes des 12 derniers mois sont ramenés à la
    quantité détenue aujourd'hui (dividende par action × quantité actuelle), puis rapportés au coût
    (valeur comptable) et à la valeur de marché de la position. Sans cela, une vente partielle
    gonflerait le rendement : le dividende avait été versé sur plus d'actions."""
    positions, _, _ = _positions_et_gains()
    detenues = {p.titre: _d(p.quantite_detenue) for p in positions}
    div = {}
    for d in dividendes_par_action(auj):
        # Quantité inconnue le jour du versement : le montant reçu, faute de mieux
        montant = d["par_action"] * detenues.get(d["titre"], Decimal(0)) if d["par_action"] is not None else _d(d["montant"])
        div[d["titre"]] = div.get(d["titre"], Decimal(0)) + montant
    for p in positions:
        d = div.get(p.titre, Decimal(0))
        p.dividendes_12m = _r(d)
        p.rendement_cout = _r4(d / _d(p.valeur_comptable)) if p.valeur_comptable > 0 else 0
        p.rendement_marche = _r4(d / _d(p.valeur_marche)) if p.valeur_marche > 0 else 0
    return positions


# ---------------------------------------------------------------- allocation cible par secteur
@router.get("/cibles")
def lister_cibles():
    with db() as conn:
        return [{"secteur": r["secteur"], "cible": float(r["cible"])}
                for r in conn.execute("SELECT secteur, cible FROM bourse_cibles_secteur ORDER BY secteur").fetchall()]


@router.put("/cibles")
def remplacer_cibles(c: CiblesIn):
    """Remplace toutes les cibles (une cible à 0 est simplement retirée)."""
    with db() as conn:
        conn.execute("DELETE FROM bourse_cibles_secteur")
        for x in c.cibles:
            if x.cible > 0:
                conn.execute("INSERT INTO bourse_cibles_secteur(secteur, cible) VALUES(%s,%s)", (x.secteur.strip(), x.cible))
    return lister_cibles()


# ---------------------------------------------------------------- allocation cible par titre
@router.get("/cibles-titres")
def lister_cibles_titres():
    with db() as conn:
        return [{"titre": r["titre"], "cible": float(r["cible"])}
                for r in conn.execute("SELECT titre, cible FROM bourse_cibles_titre ORDER BY titre").fetchall()]


@router.put("/cibles-titres")
def remplacer_cibles_titres(c: CiblesTitresIn):
    """Remplace toutes les cibles par titre (une cible à 0 est simplement retirée)."""
    with references_valides(), db() as conn:
        conn.execute("DELETE FROM bourse_cibles_titre")
        for x in c.cibles:
            if x.cible > 0:
                conn.execute("INSERT INTO bourse_cibles_titre(titre, cible) VALUES(%s,%s)", (x.titre.strip().upper(), x.cible))
    return lister_cibles_titres()


# ---------------------------------------------------------------- récapitulatif fiscal
@router.get("/fiscalite")
def recapitulatif_fiscal(annee: int):
    """Pour la déclaration de l'année : ventes (plus et moins-values brutes, TPCVM retenue),
    dividendes nets reçus, et détail par titre. La TPCVM « théorique » applique le taux des
    paramètres au résultat net de cession (gains − pertes de l'année) : un simple repère pour
    vérifier les retenues, pas un calcul fiscal officiel."""
    _, gains, _ = _positions_et_gains()
    ventes = [g for g in gains if g.date_operation.year == annee]
    with db() as conn:
        taux = _d(_parametres_dict(conn)["taux_tpcvm"])
        div = conn.execute(
            "SELECT titre, SUM(montant) t, COUNT(*) n FROM bourse_dividendes WHERE date_operation >= %s AND date_operation < %s GROUP BY titre",
            (f"{annee}-01-01", f"{annee + 1}-01-01"),
        ).fetchall()
        frais = conn.execute(
            "SELECT COALESCE(SUM(montant),0) t FROM bourse_frais WHERE date_operation >= %s AND date_operation < %s",
            (f"{annee}-01-01", f"{annee + 1}-01-01"),
        ).fetchone()["t"]

    plus_values = sum(_d(g.gain_brut) for g in ventes if g.gain_brut > 0)
    moins_values = sum(_d(g.gain_brut) for g in ventes if g.gain_brut < 0)
    resultat = plus_values + moins_values
    tpcvm = sum(_d(g.tpcvm) for g in ventes)
    theorique = resultat * taux if resultat > 0 else Decimal(0)

    par_titre = {}
    for g in ventes:
        t = par_titre.setdefault(g.titre, {"titre": g.titre, "nb_ventes": 0, "cessions": Decimal(0),
                                           "gain_brut": Decimal(0), "tpcvm": Decimal(0), "dividendes": Decimal(0)})
        t["nb_ventes"] += 1
        t["cessions"] += _d(g.montant_net)
        t["gain_brut"] += _d(g.gain_brut)
        t["tpcvm"] += _d(g.tpcvm)
    for r in div:
        par_titre.setdefault(r["titre"], {"titre": r["titre"], "nb_ventes": 0, "cessions": Decimal(0),
                                          "gain_brut": Decimal(0), "tpcvm": Decimal(0), "dividendes": Decimal(0)})
        par_titre[r["titre"]]["dividendes"] += _d(r["t"])

    return {
        "annee": annee,
        "nb_ventes": len(ventes),
        "montant_cessions": _r(sum(_d(g.montant_net) for g in ventes)),
        "plus_values_brutes": _r(plus_values),
        "moins_values_brutes": _r(moins_values),
        "resultat_cessions": _r(resultat),
        "tpcvm_retenue": _r(tpcvm),
        "taux_tpcvm": float(taux),
        "tpcvm_theorique": _r(theorique),
        "ecart_tpcvm": _r(tpcvm - theorique),
        "dividendes_nets": _r(sum(_d(r["t"]) for r in div)),
        "frais_compte": _r(frais),
        "par_titre": sorted(({**t, "cessions": _r(t["cessions"]), "gain_brut": _r(t["gain_brut"]),
                              "tpcvm": _r(t["tpcvm"]), "dividendes": _r(t["dividendes"])} for t in par_titre.values()),
                            key=lambda t: t["titre"]),
    }


@router.get("/gains", response_model=List[GainRealise])
def obtenir_gains(mois: Optional[str] = None, annee: Optional[int] = None):
    _valider_periode(mois, annee)
    _, gains, _ = _positions_et_gains()
    gains = [g for g in gains if _dans_periode(g.date_operation, mois, annee)]
    return sorted(gains, key=lambda g: g.date_operation, reverse=True)


# ---------------------------------------------------------------- rendement annualisé (TRI / XIRR)
# En dessous, un rendement « par an » extrapolé de quelques semaines n'aurait pas de sens
# (+3 % en un mois afficherait +42 % par an)
JOURS_MIN_RENDEMENT_ANNUALISE = 90


def taux_rendement_annualise(flux: list, auj) -> Optional[float]:
    """Taux annuel r tel que Σ montant / (1 + r)^(jours écoulés / 365) = 0 : le taux de rendement
    interne (XIRR des tableurs), qui tient compte de la DATE de chaque apport. `flux` : liste de
    (date, montant) vue de ta poche : apport négatif, retrait positif, et la valeur du compte
    aujourd'hui comptée comme un retrait final. None sans apport, sans valeur positive, ou si le
    premier flux date de moins de JOURS_MIN_RENDEMENT_ANNUALISE jours.

    Résolu par dichotomie : la valeur actuelle nette décroît avec r tant que les apports précèdent
    les retraits, ce qui est le cas d'un compte Bourse ; elle est plus lente que Newton mais ne
    diverge jamais."""
    flux = [(d, float(m)) for d, m in flux if m]
    if not any(m < 0 for _, m in flux) or not any(m > 0 for _, m in flux):
        return None
    debut = min(d for d, _ in flux)
    if (auj - debut).days < JOURS_MIN_RENDEMENT_ANNUALISE:
        return None

    def vna(r: float) -> float:
        return sum(m / (1 + r) ** ((d - debut).days / 365) for d, m in flux)

    bas, haut = -0.99, 1.0
    while vna(haut) > 0 and haut < 1e6:
        haut *= 2
    v_bas = vna(bas)
    if v_bas * vna(haut) > 0:
        return None            # pas de changement de signe : aucun taux ne convient
    for _ in range(200):
        milieu = (bas + haut) / 2
        v = vna(milieu)
        if v_bas * v <= 0:
            haut = milieu
        else:
            bas, v_bas = milieu, v
        if haut - bas < 1e-9:
            break
    return (bas + haut) / 2


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
    # Même performance, mais par an et pondérée par la date des apports et retraits
    flux = [(m["date_operation"], -_d(m["montant"]) if m["type_mouvement"] == "Apport" else _d(m["montant"]))
            for m in mouvements]
    rendement_annualise = taux_rendement_annualise(flux + [(aujourdhui(), patrimoine)], aujourdhui())

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
        rendement_annualise=_r4(rendement_annualise) if rendement_annualise is not None else None,
    )
