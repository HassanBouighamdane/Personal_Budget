# -*- coding: utf-8 -*-
"""
Tests des rapports du Budget : charges fixes (projection, budget journalier/hebdo),
comparaison avec la période précédente à durée égale, statistiques sur les mois
terminés. Utilise la base configurée dans .env : les données de test portent le
préfixe ZZTEST et sont datées de 1901, une année sans données réelles ; la date
« du jour » est fixée par paramètre.

Lancement :
    cd backend
    pytest tests/test_rapports.py -v
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from database import db
from schemas import CategorieIn, DepenseIn, RevenuIn
from routes.configuration import ajouter_categorie
from routes.transactions import ajouter_depense, ajouter_revenu
from routes.rapports import (
    calculer_resume, calculer_resume_annuel, calculer_resume_semaine, projection_fin_mois, resume_jour,
)

PREFIXE = "ZZTEST"
COURSES, LOYER = PREFIXE + "Courses", PREFIXE + "Loyer"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM depenses WHERE categorie LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM revenus WHERE source LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM categories WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    # Budgets « depuis toujours », pour qu'ils s'appliquent aux mois de 1901 des tests
    ajouter_categorie(CategorieIn(nom=COURSES, budget=1200, a_partir_de="1900-01"))
    ajouter_categorie(CategorieIn(nom=LOYER, budget=3000, fixe=True, a_partir_de="1900-01"))
    yield
    _nettoyer()


def _dep(jour, montant, categorie=COURSES):
    ajouter_depense(DepenseIn(date=jour, categorie=categorie, montant=montant))


def _rev(jour, montant):
    ajouter_revenu(RevenuIn(date=jour, source=PREFIXE, montant=montant))


# ---------------------------------------------------------------------------
# Problème 1 — charges fixes
# ---------------------------------------------------------------------------
CATS = [{"nom": "Loyer", "budget": 3000, "fixe": True},
        {"nom": "Factures", "budget": 700, "fixe": True},
        {"nom": "Courses", "budget": 1500, "fixe": False}]


def test_projection_n_extrapole_que_les_depenses_variables():
    # Le 2 : loyer payé, factures pas encore ; 100 DH de courses -> 3000 + 700 + 100/2×30
    assert projection_fin_mois({"Loyer": 3000, "Courses": 100}, CATS, 2, 30) == 5200
    # Ancien calcul : 3100 / 2 × 30 = 46 500


def test_projection_retient_une_charge_fixe_superieure_au_budget():
    assert projection_fin_mois({"Loyer": 3200}, CATS, 10, 30) == 3200 + 700


def test_projection_sans_charge_fixe_inchangee():
    cats = [{"nom": "Courses", "budget": 1500, "fixe": False}]
    assert projection_fin_mois({"Courses": 300}, cats, 10, 30) == 900


def test_le_loyer_ne_compte_pas_dans_le_budget_du_jour_ni_de_la_semaine():
    _dep("1901-03-01", 3000, LOYER)
    _dep("1901-03-01", 40)
    j = resume_jour("1901-03-01")
    assert (j["total_depenses"], j["depenses_variables"]) == (3040, 40)
    s = calculer_resume_semaine(date(1901, 3, 1), date(1901, 3, 1))
    assert s["depenses_variables"] == 40
    assert s["reste_budget_hebdo"] == round(s["budget_hebdo"] - 40, 2)


# ---------------------------------------------------------------------------
# Problème 2 — comparaison à durée égale
# ---------------------------------------------------------------------------
def test_mois_en_cours_compare_au_meme_jour_du_mois_precedent():
    _dep("1901-02-05", 100)
    _dep("1901-02-20", 300)
    _dep("1901-03-05", 50)
    r = calculer_resume("1901-03", date(1901, 3, 10))
    assert r["depenses_mois_precedent"] == 100          # du 1er au 10 février
    assert r["depenses_mois_precedent_total"] == 400
    assert r["jour_comparaison"] == 10


def test_mois_termine_compare_au_mois_precedent_entier():
    _dep("1901-02-05", 100)
    _dep("1901-02-20", 300)
    r = calculer_resume("1901-03", date(1901, 4, 15))
    assert r["depenses_mois_precedent"] == 400
    assert r["jour_comparaison"] is None
    assert r["projection_fin_mois"] is None


def test_mois_precedent_plus_court_pris_en_entier():
    _dep("1901-02-27", 100)
    r = calculer_resume("1901-03", date(1901, 3, 30))   # février 1901 : 28 jours
    assert r["depenses_mois_precedent"] == 100
    assert r["jour_comparaison"] is None


def test_semaine_en_cours_comparee_jusqu_au_meme_jour():
    mercredi = date(1901, 3, 6)
    lundi = mercredi - timedelta(days=mercredi.weekday())
    _dep((lundi - timedelta(days=7)).isoformat(), 10)    # lundi précédent : compté
    _dep((lundi - timedelta(days=3)).isoformat(), 50)    # vendredi précédent : hors comparaison
    s = calculer_resume_semaine(mercredi, lundi + timedelta(days=2))
    assert s["comparaison_partielle"] is True
    assert s["depenses_semaine_precedente"] == 10
    assert s["depenses_semaine_precedente_totale"] == 60


# ---------------------------------------------------------------------------
# Problème 3 — année en cours : seuls les mois terminés comptent
# ---------------------------------------------------------------------------
def test_mois_en_cours_exclu_des_statistiques_annuelles():
    _rev("1901-01-28", 1000); _dep("1901-01-10", 100)
    _rev("1901-02-28", 1000); _dep("1901-02-10", 200)
    _dep("1901-03-05", 50)                     # mars en cours, salaire pas encore reçu
    r = calculer_resume_annuel(1901, date(1901, 3, 10))
    assert r["nb_mois_actifs"] == 2
    assert r["moyenne_dep_mois"] == 150
    assert r["pire_mois"]["m"] == 2           # et non mars (épargne −50)
    assert r["mois_en_cours"] == 3
    assert r["total_depenses"] == 350         # les totaux gardent tout


def test_budget_annuel_ramene_aux_mois_ecoules():
    _dep("1901-03-05", 1200)
    r = calculer_resume_annuel(1901, date(1901, 3, 16))
    cat = next(x for x in r["categories"] if x["cat"] == COURSES)
    assert cat["budget_annuel"] == 1200 * 12
    assert cat["budget_a_date"] == round(1200 * (2 + 16 / 31), 2)
    # Année passée : budget des 12 mois
    cat = next(x for x in calculer_resume_annuel(1901, date(1902, 1, 5))["categories"] if x["cat"] == COURSES)
    assert cat["budget_a_date"] == 1200 * 12
