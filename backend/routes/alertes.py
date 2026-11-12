# -*- coding: utf-8 -*-
"""
Alertes de dépenses inhabituelles, affichées sur l'accueil et rappelées le lundi matin :

- une catégorie qui, ce mois-ci, dépasse nettement sa moyenne des 6 derniers mois terminés ;
- un montant récurrent qui augmente (un abonnement dont le prix monte) ;
- une dépense qui ressemble à un doublon (même jour, catégorie, description et montant).

Chaque alerte a une clé stable : « Ignorer » la range dans alertes_ignorees, elle ne revient plus
(un doublon qui n'en est pas un, deux cafés au même prix le même jour).
"""
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from config import aujourdhui
from database import db
from resume_rendu import dh
from schemas import IgnorerAlerteIn
from securite import utilisateur_courant

router = APIRouter(prefix="/api/alertes", tags=["alertes"], dependencies=[Depends(utilisateur_courant)])

MOIS_REFERENCE = 6          # moyenne d'une catégorie : sur les 6 derniers mois terminés...
MOIS_REFERENCE_MIN = 3      # ...dont au moins 3 avec des dépenses
HAUSSE_CATEGORIE = 0.30     # +30 % au-dessus de la moyenne...
HAUSSE_CATEGORIE_MIN = 300  # ...et au moins 300 DH de plus
JOURS_RECURRENT = 200       # montants récurrents : historique examiné
RECURRENT_MOIS_MIN = 3      # vu dans au moins 3 mois différents
RECURRENT_STABLE = 0.02     # les montants d'avant ne varient pas de plus de 2 % : un montant fixe
HAUSSE_RECURRENT = 0.05     # alerte à partir de +5 %...
HAUSSE_RECURRENT_MIN = 5    # ...et 5 DH
RECURRENT_RECENT_JOURS = 45 # la hausse doit être récente
JOURS_DOUBLONS = 14


def _mois(d: date, decalage: int) -> str:
    total = d.year * 12 + d.month - 1 + decalage
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def pct(v: float) -> str:
    return f"+{round(v * 100)} %"


def alertes_categories(c, auj: date) -> list:
    mois_courant = auj.strftime("%Y-%m")
    reference = [_mois(auj, -i) for i in range(MOIS_REFERENCE, 0, -1)]
    rows = c.execute("""SELECT categorie, substr(date,1,7) m, SUM(montant) t FROM depenses
                        WHERE date >= %s AND date <= %s GROUP BY 1, 2""",
                     (reference[0] + "-01", auj.isoformat())).fetchall()
    # Mois de référence où l'application servait (au moins une dépense) : la moyenne n'est faite que sur eux
    actifs = {r["m"] for r in rows if r["m"] in reference}
    if len(actifs) < MOIS_REFERENCE_MIN:
        return []
    par_cat = defaultdict(dict)
    for r in rows:
        par_cat[r["categorie"]][r["m"]] = float(r["t"])
    alertes = []
    for cat, mois in par_cat.items():
        actuel = mois.get(mois_courant, 0.0)
        moyenne = sum(mois.get(m, 0.0) for m in actifs) / len(actifs)
        if moyenne > 0 and actuel >= moyenne * (1 + HAUSSE_CATEGORIE) and actuel - moyenne >= HAUSSE_CATEGORIE_MIN:
            alertes.append({"cle": f"categorie:{mois_courant}:{cat}", "type": "categorie", "categorie": cat,
                            "titre": f"{cat} : {dh(actuel)} ce mois-ci",
                            "detail": f"{pct(actuel / moyenne - 1)} par rapport à ta moyenne ({dh(moyenne)} par mois)",
                            "montant": round(actuel - moyenne, 2)})
    return sorted(alertes, key=lambda a: -a["montant"])


def alertes_hausses(c, auj: date) -> list:
    """Même catégorie et même description, vue dans au moins 3 mois, à un montant fixe jusqu'ici,
    et dont le dernier montant (récent) est plus élevé."""
    rows = c.execute("""SELECT categorie, lower(trim(description)) d, date, montant FROM depenses
                        WHERE date >= %s AND date <= %s AND trim(COALESCE(description,'')) <> ''
                        ORDER BY date, id""",
                     ((auj - timedelta(days=JOURS_RECURRENT)).isoformat(), auj.isoformat())).fetchall()
    groupes = defaultdict(list)
    for r in rows:
        groupes[(r["categorie"], r["d"])].append(r)
    limite_recente = (auj - timedelta(days=RECURRENT_RECENT_JOURS)).isoformat()
    alertes = []
    for (cat, desc), ops in groupes.items():
        if len({o["date"][:7] for o in ops}) < RECURRENT_MOIS_MIN or ops[-1]["date"] < limite_recente:
            continue
        dernier, avant = float(ops[-1]["montant"]), [float(o["montant"]) for o in ops[:-1]]
        if len(avant) < 2 or max(avant) > min(avant) * (1 + RECURRENT_STABLE):
            continue
        ancien = avant[-1]
        if dernier >= ancien * (1 + HAUSSE_RECURRENT) and dernier - ancien >= HAUSSE_RECURRENT_MIN:
            nom = ops[-1]["d"]
            alertes.append({"cle": f"hausse:{cat}:{desc}:{dernier:.2f}", "type": "hausse", "categorie": cat,
                            "titre": f"« {nom} » passe de {dh(ancien)} à {dh(dernier)}",
                            "detail": f"{pct(dernier / ancien - 1)}, soit {dh((dernier - ancien) * 12)} de plus sur un an s'il revient chaque mois",
                            "montant": round(dernier - ancien, 2)})
    return alertes


def alertes_doublons(c, auj: date) -> list:
    rows = c.execute("""SELECT date, categorie, MIN(COALESCE(description,'')) description, montant, COUNT(*) n, MIN(id) premier
                        FROM depenses WHERE date >= %s AND date <= %s
                        GROUP BY date, categorie, lower(trim(COALESCE(description,''))), montant
                        HAVING COUNT(*) > 1 ORDER BY date DESC""",
                     ((auj - timedelta(days=JOURS_DOUBLONS)).isoformat(), auj.isoformat())).fetchall()
    alertes = []
    for r in rows:
        jour = date.fromisoformat(r["date"])
        quoi = f"« {r['description'].strip()} », " if r["description"].strip() else ""
        alertes.append({"cle": f"doublon:{r['premier']}:{r['n']}", "type": "doublon", "categorie": r["categorie"],
                        "titre": f"{r['n']} × {dh(r['montant'])} le {jour.day:02d}/{jour.month:02d}",
                        "detail": f"{quoi}{r['categorie']} : un doublon ? Supprime-le dans Saisie, ou ignore l'alerte",
                        "montant": float(r["montant"]), "date": r["date"]})
    return alertes


def calculer_alertes(auj: date) -> list:
    """Toutes les alertes en cours, sans celles qu'on a ignorées."""
    with db() as c:
        ignorees = {r["cle"] for r in c.execute("SELECT cle FROM alertes_ignorees").fetchall()}
        alertes = alertes_doublons(c, auj) + alertes_categories(c, auj) + alertes_hausses(c, auj)
    return [a for a in alertes if a["cle"] not in ignorees]


@router.get("")
def lister_alertes():
    return calculer_alertes(aujourdhui())


@router.post("/ignorer", status_code=204)
def ignorer_alerte(a: IgnorerAlerteIn):
    with db() as c:
        c.execute("INSERT INTO alertes_ignorees(cle) VALUES(%s) ON CONFLICT DO NOTHING", (a.cle,))
        # Une alerte ignorée il y a plus d'un an ne peut plus revenir (fenêtres de 6 mois au plus)
        c.execute("DELETE FROM alertes_ignorees WHERE le < now() - interval '400 days'")
