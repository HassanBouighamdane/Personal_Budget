# -*- coding: utf-8 -*-
"""
Tests du patrimoine net, de la réserve de sécurité et de l'estimation de la zakat.
Utilise la base configurée dans .env : les vérifications se font par DIFFÉRENCE (avant/après)
pour ne pas dépendre des données réelles ; les réglages sont sauvegardés puis restaurés.

Lancement :
    cd backend
    pytest tests/test_patrimoine.py -v
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

from config import aujourdhui
from database import db
from schemas import ActifIn, DetteIn, ReglagesPatrimoine
from routes.carnet import ajouter_dette
from routes.patrimoine import (JOURS_HAWL, PARAMS, ajouter_actif, calculer_patrimoine, modifier_actif,
                               modifier_reglages, supprimer_actif)

PREFIXE = "ZZTEST"
AUJ = aujourdhui()


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM actifs WHERE nom LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM dettes WHERE personne LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    with db() as c:
        reglages = c.execute("SELECT cle, valeur FROM params WHERE cle = ANY(%s)", (list(PARAMS),)).fetchall()
    _nettoyer()
    yield
    _nettoyer()
    with db() as c:
        c.execute("DELETE FROM params WHERE cle = ANY(%s)", (list(PARAMS),))
        for r in reglages:
            c.execute("INSERT INTO params(cle, valeur) VALUES(%s,%s)", (r["cle"], r["valeur"]))


def _actif(valeur, verse=0, type="Or / argent", zakat=False, nom="Actif"):
    return ajouter_actif(ActifIn(nom=f"{PREFIXE} {nom}", type=type, valeur=valeur, verse=verse, zakat=zakat, maj_le=AUJ))


def _ecart(avant, apres, cle):
    return round(apres[cle] - avant[cle], 2)


def test_actif_achete_avec_son_epargne_ne_compte_que_sa_plus_value():
    avant = calculer_patrimoine(AUJ)
    _actif(valeur=12000, verse=10000)
    apres = calculer_patrimoine(AUJ)
    assert _ecart(avant, apres, "autres_actifs") == 12000
    assert _ecart(avant, apres, "liquidites") == -10000        # l'argent versé a quitté les liquidités
    assert _ecart(avant, apres, "total") == 2000               # seul le gain de valeur enrichit


def test_actif_detenu_avant_l_application_s_ajoute_en_entier():
    avant = calculer_patrimoine(AUJ)
    _actif(valeur=5000)
    assert _ecart(avant, calculer_patrimoine(AUJ), "total") == 5000


def test_un_pret_deplace_l_argent_sans_changer_le_patrimoine():
    avant = calculer_patrimoine(AUJ)
    ajouter_dette(DetteIn(sens="pret", personne=f"{PREFIXE} Ali", montant=800, date_operation=AUJ))
    ajouter_dette(DetteIn(sens="emprunt", personne=f"{PREFIXE} Banque", montant=300, date_operation=AUJ))
    apres = calculer_patrimoine(AUJ)
    assert _ecart(avant, apres, "creances") == 800 and _ecart(avant, apres, "dettes") == 300
    assert _ecart(avant, apres, "liquidites") == -500          # 800 sortis, 300 entrés
    assert _ecart(avant, apres, "total") == 0


def test_solde_de_depart():
    modifier_reglages(ReglagesPatrimoine(solde_depart=0))
    avant = calculer_patrimoine(AUJ)
    modifier_reglages(ReglagesPatrimoine(solde_depart=7000))
    apres = calculer_patrimoine(AUJ)
    assert _ecart(avant, apres, "liquidites") == 7000 and _ecart(avant, apres, "total") == 7000


def test_reserve_compte_les_comptes_epargne_seulement():
    avant = calculer_patrimoine(AUJ)["reserve"]["disponible"]
    _actif(valeur=4000, type="Compte épargne", nom="Livret")
    _actif(valeur=9000, type="Immobilier", nom="Terrain")
    assert round(calculer_patrimoine(AUJ)["reserve"]["disponible"] - avant, 2) == 4000


def test_zakat_assiette_nisab_et_montant():
    modifier_reglages(ReglagesPatrimoine(solde_depart=0, prix_or_gramme=0))
    assert calculer_patrimoine(AUJ)["zakat"]["nisab"] is None and not calculer_patrimoine(AUJ)["zakat"]["atteint"]
    avant = calculer_patrimoine(AUJ)["zakat"]["detail"]["actifs"]
    _actif(valeur=100000, zakat=True, nom="Or")
    _actif(valeur=500000, zakat=False, type="Immobilier", nom="Maison")     # hors assiette
    modifier_reglages(ReglagesPatrimoine(prix_or_gramme=1000))
    z = calculer_patrimoine(AUJ)["zakat"]
    assert round(z["detail"]["actifs"] - avant, 2) == 100000
    assert z["nisab"] == 85000 and z["atteint"]
    assert z["montant"] == round(z["assiette"] * 0.025, 2)
    # Un prix de l'or qui met le nisab hors d'atteinte : rien n'est dû
    modifier_reglages(ReglagesPatrimoine(prix_or_gramme=10_000_000))
    z = calculer_patrimoine(AUJ)["zakat"]
    assert not z["atteint"] and z["montant"] == 0


def test_echeance_du_hawl():
    debut = AUJ - timedelta(days=300)
    modifier_reglages(ReglagesPatrimoine(prix_or_gramme=1000, debut_hawl=debut))
    z = calculer_patrimoine(AUJ)["zakat"]
    assert z["debut_hawl"] == debut and z["echeance"] == debut + timedelta(days=JOURS_HAWL)
    assert z["jours_restants"] == JOURS_HAWL - 300
    modifier_reglages(ReglagesPatrimoine(prix_or_gramme=1000))               # date retirée
    assert calculer_patrimoine(AUJ)["zakat"]["echeance"] is None


def test_modifier_et_supprimer_un_actif():
    a = _actif(valeur=1000)
    assert float(modifier_actif(a["id"], ActifIn(nom=f"{PREFIXE} Actif", valeur=1500, maj_le=AUJ))["valeur"]) == 1500
    supprimer_actif(a["id"])
    for appel in (lambda: supprimer_actif(a["id"]), lambda: modifier_actif(a["id"], ActifIn(nom="x", valeur=1, maj_le=AUJ))):
        with pytest.raises(HTTPException) as exc:
            appel()
        assert exc.value.status_code == 404
