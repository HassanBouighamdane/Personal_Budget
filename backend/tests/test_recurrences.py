# -*- coding: utf-8 -*-
"""
Tests des opérations récurrentes : calendrier (jour 31, mois manqués, début), suggestions tirées de
l'historique, puis génération en base (une seule fois par mois, mois passé, montant du mois).
Les tests de la dernière partie utilisent la base configurée dans .env : leurs données portent le
préfixe ZZTEST.

Lancement :
    cd backend
    pytest tests/test_recurrences.py -v
    pytest tests/test_recurrences.py -v -m "not base"     # sans base de données
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from routes.recurrences import (
    date_du_mois, echeances_en_attente, mois_a_generer, mois_precedent, mois_suivant, premier_mois_attendu, suggerer,
)


def _r(id=1, jour=5, debut="2026-09", dernier=None, actif=True, auto=False):
    return {"id": id, "type": "depense", "nom": "Loyer", "categorie": "Loyer", "source": None, "description": "",
            "montant": 4500.0, "jour": jour, "tags": [], "auto": auto, "actif": actif, "debut": debut, "dernier_mois": dernier}


# ---------------------------------------------------------------------------
# Calendrier
# ---------------------------------------------------------------------------
def test_mois_voisins():
    assert mois_suivant("2026-12") == "2027-01"
    assert mois_suivant("2026-01") == "2026-02"
    assert mois_precedent("2027-01") == "2026-12"


def test_jour_31_ramene_au_dernier_jour():
    assert date_du_mois("2026-04", 31) == date(2026, 4, 30)
    assert date_du_mois("2027-02", 30) == date(2027, 2, 28)
    assert date_du_mois("2028-02", 31) == date(2028, 2, 29)
    assert date_du_mois("2026-11", 5) == date(2026, 11, 5)


def test_premier_mois_attendu():
    assert premier_mois_attendu(_r(debut="2026-09")) == "2026-09"
    assert premier_mois_attendu(_r(debut="2026-09", dernier="2026-10")) == "2026-11"
    # Début avancé après le dernier mois généré : on reprend au début
    assert premier_mois_attendu(_r(debut="2027-01", dernier="2026-10")) == "2027-01"


def test_mois_manques_rattrapes_dans_l_ordre():
    assert mois_a_generer(_r(debut="2026-08", dernier="2026-08"), "2026-11") == ["2026-09", "2026-10", "2026-11"]
    assert mois_a_generer(_r(debut="2026-12"), "2026-11") == []


def test_en_attente_et_echues():
    auj = date(2026, 11, 12)
    recs = [_r(id=1, jour=5, debut="2026-11"), _r(id=2, jour=28, debut="2026-11"), _r(id=3, debut="2026-11", actif=False)]
    toutes = echeances_en_attente(recs, auj)
    assert [(e["recurrence"]["id"], e["date"]) for e in toutes] == [(1, date(2026, 11, 5)), (2, date(2026, 11, 28))]
    # La tâche du matin n'ajoute que ce qui est arrivé
    echues = echeances_en_attente(recs, auj, seulement_echues=True)
    assert [e["recurrence"]["id"] for e in echues] == [1]


def test_echues_avec_mois_manques():
    auj = date(2026, 11, 3)
    echues = echeances_en_attente([_r(jour=5, debut="2026-09", dernier="2026-08")], auj, seulement_echues=True)
    assert [e["mois"] for e in echues] == ["2026-09", "2026-10"]     # novembre : le 5 n'est pas encore là


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------
MOIS = ["2026-08", "2026-09", "2026-10"]


def _op(date_, montant, nom="Abonnements", description="Netflix", type_="depense", tags=()):
    return {"type": type_, "nom": nom, "description": description, "date": date_, "montant": montant, "tags": list(tags)}


def test_suggestion_trois_mois_montants_proches():
    lignes = [_op("2026-08-03", 65), _op("2026-09-03", 65), _op("2026-10-04", 70, tags=["streaming"])]
    s = suggerer(lignes, MOIS, set())
    assert len(s) == 1
    assert s[0]["nom"] == "Abonnements" and s[0]["montant"] == 70 and s[0]["jour"] == 3 and s[0]["tags"] == ["streaming"]


def test_pas_de_suggestion_si_un_mois_manque_ou_double():
    assert suggerer([_op("2026-08-03", 65), _op("2026-10-03", 65)], MOIS, set()) == []
    doublon = [_op("2026-08-03", 65), _op("2026-09-03", 65), _op("2026-09-20", 65), _op("2026-10-03", 65)]
    assert suggerer(doublon, MOIS, set()) == []


def test_pas_de_suggestion_si_montants_eloignes():
    assert suggerer([_op("2026-08-03", 300), _op("2026-09-03", 450), _op("2026-10-03", 380)], MOIS, set()) == []


def test_description_normalisee_et_existante_exclue():
    lignes = [_op("2026-08-01", 4500, "Loyer", " Loyer  Appart"), _op("2026-09-01", 4500, "Loyer", "loyer appart"),
              _op("2026-10-01", 4500, "Loyer", "Loyer appart")]
    assert len(suggerer(lignes, MOIS, set())) == 1
    assert suggerer(lignes, MOIS, {("depense", "Loyer", "loyer appart")}) == []


def test_salaire_sans_description():
    lignes = [_op(f"{m}-28", 9000, "Salaire", "", "revenu") for m in MOIS]
    s = suggerer(lignes, MOIS, set())
    assert s and s[0]["type"] == "revenu" and s[0]["jour"] == 28


# ---------------------------------------------------------------------------
# Génération en base
# ---------------------------------------------------------------------------
PREFIXE = "ZZTEST"


@pytest.fixture
def base():
    from database import db

    def nettoyer():
        with db() as c:
            c.execute("DELETE FROM depenses WHERE description LIKE %s", (PREFIXE + "%",))
            c.execute("DELETE FROM recurrences WHERE description LIKE %s", (PREFIXE + "%",))
    nettoyer()
    yield db
    nettoyer()


def _creer(jour=5, debut="1901-01", auto=False):
    from routes.recurrences import ajouter
    from schemas import RecurrenceIn
    with __import__("database").db() as c:
        cat = c.execute("SELECT nom FROM categories WHERE actif=1 ORDER BY id LIMIT 1").fetchone()["nom"]
    return ajouter(RecurrenceIn(type="depense", nom=cat, description=f"{PREFIXE} loyer", montant=100, jour=jour,
                                debut=debut, auto=auto))


@pytest.mark.base
def test_generer_une_seule_fois(base):
    from routes.recurrences import generer
    from schemas import GenerationIn
    r = _creer(jour=31, debut="1901-02")
    g = generer(GenerationIn(elements=[{"id": r["id"], "mois": "1901-02", "montant": 120}]))
    assert len(g["generees"]) == 1 and g["generees"][0]["date"] == date(1901, 2, 28) and g["generees"][0]["montant"] == 120
    # Second passage pour le même mois : rien
    assert generer(GenerationIn(elements=[{"id": r["id"], "mois": "1901-02"}]))["ignorees"] == 1
    with base() as c:
        n = c.execute("SELECT COUNT(*) n FROM depenses WHERE description=%s", (f"{PREFIXE} loyer",)).fetchone()["n"]
    assert n == 1


@pytest.mark.base
def test_mois_saute_refuse_puis_passer(base):
    from fastapi import HTTPException
    from routes.recurrences import generer, passer
    from schemas import GenerationIn, PasserIn
    r = _creer(debut="1901-01")
    # Mars avant janvier : ignoré (les mois se font dans l'ordre)
    assert generer(GenerationIn(elements=[{"id": r["id"], "mois": "1901-03"}]))["ignorees"] == 1
    passer(r["id"], PasserIn(mois="1901-01"))
    with pytest.raises(HTTPException):
        passer(r["id"], PasserIn(mois="1901-01"))
    assert len(generer(GenerationIn(elements=[{"id": r["id"], "mois": "1901-02"}]))["generees"]) == 1


@pytest.mark.base
def test_automatiques_jusqu_a_aujourdhui(base):
    from routes.recurrences import generer_automatiques
    r = _creer(jour=20, debut="1901-01", auto=True)
    faites = [g for g in generer_automatiques(date(1901, 3, 10)) if g["id"] == r["id"]]
    assert [g["mois"] for g in faites] == ["1901-01", "1901-02"]
    assert not [g for g in generer_automatiques(date(1901, 3, 10)) if g["id"] == r["id"]]
