# -*- coding: utf-8 -*-
"""
Tests du pointage du solde (rapprochement) : écart, enregistrement de l'écart en dépense ou en
revenu, jours sans dépense, dernier pointage. Les liquidités calculées sont remplacées par une
valeur fixe (monkeypatch) ; les données de test sont datées de 1901 et portent le préfixe ZZTEST.

Lancement :
    cd backend
    pytest tests/test_pointage.py -v
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

# Chaque test passe par la base (nettoyage automatique avant chaque test)
pytestmark = pytest.mark.base
from fastapi import HTTPException

from database import db
from routes import patrimoine

PREFIXE = "ZZTEST"
CAT = f"{PREFIXE} Divers"
AUJ = date(1901, 3, 15)


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM rapprochements WHERE note LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM depenses WHERE categorie LIKE %s OR (date LIKE '1901-%%' AND %s = ANY(tags))",
                  (PREFIXE + "%", patrimoine.TAG_ECART))
        c.execute("DELETE FROM revenus WHERE date LIKE '1901-%%' AND %s = ANY(tags)", (patrimoine.TAG_ECART,))
        c.execute("DELETE FROM categories WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    _nettoyer()
    with db() as c:
        c.execute("INSERT INTO categories(nom, budget) VALUES (%s, 0)", (CAT,))
    monkeypatch.setattr(patrimoine, "liquidites_du_jour", lambda auj, p=None: 10_000.0)
    yield
    _nettoyer()


def _pointer(*montants, **options):
    comptes = [{"nom": f"Compte {i}", "montant": m} for i, m in enumerate(montants)]
    return patrimoine.pointer(AUJ, comptes, f"{PREFIXE} test", **options)


def test_ecart_seulement_note():
    r = _pointer(9_000, 650)
    assert r["solde_reel"] == 9_650 and r["solde_calcule"] == 10_000 and r["ecart"] == -350
    assert r["regle"] is None and len(r["comptes"]) == 2
    with db() as c:
        assert not c.execute("SELECT 1 FROM depenses WHERE date='1901-03-15' AND %s = ANY(tags)",
                             (patrimoine.TAG_ECART,)).fetchone()


def test_argent_manquant_enregistre_en_depense():
    r = _pointer(9_650, enregistrer_ecart=True, categorie=CAT)
    assert r["regle"] == "depense"
    with db() as c:
        d = c.execute("SELECT montant, categorie, tags FROM depenses WHERE date='1901-03-15' AND categorie=%s", (CAT,)).fetchone()
    assert d["montant"] == 350 and patrimoine.TAG_ECART in d["tags"]


def test_argent_en_trop_enregistre_en_revenu():
    r = _pointer(10_200, enregistrer_ecart=True)
    assert r["regle"] == "revenu" and r["ecart"] == 200
    with db() as c:
        assert c.execute("SELECT montant FROM revenus WHERE date='1901-03-15' AND %s = ANY(tags)",
                         (patrimoine.TAG_ECART,)).fetchone()["montant"] == 200


def test_depense_d_ecart_sans_categorie_refusee():
    with pytest.raises(HTTPException) as e:
        _pointer(9_000, enregistrer_ecart=True)
    assert e.value.status_code == 400


def test_solde_juste_rien_a_enregistrer():
    r = _pointer(10_000, enregistrer_ecart=True, categorie=CAT)
    assert r["ecart"] == 0 and r["regle"] is None


def test_dernier_pointage():
    _pointer(9_900)
    with db() as c:
        p = patrimoine.dernier_pointage(c, date(1901, 3, 20))
    # D'autres pointages (réels) peuvent être plus récents : seul le calcul des jours est vérifié ici
    if p["date"] == AUJ:
        assert p["jours"] == 5 and p["ecart"] == -100 and not p["a_refaire"]


def test_jours_sans_depense():
    with db() as c:
        c.execute("INSERT INTO depenses(date, categorie, montant) VALUES ('1901-03-02', %s, 10), ('1901-03-04', %s, 10)", (CAT, CAT))
        jours = patrimoine.jours_sans_depense(c, date(1901, 3, 1), date(1901, 3, 5))
    assert jours == [date(1901, 3, 1), date(1901, 3, 3), date(1901, 3, 5)]
