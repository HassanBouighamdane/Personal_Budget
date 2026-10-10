# -*- coding: utf-8 -*-
"""
Rappels et résumé hebdomadaire, envoyés par Telegram ou e-mail (cf. messagerie.py).

Une seule tâche planifiée, GET /api/cron/quotidien, appelée chaque matin (Vercel Cron, cf.
vercel.json) : elle envoie les rappels du jour (échéances, remboursements attendus) et, le
lundi, le résumé de la semaine écoulée (Budget, Bourse, Lectures, Carnet).

Les textes sont construits par des fonctions qui reçoivent la date du jour en paramètre,
pour que les tests la fixent.
"""
import secrets
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from config import CRON_SECRET, aujourdhui
from database import db
from messagerie import EnvoiImpossible, canaux, envoyer
from securite import utilisateur_courant
from routes import bourse, lectures
from routes.carnet import lire_dettes, lire_echeances
from routes.rapports import calculer_resume, calculer_resume_semaine

router = APIRouter(prefix="/api/rappels", tags=["rappels"], dependencies=[Depends(utilisateur_courant)])
# Appelé par le planificateur, sans session : protégé par CRON_SECRET
cron = APIRouter(prefix="/api/cron", tags=["cron"])

MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
MOIS_LONGS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
              "novembre", "décembre"]
# Un remboursement attendu est rappelé 3 jours avant, puis le jour même
RAPPEL_DETTE_JOURS = (3, 0)


def _dh(v) -> str:
    return f"{round(float(v)):,}".replace(",", " ").replace("-", "−") + " DH"


def _jour(d: date) -> str:
    return f"{d.day} {MOIS_COURTS[d.month - 1]}"


def _delai(jours: int) -> str:
    if jours < 0:
        return f"en retard de {-jours} jour{'s' if jours < -1 else ''}"
    return {0: "aujourd'hui", 1: "demain"}.get(jours, f"dans {jours} jours")


def _dette_libelle(d: dict) -> str:
    qui = f"Prêt à {d['personne']}" if d["sens"] == "pret" else f"Emprunt auprès de {d['personne']}"
    return f"{qui} ({_dh(d['reste'])} restants)"


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
    lignes = [f"• {e['titre']} : {_delai(e['jours_restants'])} ({_jour(e['date_echeance'])})"
              for e in echeances if e["jours_restants"] in jours_de_rappel(e["rappel_jours"])]
    for d in dettes:
        if d["reste"] > 0 and d["echeance"] and (d["echeance"] - auj).days in RAPPEL_DETTE_JOURS:
            lignes.append(f"• {_dette_libelle(d)} : remboursement prévu {_delai((d['echeance'] - auj).days)}")
    return lignes


# ---------------------------------------------------------------- résumé hebdomadaire
def semaine_ecoulee(auj: date) -> tuple:
    """(lundi, dimanche) de la dernière semaine terminée avant `auj`."""
    lundi = auj - timedelta(days=auj.weekday() + 7)
    return lundi, lundi + timedelta(days=6)


def _section_budget(lundi: date, auj: date) -> list:
    s = calculer_resume_semaine(lundi, auj)
    lignes = ["💸 Budget"]
    dep, prec = s["total_depenses"], s["depenses_semaine_precedente"]
    variation = ""
    if prec:
        pct = round((dep - prec) / prec * 100)
        variation = f" ({'▲' if pct > 0 else '▼'} {abs(pct)} % sur la semaine d'avant)" if pct else " (comme la semaine d'avant)"
    lignes.append(f"Dépenses : {_dh(dep)}{variation}")
    if s["total_revenus"]:
        lignes.append(f"Revenus : {_dh(s['total_revenus'])}")
    if s["budget_hebdo"]:
        reste = s["reste_budget_hebdo"]
        etat = f"reste {_dh(reste)}" if reste >= 0 else f"dépassé de {_dh(-reste)}"
        lignes.append(f"Budget variable : {_dh(s['depenses_variables'])} sur {_dh(s['budget_hebdo'])} ({etat})")
    if s["donut"]:
        lignes.append("Top : " + " · ".join(f"{x['cat']} {_dh(x['montant'])}" for x in s["donut"][:3]))

    m = calculer_resume(auj.strftime("%Y-%m"), auj)
    if m["total_depenses"] or m["total_revenus"]:
        ligne = f"{MOIS_LONGS[auj.month - 1].capitalize()} : {_dh(m['total_depenses'])} dépensés"
        if m["budget_total"]:
            ligne += f" sur {_dh(m['budget_total'])} de budget"
        if m["projection_fin_mois"] and auj.day >= 5:   # trop peu de jours avant : projection sans valeur
            ligne += f", projection {_dh(m['projection_fin_mois'])}"
        lignes.append(ligne)
    return lignes


def _section_bourse(patrimoine_precedent: Optional[float]) -> tuple:
    """(lignes, patrimoine actuel). `patrimoine_precedent` : valeur au résumé précédent, pour la variation."""
    d = bourse.obtenir_dashboard()
    if not d.patrimoine_total and not d.apports_nets:
        return [], None
    lignes = ["📈 Bourse", f"Portefeuille : {_dh(d.patrimoine_total)} "
                          f"(titres {_dh(d.valeur_marche)}, espèces {_dh(d.especes_disponibles)})"]
    if patrimoine_precedent:
        ecart = d.patrimoine_total - patrimoine_precedent
        lignes.append(f"Depuis le dernier résumé : {'+' if ecart >= 0 else '−'}{_dh(abs(ecart))} (apports et retraits compris)")
    signe = "+" if d.performance_globale >= 0 else "−"
    ligne = f"Performance globale : {signe}{_dh(abs(d.performance_globale))}"
    if d.apports_nets > 0:   # sans apport saisi, le pourcentage n'a pas de base
        ligne += f" ({signe}{abs(d.performance_globale_pct) * 100:.1f} %)".replace(".", ",")
    lignes.append(ligne)
    return lignes, d.patrimoine_total


def _section_lectures(lundi: date, dimanche: date, auj: date) -> list:
    with db() as c:
        finis = c.execute("SELECT titre, pages FROM lectures_livres WHERE date_fin BETWEEN %s AND %s ORDER BY date_fin",
                          (lundi, dimanche)).fetchall()
        en_cours = c.execute("SELECT titre FROM lectures_a_lire WHERE date_debut IS NOT NULL "
                             "ORDER BY date_debut DESC").fetchall()
    bilan = lectures.calculer_bilan(auj.year, auj)
    if not finis and not en_cours and not bilan["nb_livres"]:
        return []
    lignes = ["📚 Lectures"]
    if finis:
        pages = sum(l["pages"] or 0 for l in finis)
        lignes.append("Terminé cette semaine : " + ", ".join(l["titre"] for l in finis)
                      + (f" ({pages} pages)" if pages else ""))
    if en_cours:
        lignes.append("En cours : " + ", ".join(l["titre"] for l in en_cours))
    annee = f"{auj.year} : {bilan['nb_livres']} livre{'s' if bilan['nb_livres'] > 1 else ''}"
    if bilan["objectif_annuel"]:
        annee += f" sur {bilan['objectif_annuel']}"
    lignes.append(annee)
    return lignes


def _section_carnet(auj: date) -> list:
    with db() as c:
        dettes = [d for d in lire_dettes(c) if d["reste"] > 0]
        echeances = [e for e in lire_echeances(c, auj) if e["a_rappeler"]]
    lignes = []
    if dettes:
        on_me_doit = sum(d["reste"] for d in dettes if d["sens"] == "pret")
        je_dois = sum(d["reste"] for d in dettes if d["sens"] == "emprunt")
        lignes += ["🤝 Dettes et prêts", f"On te doit : {_dh(on_me_doit)} · Tu dois : {_dh(je_dois)}"]
        lignes += [f"• {_dette_libelle(d)} : échéance dépassée ({_jour(d['echeance'])})"
                   for d in dettes if d["echeance"] and d["echeance"] < auj]
    if echeances:
        if lignes:
            lignes.append("")
        lignes.append("⏰ Échéances")
        lignes += [f"• {e['titre']} : {_delai(e['jours_restants'])} ({_jour(e['date_echeance'])})" for e in echeances]
    return lignes


def resume_hebdo(auj: date, patrimoine_precedent: Optional[float] = None) -> dict:
    """Résumé de la dernière semaine terminée : {"sujet", "texte", "patrimoine"}. Une section
    qui échoue est laissée de côté (un souci Bourse ne prive pas du résumé du Budget)."""
    lundi, dimanche = semaine_ecoulee(auj)
    patrimoine = None

    def bourse_():
        nonlocal patrimoine
        lignes, patrimoine = _section_bourse(patrimoine_precedent)
        return lignes

    sections = []
    for nom, construire in (("budget", lambda: _section_budget(lundi, auj)), ("bourse", bourse_),
                            ("lectures", lambda: _section_lectures(lundi, dimanche, auj)),
                            ("carnet", lambda: _section_carnet(auj))):
        try:
            lignes = construire()
        except Exception as e:
            print(f"[rappels] section {nom} ignorée — {e!r}", flush=True)
            continue
        if lignes:
            sections.append("\n".join(lignes))
    return {"sujet": f"📊 Mon Budget — semaine du {_jour(lundi)} au {_jour(dimanche)}",
            "texte": "\n\n".join(sections), "patrimoine": patrimoine}


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


@router.get("/apercu")
def apercu():
    """Ce qui serait envoyé maintenant : rappels du jour et résumé de la dernière semaine terminée."""
    auj = aujourdhui()
    r = resume_hebdo(auj, _param("resume_hebdo_patrimoine"))
    return {"rappels": "\n".join(rappels_du_jour(auj)), "sujet": r["sujet"], "resume": r["texte"]}


@router.post("/envoyer")
def envoyer_maintenant():
    """Envoie tout de suite le résumé (bouton de test des Paramètres) ; ne compte pas comme l'envoi du lundi."""
    r = resume_hebdo(aujourdhui(), _param("resume_hebdo_patrimoine"))
    try:
        return {"canaux": envoyer(r["sujet"], r["texte"])}
    except EnvoiImpossible as e:
        raise HTTPException(502, f"Envoi impossible — {e}")


# ---------------------------------------------------------------- tâche planifiée
@cron.get("/quotidien")
def tache_quotidienne(force: bool = False, authorization: Optional[str] = Header(default=None)):
    """Rappels du jour, plus le résumé hebdomadaire le lundi. Au plus un envoi par jour : un second
    appel le même jour ne renvoie rien (`force=true` pour passer outre)."""
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
            envoyer("⏰ Mon Budget — rappels du jour", "\n".join(lignes))
            envoyes.append("rappels")
        if auj.weekday() == 0:
            r = resume_hebdo(auj, _param("resume_hebdo_patrimoine"))
            envoyer(r["sujet"], r["texte"])
            envoyes.append("resume")
            if r["patrimoine"] is not None:
                _ecrire_param("resume_hebdo_patrimoine", r["patrimoine"])
    except EnvoiImpossible as e:
        # Jour non marqué comme fait : un nouvel appel réessaiera
        raise HTTPException(502, f"Envoi impossible — {e}")
    _ecrire_param("cron_dernier_jour", auj.toordinal())
    return {"etat": "ok", "envoyes": envoyes}
