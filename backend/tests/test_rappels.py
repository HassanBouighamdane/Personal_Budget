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


def test_une_section_en_erreur_n_empeche_pas_le_resume(monkeypatch):
    def casse(*_):
        raise RuntimeError("panne")
    monkeypatch.setattr(rappels, "_section_bourse", casse)
    assert "💸 Budget" in resume_hebdo(AUJ)["texte"]


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
    monkeypatch.setattr(rappels, "envoyer", lambda sujet, texte: envois.append(sujet) or ["telegram"])
    monkeypatch.setattr(rappels, "_param", memoire.get)
    monkeypatch.setattr(rappels, "_ecrire_param", memoire.__setitem__)
    monkeypatch.setattr(rappels.bourse, "_actualiser_cours", lambda force: None)
    ajouter_echeance(EcheanceIn(titre=f"{PREFIXE} Vignette", date_echeance=AUJ, rappel_jours=0))

    r = tache_quotidienne(authorization="Bearer secret-de-test")
    assert r == {"etat": "ok", "envoyes": ["rappels", "resume"]}      # AUJ est un lundi
    assert len(envois) == 2 and memoire["cron_dernier_jour"] == AUJ.toordinal()
    assert tache_quotidienne(authorization="Bearer secret-de-test") == {"etat": "deja_fait"}
    assert len(envois) == 2


def test_tache_quotidienne_reessayable_apres_un_echec(monkeypatch):
    memoire = {}

    def echec(*_):
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
    monkeypatch.setitem(messagerie._ENVOIS, "email", lambda sujet, texte: recus.append(sujet))
    assert messagerie.envoyer("sujet", "texte") == ["email"]
    assert recus == ["sujet"]
