# -*- coding: utf-8 -*-
"""
Tests du module Budget : cascade de renommage (catégories/sources/paiements)
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
    ajouter_paiement, modifier_paiement, desactiver_paiement,
)
from routes.transactions import ajouter_depense, supprimer_depense, ajouter_revenu, supprimer_revenu

PREFIXE = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM depenses WHERE categorie LIKE %s OR paiement LIKE %s", (PREFIXE + "%", PREFIXE + "%"))
        c.execute("DELETE FROM revenus WHERE source LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM categories WHERE nom LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM sources_revenus WHERE nom LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM paiements WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _id_categorie(nom):
    with db() as c:
        return c.execute("SELECT id FROM categories WHERE nom=%s", (nom,)).fetchone()["id"]


# ---------------------------------------------------------------------------
# Point 6 — renommer une catégorie/source/paiement ne doit pas détacher
# les dépenses/revenus déjà saisis sous l'ancien nom.
# ---------------------------------------------------------------------------
def test_renommer_categorie_met_a_jour_les_depenses_existantes():
    ajouter_categorie(CategorieIn(nom=PREFIXE + "Cat", budget=100))
    cid = _id_categorie(PREFIXE + "Cat")
    ajouter_depense(DepenseIn(date="2026-01-15", categorie=PREFIXE + "Cat", montant=50, description="", paiement=""))

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


def test_renommer_paiement_met_a_jour_les_depenses_existantes():
    ajouter_categorie(CategorieIn(nom=PREFIXE + "Cat2", budget=100))
    ajouter_paiement(NomIn(nom=PREFIXE + "Pay"))
    with db() as c:
        pid = c.execute("SELECT id FROM paiements WHERE nom=%s", (PREFIXE + "Pay",)).fetchone()["id"]
    ajouter_depense(DepenseIn(date="2026-01-15", categorie=PREFIXE + "Cat2", montant=30, description="", paiement=PREFIXE + "Pay"))

    modifier_paiement(pid, NomIn(nom=PREFIXE + "PayRenomme"))

    with db() as c:
        row = c.execute("SELECT paiement FROM depenses WHERE categorie=%s", (PREFIXE + "Cat2",)).fetchone()
    assert row["paiement"] == PREFIXE + "PayRenomme"


# ---------------------------------------------------------------------------
# Point 7 — 404 sur les modifications/suppressions inexistantes (comme le
# module Bourse), au lieu de renvoyer {ok: true} silencieusement.
# ---------------------------------------------------------------------------
def test_404_sur_depense_inexistante():
    with pytest.raises(HTTPException) as exc:
        supprimer_depense(9_999_999)
    assert exc.value.status_code == 404


def test_404_sur_revenu_inexistant():
    with pytest.raises(HTTPException) as exc:
        supprimer_revenu(9_999_999)
    assert exc.value.status_code == 404


def test_404_sur_categorie_inexistante():
    with pytest.raises(HTTPException) as exc:
        modifier_categorie(9_999_999, CategorieIn(nom="X", budget=0))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        desactiver_categorie(9_999_999)
    assert exc.value.status_code == 404


def test_404_sur_source_et_paiement_inexistants():
    with pytest.raises(HTTPException) as exc:
        modifier_source(9_999_999, NomIn(nom="X"))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        desactiver_source(9_999_999)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        modifier_paiement(9_999_999, NomIn(nom="X"))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        desactiver_paiement(9_999_999)
    assert exc.value.status_code == 404
