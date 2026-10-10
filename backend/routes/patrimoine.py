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
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from config import aujourdhui
from database import db
from securite import utilisateur_courant
from schemas import ActifIn, ReglagesPatrimoine
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
MOIS_RESERVE = 6          # dépense moyenne calculée sur les derniers mois terminés
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
            "reserve": reserve, "zakat": zakat, "liberte": liberte}


@router.get("")
def obtenir_patrimoine():
    return calculer_patrimoine(aujourdhui())


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
