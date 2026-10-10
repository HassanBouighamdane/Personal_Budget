# -*- coding: utf-8 -*-
"""
Rappels et résumé hebdomadaire, envoyés par Telegram ou e-mail (cf. messagerie.py).

Une seule tâche planifiée, GET /api/cron/quotidien, appelée chaque matin (Vercel Cron, cf.
vercel.json) : elle envoie les rappels du jour (échéances, remboursements attendus) et, le
lundi, le résumé de la semaine écoulée (Budget, Bourse, Lectures, Carnet) ; le 1er du mois,
le bilan du mois écoulé.

Les textes sont construits par des fonctions qui reçoivent la date du jour en paramètre,
pour que les tests la fixent.
"""
import secrets
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from config import CRON_SECRET, aujourdhui
from database import db
import sauvegarde
from messagerie import EnvoiImpossible, canaux, envoyer, envoyer_fichier
from securite import utilisateur_courant
from routes import bourse, lectures, patrimoine
from routes.carnet import lire_dettes, lire_echeances
from routes.rapports import calculer_resume, calculer_resume_annuel, calculer_resume_semaine
from resume_rendu import (delai, dh, jour, rendre_email, rendre_email_annee, rendre_email_mois, rendre_telegram,
                          rendre_telegram_annee, rendre_telegram_mois, rendre_texte, rendre_texte_annee, rendre_texte_mois)

router = APIRouter(prefix="/api/rappels", tags=["rappels"], dependencies=[Depends(utilisateur_courant)])
# Appelé par le planificateur, sans session : protégé par CRON_SECRET
cron = APIRouter(prefix="/api/cron", tags=["cron"])

MOIS_LONGS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
              "novembre", "décembre"]
# Un remboursement attendu est rappelé 3 jours avant, puis le jour même
RAPPEL_DETTE_JOURS = (3, 0)


def _dette_libelle(d: dict) -> str:
    qui = f"Prêt à {d['personne']}" if d["sens"] == "pret" else f"Emprunt auprès de {d['personne']}"
    return f"{qui} ({dh(d['reste'])} restants)"


# ---------------------------------------------------------------- rappels du jour
def jours_de_rappel(rappel_jours: int) -> set:
    """Jours (avant l'échéance) où un rappel part : au début de la fenêtre choisie, puis à
    J−7 et J−1 s'ils tombent dedans, et le jour même."""
    return {rappel_jours, 0} | {j for j in (7, 1) if j < rappel_jours}


def rappels_du_jour(auj: date) -> list:
    """Lignes du message de rappel du jour (liste vide : rien à envoyer)."""
    with db() as c:
        echeances = lire_echeances(c, auj)
        dettes = lire_dettes(c)
    lignes = [f"• {e['titre']} : {delai(e['jours_restants'])} ({jour(e['date_echeance'])})"
              for e in echeances if e["jours_restants"] in jours_de_rappel(e["rappel_jours"])]
    for d in dettes:
        if d["reste"] > 0 and d["echeance"] and (d["echeance"] - auj).days in RAPPEL_DETTE_JOURS:
            lignes.append(f"• {_dette_libelle(d)} : remboursement prévu {delai((d['echeance'] - auj).days)}")
    return lignes


# ---------------------------------------------------------------- résumé hebdomadaire : données
def semaine_ecoulee(auj: date) -> tuple:
    """(lundi, dimanche) de la dernière semaine terminée avant `auj`."""
    lundi = auj - timedelta(days=auj.weekday() + 7)
    return lundi, lundi + timedelta(days=6)


def _donnees_budget(lundi: date, auj: date) -> dict:
    s = calculer_resume_semaine(lundi, auj)
    dep, prec = s["total_depenses"], s["depenses_semaine_precedente"]
    jours = [{"date": date.fromisoformat(j["date"]), "dep": j["dep"]} for j in s["par_jour"]]
    plus_grosse = s["top"][0] if s["top"] else None
    m = calculer_resume(auj.strftime("%Y-%m"), auj)
    return {
        "dep": dep, "rev": s["total_revenus"], "epargne": s["epargne"], "dep_prec": prec,
        "variation_pct": round((dep - prec) / prec * 100) if prec else None,
        "budget_hebdo": s["budget_hebdo"], "dep_var": s["depenses_variables"], "reste": s["reste_budget_hebdo"],
        "jours": jours,
        "jour_max": max(jours, key=lambda j: j["dep"]) if dep else None,
        "jours_sans": sum(1 for j in jours if not j["dep"]),
        "categories": s["donut"],
        "plus_grosse": plus_grosse and {"date": date.fromisoformat(plus_grosse["date"]), "categorie": plus_grosse["categorie"],
                                        "description": (plus_grosse["description"] or "").strip(), "montant": plus_grosse["montant"]},
        # Mois en cours ; la projection n'a pas de valeur avant quelques jours de dépenses
        "mois": {"nom": MOIS_LONGS[auj.month - 1], "dep": m["total_depenses"], "budget": m["budget_total"],
                 "projection": m["projection_fin_mois"] if auj.day >= 5 else None}
                if m["total_depenses"] or m["total_revenus"] else None,
    }


def _donnees_bourse(patrimoine_precedent: Optional[float]) -> Optional[dict]:
    """`patrimoine_precedent` : valeur du compte au résumé précédent, pour l'écart."""
    d = bourse.obtenir_dashboard()
    if not d.patrimoine_total and not d.apports_nets:
        return None
    return {"patrimoine": d.patrimoine_total, "titres": d.valeur_marche, "especes": d.especes_disponibles,
            "ecart": d.patrimoine_total - patrimoine_precedent if patrimoine_precedent else None,
            "perf": d.performance_globale,
            # Sans apport saisi, le pourcentage n'a pas de base
            "perf_pct": d.performance_globale_pct if d.apports_nets > 0 else None}


def _donnees_lectures(lundi: date, dimanche: date, auj: date) -> Optional[dict]:
    with db() as c:
        finis = c.execute("SELECT titre, pages FROM lectures_livres WHERE date_fin BETWEEN %s AND %s ORDER BY date_fin",
                          (lundi, dimanche)).fetchall()
        en_cours = c.execute("SELECT titre FROM lectures_a_lire WHERE date_debut IS NOT NULL "
                             "ORDER BY date_debut DESC").fetchall()
    bilan = lectures.calculer_bilan(auj.year, auj)
    if not finis and not en_cours and not bilan["nb_livres"]:
        return None
    return {"finis": finis, "en_cours": [l["titre"] for l in en_cours], "annee": auj.year,
            "nb": bilan["nb_livres"], "objectif": bilan["objectif_annuel"]}


def _donnees_dettes(auj: date) -> Optional[dict]:
    with db() as c:
        dettes = [d for d in lire_dettes(c) if d["reste"] > 0]
    if not dettes:
        return None
    return {"on_me_doit": sum(d["reste"] for d in dettes if d["sens"] == "pret"),
            "je_dois": sum(d["reste"] for d in dettes if d["sens"] == "emprunt"),
            "en_retard": [{"libelle": _dette_libelle(d), "echeance": d["echeance"]}
                          for d in dettes if d["echeance"] and d["echeance"] < auj]}


def _donnees_echeances(auj: date) -> list:
    with db() as c:
        return [{"titre": e["titre"], "jours": e["jours_restants"], "date": e["date_echeance"]}
                for e in lire_echeances(c, auj) if e["a_rappeler"]]


def _section(nom: str, construire, defaut=None):
    """Données d'une section, ou `defaut` si elle échoue (les autres sections partent quand même)."""
    try:
        return construire()
    except Exception as e:
        print(f"[rappels] section {nom} ignorée — {e!r}", flush=True)
        return defaut


def resume_hebdo(auj: date, patrimoine_precedent: Optional[float] = None) -> dict:
    """Résumé de la dernière semaine terminée : {"sujet", "texte", "telegram", "html", "patrimoine"}
    (mise en forme : resume_rendu.py). Une section qui échoue est laissée de côté : un souci
    Bourse ne prive pas du résumé du Budget."""
    lundi, dimanche = semaine_ecoulee(auj)
    d = {"lundi": lundi, "dimanche": dimanche,
         "budget": _section("budget", lambda: _donnees_budget(lundi, auj)),
         "bourse": _section("bourse", lambda: _donnees_bourse(patrimoine_precedent)),
         "lectures": _section("lectures", lambda: _donnees_lectures(lundi, dimanche, auj)),
         "dettes": _section("dettes", lambda: _donnees_dettes(auj)),
         "echeances": _section("echeances", lambda: _donnees_echeances(auj), [])}
    return {"sujet": f"📊 Ta semaine du {jour(lundi)} au {jour(dimanche)}",
            "texte": rendre_texte(d), "telegram": rendre_telegram(d), "html": rendre_email(d),
            "patrimoine": d["bourse"]["patrimoine"] if d["bourse"] else None}


# ---------------------------------------------------------------- résumé mensuel : données
def mois_ecoule(auj: date) -> str:
    """Dernier mois terminé avant `auj`, au format AAAA-MM."""
    return (auj.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def _donnees_budget_mois(mois: str, auj: date) -> dict:
    m = calculer_resume(mois, auj)
    dep, prec = m["total_depenses"], m["depenses_mois_precedent_total"]
    # Dépenses par tranche de 7 jours (la dernière, du 29 à la fin, est plus courte)
    cumul = [0] + m["cumul_quotidien"]
    semaines = [{"libelle": f"{debut + 1}–{min(debut + 7, m['nb_jours'])}", "dep": round(cumul[min(debut + 7, m["nb_jours"])] - cumul[debut], 2)}
                for debut in range(0, m["nb_jours"], 7)]
    categories = sorted((c for c in m["budget_vs_reel"] if c["reel"]), key=lambda c: -c["reel"])
    return {
        "dep": dep, "rev": m["total_revenus"], "epargne": m["epargne"], "taux": m["taux_epargne"],
        "objectif": m["objectif_epargne"], "budget": m["budget_total"], "dep_prec": prec,
        "variation_pct": round((dep - prec) / prec * 100) if prec else None,
        "semaines": semaines, "categories": categories,
        "nb_depassees": sum(1 for c in categories if c["budget"] and c["reel"] > c["budget"]),
        "top": [{"date": date.fromisoformat(t["date"]), "categorie": t["categorie"],
                 "description": (t["description"] or "").strip(), "montant": t["montant"]} for t in m["top"]],
        "evolution": [{"m": e["m"], "dep": e["dep"]} for e in m["evolution"]],
    }


def _donnees_bourse_mois(mois: str) -> Optional[dict]:
    d = bourse.obtenir_dashboard(mois=mois)
    if not d.patrimoine_total and not d.apports_nets:
        return None
    return {"patrimoine": d.patrimoine_total, "resultat": d.resultat_net_periode, "dividendes": d.dividendes_nets,
            "apports": d.apports_periode, "retraits": d.retraits_periode, "perf": d.performance_globale,
            "perf_pct": d.performance_globale_pct if d.apports_nets > 0 else None}


def resume_mensuel(auj: date) -> dict:
    """Bilan du dernier mois terminé : {"sujet", "texte", "telegram", "html"}. Les échéances
    listées sont celles à traiter et celles qui tombent dans les 31 jours qui viennent."""
    mois = mois_ecoule(auj)
    debut = date.fromisoformat(mois + "-01")
    fin = auj.replace(day=1) - timedelta(days=1)

    def echeances():
        with db() as c:
            return [{"titre": e["titre"], "jours": e["jours_restants"], "date": e["date_echeance"]}
                    for e in lire_echeances(c, auj) if e["a_rappeler"] or e["jours_restants"] <= 31]

    def lectures_():
        l = _donnees_lectures(debut, fin, auj)
        return l and {**l, "periode": "ce mois-ci"}

    d = {"mois": mois,
         "budget": _section("budget", lambda: _donnees_budget_mois(mois, auj)),
         "bourse": _section("bourse", lambda: _donnees_bourse_mois(mois)),
         "lectures": _section("lectures", lectures_),
         "dettes": _section("dettes", lambda: _donnees_dettes(auj)),
         "echeances": _section("echeances", echeances, [])}
    return {"sujet": f"📊 Ton mois de {MOIS_LONGS[debut.month - 1]} {debut.year}",
            "texte": rendre_texte_mois(d), "telegram": rendre_telegram_mois(d), "html": rendre_email_mois(d), "patrimoine": None}


# ---------------------------------------------------------------- bilan de l'année : données
def _donnees_budget_annee(annee: int, auj: date) -> dict:
    a = calculer_resume_annuel(annee, auj)
    with db() as c:
        prec = c.execute("SELECT COALESCE(SUM(montant),0) t FROM depenses WHERE date LIKE %s", (f"{annee - 1:04d}-%",)).fetchone()["t"]
        top = c.execute("SELECT date,categorie,description,montant FROM depenses WHERE date LIKE %s "
                        "ORDER BY montant DESC LIMIT 5", (f"{annee:04d}-%",)).fetchall()
    dep = a["total_depenses"]
    categories = [{"cat": c["cat"], "reel": c["total"], "budget": c["budget_annuel"]} for c in a["categories"]]
    return {
        "dep": dep, "rev": a["total_revenus"], "epargne": a["epargne"], "taux": a["taux_epargne"],
        "objectif": a["objectif_epargne"], "nb_mois_objectif": a["nb_mois_objectif"], "nb_mois_actifs": a["nb_mois_actifs"],
        "moyenne_dep": a["moyenne_dep_mois"], "dep_prec": prec,
        "variation_pct": round((dep - prec) / prec * 100) if prec else None,
        "mois": [{"m": m["m"], "dep": m["dep"]} for m in a["par_mois"]],
        "meilleur": a["meilleur_mois"], "pire": a["pire_mois"],
        "categories": categories,
        "nb_depassees": sum(1 for c in categories if c["budget"] and c["reel"] > c["budget"]),
        "top": [{"date": date.fromisoformat(t["date"]), "categorie": t["categorie"],
                 "description": (t["description"] or "").strip(), "montant": t["montant"]} for t in top],
    }


def _donnees_bourse_annee(annee: int) -> Optional[dict]:
    d = bourse.obtenir_dashboard(annee=annee)
    if not d.patrimoine_total and not d.apports_nets:
        return None
    return {"patrimoine": d.patrimoine_total, "resultat": d.resultat_net_periode, "dividendes": d.dividendes_nets,
            "apports": d.apports_periode, "retraits": d.retraits_periode, "perf": d.performance_globale,
            "perf_pct": d.performance_globale_pct if d.apports_nets > 0 else None}


def _donnees_lectures_annee(annee: int, auj: date) -> Optional[dict]:
    b = lectures.calculer_bilan(annee, auj)
    if not b["nb_livres"]:
        return None
    return {"nb": b["nb_livres"], "pages": b["nb_pages"], "objectif": b["objectif_annuel"],
            "mieux_note": b["mieux_note"]["titre"] if b["mieux_note"] else None,
            "auteur": b["auteurs"][0]["auteur"] if b["auteurs"] else None}


def resume_annuel(auj: date) -> dict:
    """Bilan de la dernière année terminée : {"sujet", "texte", "telegram", "html"}."""
    annee = auj.year - 1
    d = {"annee": annee,
         "budget": _section("budget", lambda: _donnees_budget_annee(annee, auj)),
         "bourse": _section("bourse", lambda: _donnees_bourse_annee(annee)),
         "lectures": _section("lectures", lambda: _donnees_lectures_annee(annee, auj)),
         "patrimoine": _section("patrimoine", lambda: patrimoine.calculer_patrimoine(auj)["total"])}
    return {"sujet": f"📊 Ton année {annee}", "texte": rendre_texte_annee(d), "telegram": rendre_telegram_annee(d),
            "html": rendre_email_annee(d), "patrimoine": None}


def _envoyer_resume(r: dict) -> list:
    return envoyer(r["sujet"], r["texte"], html=r["html"], telegram=r["telegram"])


# ---------------------------------------------------------------- mémoire entre deux exécutions (table params)
def _param(cle: str) -> Optional[float]:
    with db() as c:
        row = c.execute("SELECT valeur FROM params WHERE cle=%s", (cle,)).fetchone()
    return row["valeur"] if row else None


def _ecrire_param(cle: str, valeur: float):
    with db() as c:
        c.execute("""INSERT INTO params(cle,valeur) VALUES(%s,%s)
                     ON CONFLICT (cle) DO UPDATE SET valeur=EXCLUDED.valeur""", (cle, valeur))


# ---------------------------------------------------------------- routes (session requise)
@router.get("/etat")
def etat():
    """Ce qui est configuré côté serveur (aucun secret n'est renvoyé)."""
    return {"canaux": canaux(), "cron": bool(CRON_SECRET)}


def _resume(periode: str, auj: date) -> dict:
    if periode == "annee":
        return resume_annuel(auj)
    return resume_mensuel(auj) if periode == "mois" else resume_hebdo(auj, _param("resume_hebdo_patrimoine"))


@router.get("/apercu")
def apercu(periode: Literal["semaine", "mois", "annee"] = "semaine"):
    """Ce qui serait envoyé maintenant : rappels du jour, et résumé de la dernière semaine
    terminée ou bilan du dernier mois terminé."""
    auj = aujourdhui()
    r = _resume(periode, auj)
    return {"rappels": "\n".join(rappels_du_jour(auj)), "sujet": r["sujet"], "resume": r["texte"], "html": r["html"]}


@router.post("/envoyer")
def envoyer_maintenant(periode: Literal["semaine", "mois", "annee"] = "semaine"):
    """Envoie tout de suite le résumé choisi (bouton de test des Paramètres) ; ne compte pas comme un envoi planifié."""
    r = _resume(periode, aujourdhui())
    try:
        return {"canaux": _envoyer_resume(r)}
    except EnvoiImpossible as e:
        raise HTTPException(502, f"Envoi impossible — {e}")


# ---------------------------------------------------------------- tâche planifiée
@cron.get("/quotidien")
def tache_quotidienne(force: bool = False, authorization: Optional[str] = Header(default=None)):
    """Rappels du jour, plus le résumé de la semaine le lundi, le bilan du mois le 1er (avec une copie
    de sauvegarde en pièce jointe) et le bilan de l'année le 1er janvier. Au plus un envoi par jour :
    un second appel le même jour ne renvoie rien (`force=true` pour passer outre)."""
    if not CRON_SECRET:
        raise HTTPException(503, "CRON_SECRET non configuré")
    if not secrets.compare_digest((authorization or "").encode(), f"Bearer {CRON_SECRET}".encode()):
        raise HTTPException(401, "Non autorisé")
    auj = aujourdhui()
    if not force and _param("cron_dernier_jour") == auj.toordinal():
        return {"etat": "deja_fait"}
    if not canaux():
        return {"etat": "aucun_canal"}

    try:
        bourse._actualiser_cours(force=False)   # cours du jour pour la valeur du portefeuille
    except Exception as e:
        print(f"[rappels] cours non actualisés — {e!r}", flush=True)

    envoyes = []
    try:
        lignes = rappels_du_jour(auj)
        if lignes:
            envoyer("⏰ Carnet — rappels du jour", "\n".join(lignes))
            envoyes.append("rappels")
        if auj.day == 1 and auj.month == 1:
            _envoyer_resume(resume_annuel(auj))
            envoyes.append("annee")
        if auj.day == 1:
            _envoyer_resume(resume_mensuel(auj))
            envoyes.append("mois")
        if auj.weekday() == 0:
            r = resume_hebdo(auj, _param("resume_hebdo_patrimoine"))
            _envoyer_resume(r)
            envoyes.append("resume")
            if r["patrimoine"] is not None:
                _ecrire_param("resume_hebdo_patrimoine", r["patrimoine"])
    except EnvoiImpossible as e:
        # Jour non marqué comme fait : un nouvel appel réessaiera
        raise HTTPException(502, f"Envoi impossible — {e}")
    if auj.day == 1 and envoyer_sauvegarde():
        envoyes.append("sauvegarde")
    _ecrire_param("cron_dernier_jour", auj.toordinal())
    return {"etat": "ok", "envoyes": envoyes}


def envoyer_sauvegarde() -> bool:
    """Copie mensuelle de toutes les données, en pièce jointe. Un échec est journalisé sans
    faire échouer la tâche : les résumés du jour sont déjà partis."""
    try:
        nom, contenu = sauvegarde.fichier_compresse()
        envoyer_fichier("💾 Carnet — sauvegarde du mois",
                        "Copie complète de tes données. Garde ce fichier : il se restaure avec "
                        "scripts/restaurer_sauvegarde.py.", nom, contenu)
        return True
    except Exception as e:
        print(f"[rappels] sauvegarde mensuelle non envoyée — {e!r}", flush=True)
        return False
