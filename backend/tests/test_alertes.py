# -*- coding: utf-8 -*-
"""
Tests des alertes de dépenses inhabituelles : catégorie au-dessus de sa moyenne, hausse d'un
montant récurrent, doublon, alerte ignorée. Utilise la base configurée dans .env : les données de
test sont datées de 1901 et portent le préfixe ZZTEST (catégories comprises).

Lancement :
    cd backend
    pytest tests/test_alertes.py -v
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

# Chaque test passe par la base (nettoyage automatique avant chaque test)
pytestmark = pytest.mark.base

from database import db
from routes import alertes

PREFIXE = "ZZTEST"
CAT = f"{PREFIXE} Courses"
AUJ = date(1901, 7, 20)


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM depenses WHERE categorie LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM categories WHERE nom LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM alertes_ignorees WHERE cle LIKE %s", (f"%{PREFIXE}%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    with db() as c:
        c.execute("INSERT INTO categories(nom, budget) VALUES (%s, 0)", (CAT,))
    yield
    _nettoyer()


def _depense(jour: str, montant: float, description: str = "", categorie: str = CAT):
    with db() as c:
        c.execute("INSERT INTO depenses(date, categorie, description, montant) VALUES (%s,%s,%s,%s)",
                  (jour, categorie, description, montant))


def _miennes(liste):
    return [a for a in liste if a["categorie"].startswith(PREFIXE)]


def test_categorie_au_dessus_de_sa_moyenne():
    for mois in range(1, 7):                      # 1 000 DH par mois de janvier à juin
        _depense(f"1901-{mois:02d}-10", 1000)
    _depense("1901-07-05", 1500)                  # +50 % et +500 DH en juillet
    with db() as c:
        trouvees = _miennes(alertes.alertes_categories(c, AUJ))
    assert len(trouvees) == 1
    assert trouvees[0]["type"] == "categorie" and trouvees[0]["montant"] == 500
    assert trouvees[0]["cle"] == f"categorie:1901-07:{CAT}"


def test_petit_depassement_ou_historique_court_sans_alerte():
    for mois in range(1, 7):
        _depense(f"1901-{mois:02d}-10", 1000)
    _depense("1901-07-05", 1250)                  # +25 % : sous le seuil
    with db() as c:
        assert not _miennes(alertes.alertes_categories(c, AUJ))
    _nettoyer()
    with db() as c:
        c.execute("INSERT INTO categories(nom, budget) VALUES (%s, 0)", (CAT,))
    _depense("1901-06-10", 100)                   # un seul mois d'historique : pas de moyenne fiable
    _depense("1901-07-05", 5000)
    with db() as c:
        assert not _miennes(alertes.alertes_categories(c, AUJ))


def test_hausse_d_un_montant_recurrent():
    for mois in (3, 4, 5, 6):
        _depense(f"1901-{mois:02d}-02", 65, "Netflix")
    _depense("1901-07-02", 75, "netflix ")        # même description, casse et espaces près
    with db() as c:
        trouvees = _miennes(alertes.alertes_hausses(c, AUJ))
    assert len(trouvees) == 1 and trouvees[0]["montant"] == 10


def test_montant_variable_n_est_pas_une_hausse():
    for mois, montant in ((3, 300), (4, 420), (5, 350), (6, 280)):
        _depense(f"1901-{mois:02d}-02", montant, "Marché")
    _depense("1901-07-02", 500, "Marché")
    with db() as c:
        assert not _miennes(alertes.alertes_hausses(c, AUJ))


def test_doublon_et_alerte_ignoree():
    _depense("1901-07-18", 45, "Café")
    _depense("1901-07-18", 45, "café")
    _depense("1901-07-18", 45, "Thé")             # autre description : pas un doublon
    with db() as c:
        trouvees = _miennes(alertes.alertes_doublons(c, AUJ))
    assert len(trouvees) == 1 and trouvees[0]["titre"].startswith("2 ×")
    cle = trouvees[0]["cle"]
    # Ignorée : elle ne revient plus (la clé de test est rangée sous le préfixe pour être nettoyée)
    with db() as c:
        c.execute("INSERT INTO alertes_ignorees(cle) VALUES(%s)", (cle,))
    try:
        assert cle not in {a["cle"] for a in alertes.calculer_alertes(AUJ)}
    finally:
        with db() as c:
            c.execute("DELETE FROM alertes_ignorees WHERE cle=%s", (cle,))
