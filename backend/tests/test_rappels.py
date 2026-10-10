# -*- coding: utf-8 -*-
"""
Tests des rappels et du résumé hebdomadaire : jours où un rappel part, lignes du jour,
semaine couverte par le résumé, contenu du résumé, protection de la tâche planifiée.
Aucun message n'est réellement envoyé. Utilise la base configurée dans .env (préfixe ZZTEST).

Lancement :
    cd backend
    pytest tests/test_rappels.py -v
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

import messagerie
import resume_rendu
import sauvegarde
from database import db
from schemas import DetteIn, EcheanceIn, RemboursementIn
from routes import rappels
from routes.carnet import ajouter_dette, ajouter_echeance, ajouter_remboursement
from routes.rappels import jours_de_rappel, rappels_du_jour, resume_hebdo, semaine_ecoulee, tache_quotidienne

PREFIXE = "ZZTEST"
AUJ = date(1901, 6, 10)   # un lundi, dans une année sans données réelles


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM dettes WHERE personne LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM echeances WHERE titre LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _lignes(auj=AUJ):
    return [l for l in rappels_du_jour(auj) if PREFIXE in l]


def test_jours_de_rappel():
    assert jours_de_rappel(30) == {30, 7, 1, 0}
    assert jours_de_rappel(7) == {7, 1, 0}
    assert jours_de_rappel(3) == {3, 1, 0}
    assert jours_de_rappel(0) == {0}


def test_rappel_d_echeance_seulement_les_jours_prevus():
    ajouter_echeance(EcheanceIn(titre=f"{PREFIXE} Assurance", date_echeance=date(1901, 7, 10), rappel_jours=30))
    assert len(_lignes(date(1901, 6, 10))) == 1 and "dans 30 jours" in _lignes(date(1901, 6, 10))[0]
    assert _lignes(date(1901, 6, 11)) == []                      # J−29 : rien
    assert "dans 7 jours" in _lignes(date(1901, 7, 3))[0]
    assert "demain" in _lignes(date(1901, 7, 9))[0]
    assert "aujourd'hui" in _lignes(date(1901, 7, 10))[0]
    assert _lignes(date(1901, 7, 11)) == []                      # en retard : repris dans le résumé du lundi


def test_rappel_de_remboursement_tant_que_la_dette_n_est_pas_soldee():
    d = ajouter_dette(DetteIn(sens="pret", personne=f"{PREFIXE} Ali", montant=500,
                              date_operation=date(1901, 5, 1), echeance=date(1901, 6, 13)))
    assert "dans 3 jours" in _lignes()[0] and "500 DH restants" in _lignes()[0]
    assert _lignes(date(1901, 6, 12)) == []
    ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(1901, 6, 1), montant=500))
    assert _lignes() == []


def test_semaine_ecoulee():
    assert semaine_ecoulee(date(2026, 10, 12)) == (date(2026, 10, 5), date(2026, 10, 11))   # un lundi
    assert semaine_ecoulee(date(2026, 10, 18)) == (date(2026, 10, 5), date(2026, 10, 11))   # le dimanche suivant


def test_resume_hebdo_contient_le_carnet():
    ajouter_dette(DetteIn(sens="pret", personne=f"{PREFIXE} Ali", montant=500,
                          date_operation=date(1901, 5, 1), echeance=date(1901, 6, 1)))
    ajouter_echeance(EcheanceIn(titre=f"{PREFIXE} Passeport", date_echeance=date(1901, 6, 5), rappel_jours=7))
    r = resume_hebdo(AUJ)
    assert r["sujet"].endswith("semaine du 3 juin au 9 juin")
    assert "💸 Budget" in r["texte"] and "🤝 Dettes et prêts" in r["texte"]
    assert f"Prêt à {PREFIXE} Ali (500 DH restants) : échéance dépassée (1 juin)" in r["texte"]
    assert f"{PREFIXE} Passeport : en retard de 5 jours (5 juin)" in r["texte"]
    # Les trois mises en forme portent les mêmes informations
    for version in (r["telegram"], r["html"]):
        assert f"{PREFIXE} Passeport" in version and "en retard de 5 jours" in version and "500 DH restants" in version


def test_une_section_en_erreur_n_empeche_pas_le_resume(monkeypatch):
    def casse(*_):
        raise RuntimeError("panne")
    monkeypatch.setattr(rappels, "_donnees_bourse", casse)
    r = resume_hebdo(AUJ)
    assert "💸 Budget" in r["texte"] and "Bourse" not in r["texte"] and r["patrimoine"] is None


def test_tache_quotidienne_exige_le_secret(monkeypatch):
    monkeypatch.setattr(rappels, "CRON_SECRET", "")
    with pytest.raises(HTTPException) as exc:
        tache_quotidienne(authorization="Bearer x")
    assert exc.value.status_code == 503
    monkeypatch.setattr(rappels, "CRON_SECRET", "secret-de-test")
    for entete in (None, "secret-de-test", "Bearer autre"):
        with pytest.raises(HTTPException) as exc:
            tache_quotidienne(authorization=entete)
        assert exc.value.status_code == 401


def test_tache_quotidienne_envoie_une_seule_fois_par_jour(monkeypatch):
    envois = []
    memoire = {}
    monkeypatch.setattr(rappels, "CRON_SECRET", "secret-de-test")
    monkeypatch.setattr(rappels, "aujourdhui", lambda: AUJ)
    monkeypatch.setattr(rappels, "canaux", lambda: ["telegram"])
    monkeypatch.setattr(rappels, "envoyer", lambda sujet, texte, **_: envois.append(sujet) or ["telegram"])
    monkeypatch.setattr(rappels, "_param", memoire.get)
    monkeypatch.setattr(rappels, "_ecrire_param", memoire.__setitem__)
    monkeypatch.setattr(rappels.bourse, "_actualiser_cours", lambda force: None)
    ajouter_echeance(EcheanceIn(titre=f"{PREFIXE} Vignette", date_echeance=AUJ, rappel_jours=0))

    r = tache_quotidienne(authorization="Bearer secret-de-test")
    assert r == {"etat": "ok", "envoyes": ["rappels", "resume"]}      # AUJ est un lundi
    assert len(envois) == 2 and memoire["cron_dernier_jour"] == AUJ.toordinal()
    assert tache_quotidienne(authorization="Bearer secret-de-test") == {"etat": "deja_fait"}
    assert len(envois) == 2


def test_bilan_du_mois_envoye_le_premier(monkeypatch):
    envois = []
    memoire = {}
    monkeypatch.setattr(rappels, "CRON_SECRET", "secret-de-test")
    monkeypatch.setattr(rappels, "canaux", lambda: ["telegram"])
    monkeypatch.setattr(rappels, "envoyer", lambda sujet, texte, **_: envois.append(sujet) or ["telegram"])
    monkeypatch.setattr(rappels, "_param", memoire.get)
    monkeypatch.setattr(rappels, "_ecrire_param", memoire.__setitem__)
    monkeypatch.setattr(rappels.bourse, "_actualiser_cours", lambda force: None)
    fichiers = []
    monkeypatch.setattr(rappels, "envoyer_fichier", lambda sujet, texte, nom, contenu: fichiers.append((nom, contenu)) or ["telegram"])
    monkeypatch.setattr(rappels, "aujourdhui", lambda: date(1901, 7, 1))     # un lundi qui est aussi un 1er
    assert tache_quotidienne(authorization="Bearer secret-de-test")["envoyes"] == ["mois", "resume", "sauvegarde"]
    assert envois[0].endswith("Ton mois de juin 1901")
    # La copie mensuelle : un fichier compressé qui se relit comme une sauvegarde
    nom, contenu = fichiers[0]
    assert nom.endswith(".json.gz") and "depenses" in sauvegarde.lire(contenu)["tables"]
    monkeypatch.setattr(rappels, "aujourdhui", lambda: date(1901, 8, 1))     # un jeudi
    assert tache_quotidienne(authorization="Bearer secret-de-test")["envoyes"] == ["mois", "sauvegarde"]
    # Le 1er janvier : le bilan de l'année d'abord, puis celui de décembre
    monkeypatch.setattr(rappels, "aujourdhui", lambda: date(1902, 1, 1))
    assert tache_quotidienne(authorization="Bearer secret-de-test")["envoyes"] == ["annee", "mois", "sauvegarde"]
    assert envois[-2].endswith("Ton année 1901") and envois[-1].endswith("Ton mois de décembre 1901")
    # Une sauvegarde qui échoue n'empêche pas le reste
    def panne(*_):
        raise messagerie.EnvoiImpossible("injoignable")
    monkeypatch.setattr(rappels, "envoyer_fichier", panne)
    monkeypatch.setattr(rappels, "aujourdhui", lambda: date(1902, 2, 1))
    assert tache_quotidienne(authorization="Bearer secret-de-test")["envoyes"] == ["mois"]
    monkeypatch.setattr(rappels, "aujourdhui", lambda: date(1901, 8, 2))
    assert tache_quotidienne(authorization="Bearer secret-de-test")["envoyes"] == []


def test_tache_quotidienne_reessayable_apres_un_echec(monkeypatch):
    memoire = {}

    def echec(*_, **__):
        raise messagerie.EnvoiImpossible("telegram : injoignable")
    monkeypatch.setattr(rappels, "CRON_SECRET", "secret-de-test")
    monkeypatch.setattr(rappels, "aujourdhui", lambda: AUJ)
    monkeypatch.setattr(rappels, "canaux", lambda: ["telegram"])
    monkeypatch.setattr(rappels, "envoyer", echec)
    monkeypatch.setattr(rappels, "_param", memoire.get)
    monkeypatch.setattr(rappels, "_ecrire_param", memoire.__setitem__)
    monkeypatch.setattr(rappels.bourse, "_actualiser_cours", lambda force: None)
    with pytest.raises(HTTPException) as exc:
        tache_quotidienne(authorization="Bearer secret-de-test")
    assert exc.value.status_code == 502 and "cron_dernier_jour" not in memoire


def test_envoyer_sans_canal(monkeypatch):
    monkeypatch.setattr(messagerie, "canaux", lambda: [])
    with pytest.raises(messagerie.EnvoiImpossible):
        messagerie.envoyer("sujet", "texte")


def test_un_canal_en_echec_n_empeche_pas_l_autre(monkeypatch):
    def echec(*_):
        raise RuntimeError("injoignable")
    recus = []
    monkeypatch.setattr(messagerie, "canaux", lambda: ["telegram", "email"])
    monkeypatch.setitem(messagerie._ENVOIS, "telegram", echec)
    monkeypatch.setitem(messagerie._ENVOIS, "email", lambda sujet, texte, *_: recus.append(sujet))
    assert messagerie.envoyer("sujet", "texte") == ["email"]
    assert recus == ["sujet"]


# ---------------------------------------------------------------- mise en forme du résumé
def _semaine(**budget):
    """Données d'une semaine type (du lundi 5 au dimanche 11 octobre 2026)."""
    jours = [{"date": date(2026, 10, 5 + i), "dep": d} for i, d in enumerate([120, 0, 450, 80, 0, 300, 50])]
    b = {"dep": 1000, "rev": 0, "epargne": -1000, "dep_prec": 800, "variation_pct": 25, "budget_hebdo": 900,
         "dep_var": 1000, "reste": -100, "jours": jours, "jour_max": jours[2], "jours_sans": 2,
         "categories": [{"cat": "Courses & <Marché>", "montant": 600}, {"cat": "Restaurants", "montant": 400}],
         "plus_grosse": {"date": date(2026, 10, 7), "categorie": "Courses", "description": "Marjane <promo>", "montant": 450},
         "mois": None, **budget}
    return {"lundi": date(2026, 10, 5), "dimanche": date(2026, 10, 11), "budget": b, "bourse": None,
            "lectures": None, "dettes": None, "echeances": []}


def test_verdict_de_la_semaine():
    assert resume_rendu.verdict(_semaine()["budget"]) == "Budget de la semaine dépassé de 100 DH."
    assert resume_rendu.verdict(_semaine(reste=250)["budget"]) == "Semaine sous le budget : 250 DH de marge."
    assert resume_rendu.verdict(_semaine(dep=0, rev=0)["budget"]) == "Aucune opération saisie cette semaine."
    assert resume_rendu.verdict(_semaine(budget_hebdo=0)["budget"]) == "1 000 DH dépensés cette semaine."


def test_resume_raconte_la_semaine():
    d = _semaine()
    texte, telegram, html = resume_rendu.rendre_texte(d), resume_rendu.rendre_telegram(d), resume_rendu.rendre_email(d)
    for version in (texte, telegram, html):
        assert "▲ 25 %" in version                                   # comparaison avec la semaine d'avant
        assert "mercredi" in version and "450 DH" in version         # plus grosse dépense, jour le plus dépensier
        assert "2 jours sans dépense" in version
    assert "Lun" in telegram and "Dim" in telegram and "<pre>" in telegram   # barres jour par jour
    assert "5 oct. → 11 oct." in html


def test_le_texte_saisi_est_echappe_dans_les_versions_html():
    d = _semaine()
    for version in (resume_rendu.rendre_telegram(d), resume_rendu.rendre_email(d)):
        assert "<promo>" not in version and "&lt;promo&gt;" in version
        assert "<Marché>" not in version


def test_semaine_sans_depense():
    jours = [{"date": date(2026, 10, 5 + i), "dep": 0} for i in range(7)]
    d = _semaine(dep=0, rev=0, epargne=0, dep_var=0, reste=900, jours=jours, jour_max=None, jours_sans=7,
                 categories=[], plus_grosse=None, variation_pct=None)
    for rendre in (resume_rendu.rendre_texte, resume_rendu.rendre_telegram, resume_rendu.rendre_email):
        assert "Aucune opération saisie cette semaine." in rendre(d)
    assert "Jour par jour" not in resume_rendu.rendre_email(d)


def test_telegram_mise_en_forme_refusee_repasse_en_texte_brut(monkeypatch):
    import urllib.error
    envois = []

    def poster(champs):
        envois.append(champs)
        if champs.get("parse_mode"):
            raise urllib.error.HTTPError("url", 400, "Bad Request", None, None)
    monkeypatch.setattr(messagerie, "_poster_telegram", poster)
    messagerie._telegram("sujet", "texte brut", telegram="<b>mal fermé")
    assert [bool(e.get("parse_mode")) for e in envois] == [True, False] and "texte brut" in envois[1]["text"]


# ---------------------------------------------------------------- bilan du mois
def _mois(**budget):
    b = {"dep": 6200, "rev": 12000, "epargne": 5800, "taux": 48.3, "objectif": 5000, "budget": 6600, "dep_prec": 5000,
         "variation_pct": 24,
         "semaines": [{"libelle": "1–7", "dep": 3400}, {"libelle": "8–14", "dep": 900}, {"libelle": "15–21", "dep": 1100},
                      {"libelle": "22–28", "dep": 600}, {"libelle": "29–30", "dep": 200}],
         "categories": [{"cat": "Loyer", "budget": 3000, "reel": 3000, "pct": 100},
                        {"cat": "Restaurants <bis>", "budget": 200, "reel": 450, "pct": 225},
                        {"cat": "Divers", "budget": 0, "reel": 120, "pct": 0}],
         "nb_depassees": 1,
         "top": [{"date": date(2026, 9, 1), "categorie": "Loyer", "description": "", "montant": 3000},
                 {"date": date(2026, 9, 12), "categorie": "Restaurants <bis>", "description": "Anniversaire", "montant": 300}],
         "evolution": [{"m": "2026-08", "dep": 5000}, {"m": "2026-09", "dep": 6200}], **budget}
    return {"mois": "2026-09", "budget": b, "bourse": None, "lectures": None, "dettes": None, "echeances": []}


def test_mois_ecoule():
    assert rappels.mois_ecoule(date(2026, 10, 1)) == "2026-09"
    assert rappels.mois_ecoule(date(2026, 1, 15)) == "2025-12"


def test_verdict_du_mois():
    v = resume_rendu.verdict_mois
    assert v(_mois()["budget"]) == "Objectif d'épargne atteint : 5 800 DH mis de côté."
    assert v(_mois(epargne=3000)["budget"]) == "3 000 DH mis de côté, il manquait 2 000 DH pour l'objectif."
    assert v(_mois(epargne=-400)["budget"]) == "Mois dans le rouge : 400 DH dépensés de plus que reçus."
    assert v(_mois(dep=0, rev=0)["budget"]) == "Aucune opération saisie ce mois-ci."


def test_bilan_du_mois_dans_les_trois_versions():
    d = _mois()
    texte, telegram, html = resume_rendu.rendre_texte_mois(d), resume_rendu.rendre_telegram_mois(d), resume_rendu.rendre_email_mois(d)
    for version in (texte, telegram, html):
        assert "▲ 24 %" in version and "1 catégorie au-dessus de son budget" in version
        assert "Anniversaire" in version and "5 800 DH" in version
    assert "Septembre 2026" in html and "dépassé" in html and "sept. 26" in html
    assert "8–14" in telegram
    for version in (telegram, html):
        assert "<bis>" not in version


def test_resume_mensuel_sur_la_base():
    ajouter_echeance(EcheanceIn(titre=f"{PREFIXE} Vignette", date_echeance=date(1901, 7, 20), rappel_jours=3))
    r = rappels.resume_mensuel(date(1901, 7, 1))
    assert r["sujet"].endswith("Ton mois de juin 1901")
    # Pas encore dans sa fenêtre de rappel, mais elle tombe dans le mois qui commence
    assert f"{PREFIXE} Vignette : dans 19 jours (20 juil.)" in r["texte"]
    assert f"{PREFIXE} Vignette" in r["telegram"] and f"{PREFIXE} Vignette" in r["html"]


def test_les_lignes_alignees_de_telegram_tiennent_sur_un_telephone():
    import re
    for message in (resume_rendu.rendre_telegram(_semaine()), resume_rendu.rendre_telegram_mois(_mois())):
        for bloc in re.findall(r"<pre>(.*?)</pre>", message, re.S):
            assert all(len(resume_rendu.unescape(l)) <= resume_rendu.LARGEUR_TG for l in bloc.split("\n"))


# ---------------------------------------------------------------- bilan de l'année
def _annee(**budget):
    b = {"dep": 70000, "rev": 130000, "epargne": 60000, "taux": 46.2, "objectif": 5000, "nb_mois_objectif": 7, "nb_mois_actifs": 12,
         "moyenne_dep": 5833, "dep_prec": 56000, "variation_pct": 25,
         "mois": [{"m": m, "dep": 5000 + 400 * m} for m in range(1, 13)],
         "meilleur": {"m": 3, "ep": 8000}, "pire": {"m": 8, "ep": -1200},
         "categories": [{"cat": "Loyer", "budget": 36000, "reel": 36000}, {"cat": "Voyages <été>", "budget": 6000, "reel": 9500}],
         "nb_depassees": 1,
         "top": [{"date": date(2026, 8, 3), "categorie": "Voyages <été>", "description": "Billets d'avion", "montant": 4200}], **budget}
    return {"annee": 2026, "budget": b, "bourse": None,
            "lectures": {"nb": 18, "pages": 5400, "objectif": 24, "mieux_note": "Sapiens", "auteur": "Camus"}, "patrimoine": 215000}


def test_verdict_de_l_annee():
    v = resume_rendu.verdict_annee
    assert v(_annee()["budget"], 2026) == "60 000 DH mis de côté en 2026, soit 46,2 % de tes revenus."
    assert v(_annee(epargne=-3000)["budget"], 2026) == "Année dans le rouge : 3 000 DH dépensés de plus que reçus."
    assert v(_annee(dep=0, rev=0)["budget"], 2026) == "Aucune opération saisie en 2026."


def test_bilan_de_l_annee_dans_les_trois_versions():
    d = _annee()
    texte, telegram, html = resume_rendu.rendre_texte_annee(d), resume_rendu.rendre_telegram_annee(d), resume_rendu.rendre_email_annee(d)
    for version in (texte, telegram, html):
        assert "▲ 25 %" in version and "Meilleur mois : mars" in version and "Mois le plus difficile : août" in version
        assert "Billets d'avion" in version or "Billets d&#x27;avion" in version
        assert "Sapiens" in version and "215 000 DH" in version
    assert "Ton année 2026" in html and "7 / 12" in html and "déc." in html
    assert "janv" in telegram and "<été>" not in telegram and "<été>" not in html


def test_resume_annuel_sur_la_base():
    r = rappels.resume_annuel(date(1902, 1, 1))
    assert r["sujet"].endswith("Ton année 1901") and "Aucune opération saisie en 1901." in r["texte"]
