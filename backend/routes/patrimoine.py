# -*- coding: utf-8 -*-
"""
Patrimoine net — ce que je possède, tous modules confondus.

    liquidités    = solde de départ + épargne cumulée du Budget
                    − apports nets au compte Bourse − argent versé dans les autres actifs
                    − argent prêté + argent emprunté
    patrimoine    = liquidités + compte Bourse + autres actifs + ce qu'on me doit − ce que je dois

Les autres actifs (or, compte épargne, immobilier...) ont une valeur saisie à la main. Trois
indicateurs en découlent : la réserve de sécurité (mois de dépenses couverts par l'argent
disponible), une estimation de la zakat (assiette comparée au nisab, échéance du hawl) et la
liberté financière (patrimoine comparé à 25 × les dépenses annuelles, date estimée pour l'atteindre).

Pointage du solde (rapprochements) : les liquidités sont calculées, jamais saisies. Pointer, c'est
taper le solde réel (banque, espèces) pour voir l'écart : une dépense oubliée s'y voit. L'écart peut
être enregistré en dépense (ou en revenu) datée du jour, pour que la suite reparte juste.

La courbe d'évolution (patrimoine_historique) reçoit un point par jour depuis sa mise en place. Les
mois d'avant peuvent être reconstitués (un point par fin de mois, marqué `estime`) à partir des
opérations datées ; chaque titre y prend son dernier cours connu (cours saisi à la main pour cette
date, sinon cours noté ce jour-là dans bourse_prix_historique, sinon prix de la dernière transaction).
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from config import aujourdhui
from database import db, references_valides
from securite import utilisateur_courant
from schemas import ActifIn, CoursPassesIn, RapprochementIn, ReglagesPatrimoine
from routes import bourse
from routes.carnet import lire_dettes

router = APIRouter(prefix="/api/patrimoine", tags=["patrimoine"],
                   dependencies=[Depends(utilisateur_courant)])

# Proposés par le formulaire (le type reste un texte libre en base). `zakat` : coché par défaut.
TYPES_ACTIFS = [
    {"type": "Compte épargne", "zakat": True}, {"type": "Or / argent", "zakat": True},
    {"type": "OPCVM / placement", "zakat": True}, {"type": "Crypto", "zakat": True},
    {"type": "Immobilier", "zakat": False}, {"type": "Véhicule", "zakat": False}, {"type": "Autre", "zakat": False},
]
# Argent disponible tout de suite en cas de coup dur : compte dans la réserve de sécurité
TYPE_DISPONIBLE = "Compte épargne"
MOIS_RESERVE = 12          # dépense moyenne calculée sur les derniers mois terminés
NISAB_GRAMMES_OR = 85     # seuil de la zakat : valeur de 85 g d'or
TAUX_ZAKAT = 0.025
JOURS_HAWL = 354          # une année lunaire
# Liberté financière : le logement et la voiture ne produisent pas de quoi vivre
TYPES_HORS_LIBERTE = ("Immobilier", "Véhicule")
MOIS_LIBERTE = 12         # 12 mois : l'Aïd, l'été et la rentrée scolaire sont compris
TAUX_RETRAIT_DEFAUT = 0.04
RENDEMENT_DEFAUT = 0.04
ECONOMIE_SIMULEE = 500    # « et si tu dépensais 500 DH de moins par mois ? »
MOIS_MAX = 100 * 12

ACTIF_COLONNES = "id, nom, type, valeur, verse, zakat, maj_le, note"
PARAMS = ("solde_depart", "zakat_prix_or", "zakat_debut_hawl", "liberte_taux_retrait", "liberte_rendement")


def _params(c) -> dict:
    rows = c.execute("SELECT cle, valeur FROM params WHERE cle = ANY(%s)", (list(PARAMS),)).fetchall()
    return {r["cle"]: r["valeur"] for r in rows}


def depense_moyenne(c, auj: date) -> tuple:
    """(dépense mensuelle moyenne, nombre de mois) sur les derniers mois TERMINÉS ayant des dépenses."""
    rows = c.execute("""SELECT SUM(montant) t FROM depenses WHERE substr(date,1,7) < %s
                        GROUP BY substr(date,1,7) ORDER BY substr(date,1,7) DESC LIMIT %s""",
                     (auj.strftime("%Y-%m"), MOIS_RESERVE)).fetchall()
    return (sum(r["t"] for r in rows) / len(rows), len(rows)) if rows else (0.0, 0)


def moyennes_annuelles(c, auj: date) -> tuple:
    """(dépenses par mois, épargne par mois, nombre de mois) sur les derniers mois TERMINÉS ayant des dépenses."""
    rows = c.execute("""WITH mois AS (SELECT substr(date,1,7) m, SUM(montant) dep FROM depenses
                                      WHERE substr(date,1,7) < %s GROUP BY 1 ORDER BY 1 DESC LIMIT %s)
                        SELECT m, dep, (SELECT COALESCE(SUM(montant),0) FROM revenus WHERE substr(date,1,7) = m) rev
                        FROM mois""", (auj.strftime("%Y-%m"), MOIS_LIBERTE)).fetchall()
    if not rows:
        return 0.0, 0.0, 0
    return sum(r["dep"] for r in rows) / len(rows), sum(r["rev"] - r["dep"] for r in rows) / len(rows), len(rows)


def mois_avant_liberte(patrimoine: float, epargne_mois: float, cible: float, rendement: float) -> Optional[int]:
    """Mois avant que le patrimoine atteigne la cible : chaque mois, il rapporte (rendement annuel
    composé) et reçoit l'épargne du mois. None si la cible n'est pas atteinte en 100 ans."""
    taux = (1 + rendement) ** (1 / 12) - 1
    for mois in range(MOIS_MAX + 1):
        if patrimoine >= cible:
            return mois
        patrimoine = patrimoine * (1 + taux) + epargne_mois
    return None


def liberte_financiere(patrimoine: float, depense_mois: float, epargne_mois: float,
                       taux_retrait: float, rendement: float, auj: date) -> dict:
    """Objectif = dépenses annuelles ÷ taux de retrait (4 % → 25 ×). Épargner plus compte deux fois :
    le patrimoine grossit plus vite ET l'objectif baisse, d'où la simulation « 500 DH de moins »."""
    annuelle = depense_mois * 12
    cible = annuelle / taux_retrait
    mois = mois_avant_liberte(patrimoine, epargne_mois, cible, rendement)
    simule = mois_avant_liberte(patrimoine, epargne_mois + ECONOMIE_SIMULEE,
                                (depense_mois - ECONOMIE_SIMULEE) * 12 / taux_retrait, rendement) \
        if depense_mois > ECONOMIE_SIMULEE else None
    return {
        "depense_annuelle": round(annuelle, 2), "epargne_annuelle": round(epargne_mois * 12, 2),
        "cible": round(cible, 2), "progression": round(max(patrimoine, 0) / cible, 4),
        "annees_couvertes": round(max(patrimoine, 0) / annuelle, 1),
        "annees_restantes": round(mois / 12, 1) if mois is not None else None,
        "date_atteinte": date(auj.year + (auj.month - 1 + mois) // 12, (auj.month - 1 + mois) % 12 + 1, 1) if mois is not None else None,
        "economie_simulee": ECONOMIE_SIMULEE,
        "annees_gagnees": round((mois - simule) / 12, 1) if mois is not None and simule is not None else None,
    }


def calculer_patrimoine(auj: date) -> dict:
    with db() as c:
        epargne = c.execute("""SELECT (SELECT COALESCE(SUM(montant),0) FROM revenus)
                                    - (SELECT COALESCE(SUM(montant),0) FROM depenses) t""").fetchone()["t"]
        actifs = c.execute(f"SELECT {ACTIF_COLONNES} FROM actifs ORDER BY valeur DESC, id").fetchall()
        dettes = [d for d in lire_dettes(c) if d["reste"] > 0]
        params = _params(c)
        moyenne, nb_mois = depense_moyenne(c, auj)
        depense_an, epargne_an, nb_mois_an = moyennes_annuelles(c, auj)
        pointage = dernier_pointage(c, auj)
    try:
        compte = bourse.obtenir_dashboard()
        apports, compte_bourse = compte.apports_nets, compte.patrimoine_total
    except Exception as e:   # un souci Bourse ne doit pas masquer le reste du patrimoine
        print(f"[patrimoine] Bourse ignorée — {e!r}", flush=True)
        apports = compte_bourse = 0.0

    for a in actifs:
        a["valeur"], a["verse"] = float(a["valeur"]), float(a["verse"])
    on_me_doit = float(sum((d["reste"] for d in dettes if d["sens"] == "pret"), Decimal(0)))
    je_dois = float(sum((d["reste"] for d in dettes if d["sens"] == "emprunt"), Decimal(0)))
    solde_depart = params.get("solde_depart", 0.0)
    verse = sum(a["verse"] for a in actifs)
    autres = sum(a["valeur"] for a in actifs)
    liquidites = solde_depart + epargne - apports - verse - on_me_doit + je_dois
    total = liquidites + compte_bourse + autres + on_me_doit - je_dois

    # Réserve de sécurité : combien de mois de dépenses l'argent disponible couvre
    disponible = max(liquidites, 0) + sum(a["valeur"] for a in actifs if a["type"] == TYPE_DISPONIBLE)
    reserve = {"disponible": round(disponible, 2), "depense_moyenne": round(moyenne, 2), "nb_mois_base": nb_mois,
               "mois_couverts": round(disponible / moyenne, 1) if moyenne > 0 else None}

    # Zakat : estimation. Assiette = argent, compte Bourse à sa valeur de marché, actifs cochés,
    # ce qu'on me doit, moins ce que je dois.
    prix_or = params.get("zakat_prix_or", 0.0)
    detail = {"liquidites": round(max(liquidites, 0), 2), "bourse": round(max(compte_bourse, 0), 2),
              "actifs": round(sum(a["valeur"] for a in actifs if a["zakat"]), 2),
              "creances": round(on_me_doit, 2), "dettes": round(je_dois, 2)}
    assiette = max(0.0, detail["liquidites"] + detail["bourse"] + detail["actifs"] + detail["creances"] - detail["dettes"])
    nisab = round(NISAB_GRAMMES_OR * prix_or, 2) if prix_or > 0 else None
    atteint = nisab is not None and assiette >= nisab
    debut = date.fromordinal(int(params["zakat_debut_hawl"])) if params.get("zakat_debut_hawl") else None
    echeance = debut + timedelta(days=JOURS_HAWL) if debut else None
    zakat = {"prix_or_gramme": prix_or, "nisab": nisab, "assiette": round(assiette, 2), "detail": detail,
             "atteint": atteint, "montant": round(assiette * TAUX_ZAKAT, 2) if atteint else 0.0,
             "debut_hawl": debut, "echeance": echeance,
             "jours_restants": (echeance - auj).days if echeance else None}

    # Liberté financière : patrimoine sans le logement ni la voiture
    exclus = sum(a["valeur"] for a in actifs if a["type"] in TYPES_HORS_LIBERTE)
    taux_retrait = params.get("liberte_taux_retrait", TAUX_RETRAIT_DEFAUT)
    rendement = params.get("liberte_rendement", RENDEMENT_DEFAUT)
    liberte = {"taux_retrait": taux_retrait, "rendement": rendement, "patrimoine": round(total - exclus, 2),
               "exclus": round(exclus, 2), "nb_mois_base": nb_mois_an}
    if depense_an > 0:
        liberte |= liberte_financiere(total - exclus, depense_an, epargne_an, taux_retrait, rendement, auj)

    return {"solde_depart": solde_depart, "epargne_cumulee": round(epargne, 2),
            "liquidites": round(liquidites, 2), "bourse": round(compte_bourse, 2),
            "autres_actifs": round(autres, 2), "creances": round(on_me_doit, 2), "dettes": round(je_dois, 2),
            "total": round(total, 2), "actifs": actifs, "types_actifs": TYPES_ACTIFS,
            "reserve": reserve, "zakat": zakat, "liberte": liberte, "pointage": pointage}


# ---------------------------------------------------------------- pointage du solde
POINTAGE_A_REFAIRE_JOURS = 30   # au-delà, l'accueil et le message du lundi invitent à pointer
JOURS_SANS_DEPENSE_MAX = 62     # période examinée pour repérer les jours sans aucune dépense
LIBELLE_ECART = "Écart de pointage du solde"
TAG_ECART = "pointage"
RAPPROCHEMENT_COLONNES = "id, date, solde_reel, solde_calcule, comptes, regle, note"


def dernier_pointage(c, auj: date) -> Optional[dict]:
    """Dernier pointage : {date, jours, ecart, regle, a_refaire} (`jours` : il y a combien de jours),
    None s'il n'y en a jamais eu."""
    r = c.execute("SELECT date, solde_reel - solde_calcule ecart, regle FROM rapprochements "
                  "ORDER BY date DESC, id DESC LIMIT 1").fetchone()
    if not r:
        return None
    jours = (auj - r["date"]).days
    return {"date": r["date"], "jours": jours, "ecart": float(r["ecart"]), "regle": r["regle"],
            "a_refaire": jours > POINTAGE_A_REFAIRE_JOURS}


def liquidites_du_jour(auj: date, p: Optional[dict] = None) -> float:
    """Liquidités calculées à la fin d'aujourd'hui : celles du patrimoine, sans les opérations du
    Budget datées de demain ou après (un loyer saisi d'avance n'est pas encore sorti de la banque)."""
    p = p or calculer_patrimoine(auj)
    with db() as c:
        futur = c.execute("""SELECT (SELECT COALESCE(SUM(montant),0) FROM revenus WHERE date > %s)
                                  - (SELECT COALESCE(SUM(montant),0) FROM depenses WHERE date > %s) t""",
                          (auj.isoformat(), auj.isoformat())).fetchone()["t"]
    return round(p["liquidites"] - float(futur), 2)


def jours_sans_depense(c, debut: date, fin: date) -> list:
    """Jours de [debut, fin] sans aucune dépense : c'est souvent là que se cachent les oublis."""
    debut = max(debut, fin - timedelta(days=JOURS_SANS_DEPENSE_MAX - 1))
    if debut > fin:
        return []
    avec = {r["date"] for r in c.execute("SELECT DISTINCT date FROM depenses WHERE date >= %s AND date <= %s",
                                         (debut.isoformat(), fin.isoformat())).fetchall()}
    jours = [debut + timedelta(days=i) for i in range((fin - debut).days + 1)]
    return [j for j in jours if j.isoformat() not in avec]


def _rapprochement(r: dict) -> dict:
    comptes = json.loads(r["comptes"]) if isinstance(r["comptes"], str) else r["comptes"]
    return {**r, "solde_reel": float(r["solde_reel"]), "solde_calcule": float(r["solde_calcule"]),
            "ecart": round(float(r["solde_reel"] - r["solde_calcule"]), 2), "comptes": comptes}


@router.get("/rapprochements")
def lire_rapprochements():
    """Liquidités calculées à comparer au solde réel, les pointages passés (les plus récents d'abord)
    et les jours sans dépense depuis le dernier pointage (sinon sur les 30 derniers jours)."""
    auj = aujourdhui()
    calcule = liquidites_du_jour(auj)
    with db() as c:
        historique = [_rapprochement(r) for r in c.execute(
            f"SELECT {RAPPROCHEMENT_COLONNES} FROM rapprochements ORDER BY date DESC, id DESC LIMIT 12").fetchall()]
        depuis = historique[0]["date"] + timedelta(days=1) if historique else auj - timedelta(days=30)
        sans = jours_sans_depense(c, depuis, auj - timedelta(days=1))
    return {"solde_calcule": calcule, "historique": historique, "jours_sans_depense": sans, "depuis": depuis,
            "a_refaire_jours": POINTAGE_A_REFAIRE_JOURS}


def pointer(auj: date, comptes: list, note: str = "", categorie: Optional[str] = None,
            enregistrer_ecart: bool = False) -> dict:
    """Enregistre un pointage (`comptes` : [{nom, montant}]) et, si demandé, l'écart en opération du
    jour. Renvoie le pointage avec son `ecart` (réel − calculé : négatif = argent qui manque)."""
    calcule = liquidites_du_jour(auj)
    reel = round(sum(float(x["montant"]) for x in comptes), 2)
    ecart = round(reel - calcule, 2)
    regle = None
    with references_valides(), db() as c:
        if enregistrer_ecart and abs(ecart) >= 0.01:
            if ecart < 0:
                if not categorie or not c.execute("SELECT 1 FROM categories WHERE nom=%s AND actif=1", (categorie,)).fetchone():
                    raise HTTPException(400, "Choisis la catégorie de la dépense qui manque")
                c.execute("INSERT INTO depenses(date,categorie,description,montant,tags) VALUES(%s,%s,%s,%s,%s)",
                          (auj.isoformat(), categorie, LIBELLE_ECART, -ecart, [TAG_ECART]))
                regle = "depense"
            else:
                c.execute("INSERT INTO revenus(date,source,description,montant,tags) VALUES(%s,NULL,%s,%s,%s)",
                          (auj.isoformat(), LIBELLE_ECART, ecart, [TAG_ECART]))
                regle = "revenu"
        row = c.execute(f"""INSERT INTO rapprochements (date, solde_reel, solde_calcule, comptes, regle, note)
                            VALUES (%s,%s,%s,%s,%s,%s) RETURNING {RAPPROCHEMENT_COLONNES}""",
                        (auj, reel, calcule, json.dumps(comptes, ensure_ascii=False), regle, note)).fetchone()
    return _rapprochement(row)


@router.post("/rapprochements", status_code=201)
def ajouter_rapprochement(r: RapprochementIn):
    return pointer(aujourdhui(), [x.model_dump() for x in r.comptes], r.note, r.categorie, r.enregistrer_ecart)


@router.delete("/rapprochements/{rapprochement_id}", status_code=204)
def supprimer_rapprochement(rapprochement_id: int):
    """Retire un pointage (erreur de frappe). L'opération d'écart éventuelle reste dans le Budget :
    elle se supprime dans Saisie, comme toute opération."""
    with db() as c:
        if c.execute("DELETE FROM rapprochements WHERE id=%s", (rapprochement_id,)).rowcount == 0:
            raise HTTPException(404, "Pointage introuvable")


COLONNES_HISTORIQUE = ("total", "liquidites", "bourse", "autres_actifs", "creances", "dettes")


def noter_patrimoine(auj: date, p: Optional[dict] = None) -> dict:
    """Note le patrimoine du jour dans patrimoine_historique (une ligne par jour, remplacée par
    le dernier calcul de la journée) : la courbe se construit ainsi au fil des jours. Appelée par
    la tâche du matin et à chaque lecture du patrimoine. Renvoie le patrimoine calculé."""
    p = p or calculer_patrimoine(auj)
    with db() as c:
        c.execute(f"""INSERT INTO patrimoine_historique (date, {", ".join(COLONNES_HISTORIQUE)})
                      VALUES (%s, {", ".join(["%s"] * len(COLONNES_HISTORIQUE))})
                      ON CONFLICT (date) DO UPDATE SET {", ".join(f"{k}=EXCLUDED.{k}" for k in COLONNES_HISTORIQUE)},
                                                       estime=false, maj_le=now()""",
                  (auj, *(p[k] for k in COLONNES_HISTORIQUE)))
    return p


@router.get("")
def obtenir_patrimoine():
    auj = aujourdhui()
    p = calculer_patrimoine(auj)
    try:
        noter_patrimoine(auj, p)
    except Exception as e:   # la courbe ne doit jamais empêcher d'afficher le patrimoine
        print(f"[patrimoine] historique non noté — {e!r}", flush=True)
    return p


@router.get("/historique")
def historique_patrimoine(jours: Optional[int] = None):
    """Patrimoine noté jour après jour, du plus ancien au plus récent ; `jours` : seulement les N derniers jours."""
    clause, params = ("WHERE date > %s", (aujourdhui() - timedelta(days=jours),)) if jours else ("", ())
    with db() as c:
        rows = c.execute(f"SELECT date, estime, {', '.join(COLONNES_HISTORIQUE)} FROM patrimoine_historique {clause} ORDER BY date",
                         params).fetchall()
    return [{"date": r["date"], "estime": r["estime"], **{k: float(r[k]) for k in COLONNES_HISTORIQUE}} for r in rows]


# ---------------------------------------------------------------- courbe : mois passés reconstitués
# Priorité d'un cours à date égale : le cours saisi à la main l'emporte sur le cours actuel, qui
# l'emporte sur le cours noté ce jour-là (bourse_prix_historique), qui l'emporte sur le prix d'une transaction
COURS_TRANSACTION, COURS_HISTORIQUE, COURS_ACTUEL, COURS_SAISI = 0, 1, 2, 3
SOURCES_COURS = {COURS_TRANSACTION: "transaction", COURS_HISTORIQUE: "historique", COURS_ACTUEL: "actuel",
                 COURS_SAISI: "saisi"}


def fins_de_mois(debut: date, avant: date) -> list:
    """Derniers jours des mois, du mois de `debut` jusqu'au dernier qui tombe strictement avant `avant`."""
    jours, annee, mois = [], debut.year, debut.month
    while True:
        suivant = date(annee + mois // 12, mois % 12 + 1, 1)
        fin = suivant - timedelta(days=1)
        if fin >= avant:
            return jours
        jours.append(fin)
        annee, mois = suivant.year, suivant.month


def dernier_cours(cours: list, jour: date) -> Optional[tuple]:
    """`cours` : [(date, priorité, cours)] triée. Renvoie le plus récent jusqu'à `jour` inclus
    (à date égale, la plus haute priorité), None si aucun."""
    meilleur = None
    for c in cours:
        if c[0] > jour:
            break
        meilleur = c
    return meilleur


def quantites_le(transactions: list, jour: date) -> dict:
    """Quantité détenue de chaque titre à la fin de `jour` (titres encore détenus seulement)."""
    q = {}
    for t in transactions:
        if t["date"] <= jour:
            q[t["titre"]] = q.get(t["titre"], 0.0) + t["quantite"]
    return {titre: n for titre, n in q.items() if n > 1e-9}


def patrimoine_aux_dates(jours: list, d: dict) -> list:
    """Patrimoine à la fin de chaque jour de `jours`, avec les seules opérations datées jusqu'à ce
    jour (mêmes formules que calculer_patrimoine). `d` vient de charger_operations() : la fonction
    ne lit pas la base. Limites : un autre actif compte à sa valeur ACTUELLE dès sa date, et un
    titre à son dernier cours connu ce jour-là."""
    points = []
    for jour in jours:
        iso = jour.isoformat()
        epargne = sum(m for j, m in d["budget"] if j <= iso)
        actifs = [a for a in d["actifs"] if a["depuis"] <= jour]
        autres, verse = sum(a["valeur"] for a in actifs), sum(a["verse"] for a in actifs)
        pret = emprunt = 0.0
        for x in d["dettes"]:
            if x["date"] > jour:
                continue
            reste = x["montant"] - sum(m for j, m in x["remboursements"] if j <= jour)
            if reste > 0:
                if x["sens"] == "pret":
                    pret += reste
                else:
                    emprunt += reste
        apports = sum(m for j, m in d["mouvements"] if j <= jour)
        especes = apports + sum(m for j, m in d["flux_bourse"] if j <= jour)
        titres = 0.0
        for titre, n in quantites_le(d["transactions"], jour).items():
            c = dernier_cours(d["cours"].get(titre, []), jour)
            titres += n * (c[2] if c else 0.0)
        bourse_total = titres + especes
        liquidites = d["solde_depart"] + epargne - apports - verse - pret + emprunt
        total = liquidites + bourse_total + autres + pret - emprunt
        points.append({"date": jour, "total": round(total, 2), "liquidites": round(liquidites, 2),
                       "bourse": round(bourse_total, 2), "autres_actifs": round(autres, 2),
                       "creances": round(pret, 2), "dettes": round(emprunt, 2)})
    return points


def charger_operations() -> dict:
    """Toutes les opérations datées utiles à patrimoine_aux_dates, en nombres Python simples.
    `debut` : date de la plus ancienne opération (None si l'application est vide)."""
    _, gains, calc = bourse._positions_et_gains()
    tpcvm = {g.id: g.tpcvm for g in gains}
    mouvements = bourse._mouvements()
    dividendes, frais = bourse._dividendes(), bourse._frais_compte()
    with db() as c:
        solde_depart = _params(c).get("solde_depart", 0.0)
        budget = [(r["date"], float(r["m"])) for r in c.execute(
            """SELECT date, SUM(montant) m FROM revenus GROUP BY date
               UNION ALL SELECT date, -SUM(montant) FROM depenses GROUP BY date""").fetchall()]
        actifs = [{"depuis": min(r["cree_le"].date(), r["maj_le"]), "valeur": float(r["valeur"]), "verse": float(r["verse"])}
                  for r in c.execute("SELECT valeur, verse, maj_le, cree_le FROM actifs").fetchall()]
        dettes = [{"sens": x["sens"], "date": x["date_operation"], "montant": float(x["montant"]),
                   "remboursements": [(r["date_operation"], float(r["montant"])) for r in x["remboursements"]]}
                  for x in lire_dettes(c)]
        prix = c.execute("SELECT titre, cours_actuel, maj_le FROM bourse_prix WHERE cours_actuel > 0").fetchall()
        saisis = c.execute("SELECT titre, date, cours FROM bourse_cours_historique").fetchall()
        notes = c.execute("SELECT titre, date, cours FROM bourse_prix_historique").fetchall()

    cours = {}
    for r in notes:
        cours.setdefault(r["titre"], []).append((r["date"], COURS_HISTORIQUE, float(r["cours"])))
    for t in calc:
        cours.setdefault(t["titre"], []).append((t["date_operation"], COURS_TRANSACTION, float(t["cours_unitaire"])))
    for r in prix:
        cours.setdefault(r["titre"], []).append((r["maj_le"].date(), COURS_ACTUEL, float(r["cours_actuel"])))
    for r in saisis:
        cours.setdefault(r["titre"], []).append((r["date"], COURS_SAISI, float(r["cours"])))
    for liste in cours.values():
        liste.sort()

    transactions = [{"date": t["date_operation"], "titre": t["titre"],
                     "quantite": float(t["quantite"]) * (1 if t["type_operation"] == "Achat" else -1)} for t in calc]
    flux_bourse = [(t["date_operation"], -float(t["_net_decimal"]) if t["type_operation"] == "Achat"
                    else float(t["_net_decimal"]) - float(tpcvm.get(t["id"], 0))) for t in calc]
    flux_bourse += [(x["date_operation"], float(x["montant"])) for x in dividendes]
    flux_bourse += [(x["date_operation"], -float(x["montant"])) for x in frais]
    mvts = [(m["date_operation"], float(m["montant"]) * (1 if m["type_mouvement"] == "Apport" else -1)) for m in mouvements]

    dates = [a["depuis"] for a in actifs] + [x["date"] for x in dettes] + [j for j, _ in mvts + flux_bourse]
    for j, _ in budget:
        try:
            dates.append(date.fromisoformat(j[:10]))
        except (TypeError, ValueError):
            pass
    return {"solde_depart": solde_depart, "budget": budget, "actifs": actifs, "dettes": dettes, "mouvements": mvts,
            "flux_bourse": flux_bourse, "transactions": transactions, "cours": cours,
            "debut": min(dates) if dates else None}


def a_des_estimations() -> bool:
    with db() as c:
        return c.execute("SELECT EXISTS (SELECT 1 FROM patrimoine_historique WHERE estime) e").fetchone()["e"]


def reconstituer_historique(auj: date) -> dict:
    """Recalcule un point par fin de mois, de la première opération jusqu'au premier vrai point
    noté (ou jusqu'à aujourd'hui s'il n'y en a pas). Les anciens points estimés sont remplacés ;
    un vrai point n'est jamais touché. Relancée chaque matin une fois activée : corriger une
    ancienne saisie met donc la courbe à jour le lendemain (ou tout de suite avec le bouton)."""
    d = charger_operations()
    with db() as c:
        premier_vrai = c.execute("SELECT MIN(date) m FROM patrimoine_historique WHERE NOT estime").fetchone()["m"]
    jours = fins_de_mois(d["debut"], min(premier_vrai or auj, auj)) if d["debut"] else []
    points = patrimoine_aux_dates(jours, d)
    with db() as c:
        c.execute("DELETE FROM patrimoine_historique WHERE estime")
        with c.cursor() as cur:
            cur.executemany(f"""INSERT INTO patrimoine_historique (date, {", ".join(COLONNES_HISTORIQUE)}, estime)
                                VALUES (%s, {", ".join(["%s"] * len(COLONNES_HISTORIQUE))}, true)
                                ON CONFLICT (date) DO NOTHING""",
                            [(p["date"], *(p[k] for k in COLONNES_HISTORIQUE)) for p in points])
    return {"points": len(points), "debut": jours[0] if jours else None, "fin": jours[-1] if jours else None}


@router.post("/historique/reconstituer")
def reconstituer():
    return reconstituer_historique(aujourdhui())


@router.get("/cours-passes")
def lire_cours_passes(jour: date):
    """Titres détenus à la fin de `jour`, avec le cours qu'utilise la reconstitution sans saisie
    (`estime`, et d'où il vient) et celui saisi à la main pour ce jour (`saisi`)."""
    d = charger_operations()
    resultat = []
    for titre, n in sorted(quantites_le(d["transactions"], jour).items()):
        liste = d["cours"].get(titre, [])
        saisi = next((c[2] for c in liste if c[0] == jour and c[1] == COURS_SAISI), None)
        estime = dernier_cours([c for c in liste if not (c[0] == jour and c[1] == COURS_SAISI)], jour)
        resultat.append({"titre": titre, "quantite": round(n, 4), "saisi": saisi,
                         "estime": estime[2] if estime else None,
                         "source": SOURCES_COURS[estime[1]] if estime else None,
                         "source_date": estime[0] if estime else None})
    return resultat


@router.put("/cours-passes")
def enregistrer_cours_passes(e: CoursPassesIn):
    auj = aujourdhui()
    if e.jour >= auj:
        raise HTTPException(400, "Choisis une date passée : le cours du jour se met à jour dans Bourse → Positions")
    with references_valides(), db() as c:
        for x in e.cours:
            titre = x.titre.strip().upper()
            if x.cours is None:
                c.execute("DELETE FROM bourse_cours_historique WHERE titre=%s AND date=%s", (titre, e.jour))
            else:
                c.execute("""INSERT INTO bourse_cours_historique (titre, date, cours) VALUES (%s,%s,%s)
                             ON CONFLICT (titre, date) DO UPDATE SET cours=EXCLUDED.cours""", (titre, e.jour, x.cours))
    return reconstituer_historique(auj)


@router.put("/reglages")
def modifier_reglages(r: ReglagesPatrimoine):
    valeurs = {"solde_depart": r.solde_depart, "zakat_prix_or": r.prix_or_gramme}
    with db() as c:
        for cle, valeur in valeurs.items():
            c.execute("""INSERT INTO params(cle,valeur) VALUES(%s,%s)
                         ON CONFLICT (cle) DO UPDATE SET valeur=EXCLUDED.valeur""", (cle, valeur))
        if r.debut_hawl:
            # Date gardée en numéro de jour : la table params ne stocke que des nombres
            c.execute("""INSERT INTO params(cle,valeur) VALUES('zakat_debut_hawl',%s)
                         ON CONFLICT (cle) DO UPDATE SET valeur=EXCLUDED.valeur""", (r.debut_hawl.toordinal(),))
        else:
            c.execute("DELETE FROM params WHERE cle='zakat_debut_hawl'")
        for cle, valeur in (("liberte_taux_retrait", r.taux_retrait), ("liberte_rendement", r.rendement)):
            if valeur is not None:
                c.execute("""INSERT INTO params(cle,valeur) VALUES(%s,%s)
                             ON CONFLICT (cle) DO UPDATE SET valeur=EXCLUDED.valeur""", (cle, valeur))
    return {"ok": True}


# ---------------------------------------------------------------- autres actifs
def _valeurs(a: ActifIn) -> tuple:
    return (a.nom, a.type.strip() or "Autre", a.valeur, a.verse, a.zakat, a.maj_le, a.note.strip())


@router.post("/actifs", status_code=201)
def ajouter_actif(a: ActifIn):
    with db() as c:
        return c.execute(f"""INSERT INTO actifs (nom, type, valeur, verse, zakat, maj_le, note)
                             VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING {ACTIF_COLONNES}""", _valeurs(a)).fetchone()


@router.put("/actifs/{actif_id}")
def modifier_actif(actif_id: int, a: ActifIn):
    with db() as c:
        row = c.execute(f"""UPDATE actifs SET nom=%s, type=%s, valeur=%s, verse=%s, zakat=%s, maj_le=%s, note=%s
                            WHERE id=%s RETURNING {ACTIF_COLONNES}""", (*_valeurs(a), actif_id)).fetchone()
    if not row:
        raise HTTPException(404, "Actif introuvable")
    return row


@router.delete("/actifs/{actif_id}", status_code=204)
def supprimer_actif(actif_id: int):
    with db() as c:
        if c.execute("DELETE FROM actifs WHERE id=%s", (actif_id,)).rowcount == 0:
            raise HTTPException(404, "Actif introuvable")
