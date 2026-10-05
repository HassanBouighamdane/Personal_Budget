# -*- coding: utf-8 -*-
"""
Tests du module Budget : cascade de renommage (catégories/sources)
et erreurs 404 sur les suppressions/modifications. Utilise la vraie base
configurée dans .env : chaque test isole ses données sous un préfixe fictif
(ZZTEST) et les supprime avant/après, pour ne jamais toucher aux données réelles.

Lancement :
    cd backend
    pytest tests/test_budget.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

from database import db
from schemas import CategorieIn, NomIn, DepenseIn, RevenuIn
from routes.configuration import (
    ajouter_categorie, modifier_categorie, desactiver_categorie,
    ajouter_source, modifier_source, desactiver_source,
)
from routes.transactions import (
    ajouter_depense, modifier_depense, supprimer_depense,
    ajouter_revenu, modifier_revenu, supprimer_revenu,
)

PREFIXE = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM depenses WHERE categorie LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM revenus WHERE source LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM categories WHERE nom LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM sources_revenus WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _id_categorie(nom):
    with db() as c:
        return c.execute("SELECT id FROM categories WHERE nom=%s", (nom,)).fetchone()["id"]


# ---------------------------------------------------------------------------
# Point 6 — renommer une catégorie/source ne doit pas détacher
# les dépenses/revenus déjà saisis sous l'ancien nom.
# ---------------------------------------------------------------------------
def test_renommer_categorie_met_a_jour_les_depenses_existantes():
    ajouter_categorie(CategorieIn(nom=PREFIXE + "Cat", budget=100))
    cid = _id_categorie(PREFIXE + "Cat")
    ajouter_depense(DepenseIn(date="2026-01-15", categorie=PREFIXE + "Cat", montant=50, description=""))

    modifier_categorie(cid, CategorieIn(nom=PREFIXE + "CatRenommee", budget=100))

    with db() as c:
        row = c.execute("SELECT categorie FROM depenses WHERE categorie LIKE %s", (PREFIXE + "%",)).fetchone()
    assert row["categorie"] == PREFIXE + "CatRenommee"


def test_renommer_source_met_a_jour_les_revenus_existants():
    ajouter_source(NomIn(nom=PREFIXE + "Src"))
    with db() as c:
        sid = c.execute("SELECT id FROM sources_revenus WHERE nom=%s", (PREFIXE + "Src",)).fetchone()["id"]
    ajouter_revenu(RevenuIn(date="2026-01-15", source=PREFIXE + "Src", montant=200))

    modifier_source(sid, NomIn(nom=PREFIXE + "SrcRenommee"))

    with db() as c:
        row = c.execute("SELECT source FROM revenus WHERE source LIKE %s", (PREFIXE + "%",)).fetchone()
    assert row["source"] == PREFIXE + "SrcRenommee"


# ---------------------------------------------------------------------------
# Point 7 — 404 sur les modifications/suppressions inexistantes (comme le
# module Bourse), au lieu de renvoyer {ok: true} silencieusement.
# ---------------------------------------------------------------------------
def test_404_sur_depense_inexistante():
    with pytest.raises(HTTPException) as exc:
        supprimer_depense(9_999_999)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        modifier_depense(9_999_999, DepenseIn(date="2026-01-15", categorie="X", montant=1))
    assert exc.value.status_code == 404


def test_404_sur_revenu_inexistant():
    with pytest.raises(HTTPException) as exc:
        supprimer_revenu(9_999_999)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        modifier_revenu(9_999_999, RevenuIn(date="2026-01-15", source="X", montant=1))
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Modification d'une dépense / d'un revenu déjà saisi (tous les champs, y compris
# la date : la ligne peut changer de mois).
# ---------------------------------------------------------------------------
def test_modifier_depense():
    did = ajouter_depense(DepenseIn(date="2026-01-15", categorie=PREFIXE + "Cat", montant=50, description="avant"))["id"]

    modifier_depense(did, DepenseIn(date="2026-02-03", categorie=PREFIXE + "Autre", montant=75.5, description=" après "))

    with db() as c:
        row = c.execute("SELECT date,categorie,description,montant FROM depenses WHERE id=%s", (did,)).fetchone()
    assert (row["date"], row["categorie"], row["description"], row["montant"]) == \
           ("2026-02-03", PREFIXE + "Autre", "après", 75.5)


def test_modifier_revenu():
    rid = ajouter_revenu(RevenuIn(date="2026-01-15", source=PREFIXE + "Src", montant=200))["id"]

    modifier_revenu(rid, RevenuIn(date="2026-02-03", source=PREFIXE + "Autre", montant=250))

    with db() as c:
        row = c.execute("SELECT date,source,montant FROM revenus WHERE id=%s", (rid,)).fetchone()
    assert (row["date"], row["source"], row["montant"]) == ("2026-02-03", PREFIXE + "Autre", 250)


def test_404_sur_categorie_inexistante():
    with pytest.raises(HTTPException) as exc:
        modifier_categorie(9_999_999, CategorieIn(nom="X", budget=0))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        desactiver_categorie(9_999_999)
    assert exc.value.status_code == 404


def test_404_sur_source_inexistante():
    with pytest.raises(HTTPException) as exc:
        modifier_source(9_999_999, NomIn(nom="X"))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        desactiver_source(9_999_999)
    assert exc.value.status_code == 404
