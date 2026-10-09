# -*- coding: utf-8 -*-
"""
Tests de la lecture du flux de cours (cours_bvc.py). Aucun accès réseau ni base :
seule l'interprétation de la réponse est vérifiée.

Lancement :
    cd backend
    pytest tests/test_cours.py -v
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cours_bvc import Cours, lire_cours_medias24 as lire_cours, lire_cours_officiel


def test_cours_lu_par_isin():
    flux = {"result": [{"ISIN": "MA0000012445", "cours": "676.00", "cloture": "670,00"}]}
    assert lire_cours(flux) == {"MA0000012445": Decimal("676.00")}


def test_sans_cours_du_jour_la_cloture_est_utilisee():
    flux = {"result": [{"ISIN": "MA0000012296", "cours": "", "cloture": "1 250,00"},
                       {"ISIN": "MA0000010944", "cours": "0.00", "cloture": "6 680,00"}]}
    assert lire_cours(flux) == {"MA0000012296": Decimal("1250.00"), "MA0000010944": Decimal("6680.00")}


def test_lignes_illisibles_ignorees():
    flux = {"result": [{"ISIN": "", "cours": "10"}, {"ISIN": "MA1", "cours": "n/a", "cloture": None}, {"cours": "5"}]}
    assert lire_cours(flux) == {}
    assert lire_cours({}) == {}


PAGE = ('<html><script type="application/json" data-drupal-selector="drupal-settings-json">'
        '{"live_market":{"actions":[{"symbol":"ATW","dernierCours":670,"reference":665.5},'
        '{"symbol":"DRI ","dernierCours":null,"reference":4180},{"symbol":"X","dernierCours":0,"reference":0}]}}'
        '</script></html>')


def test_page_officielle_lue_par_symbole():
    assert lire_cours_officiel(PAGE) == {"ATW": Decimal("670"), "DRI": Decimal("4180")}
    assert lire_cours_officiel("<html>page sans données</html>") == {}


def test_rapprochement_par_code_puis_par_isin():
    officiel = Cours("Bourse de Casablanca", lire_cours_officiel(PAGE), {})
    assert officiel.de("ATW", None) == Decimal("670")
    assert officiel.de("DARI", None) == Decimal("4180")     # code de l'application ≠ symbole officiel
    assert officiel.de("ZZZ", "MA0000012445") is None
    secours = Cours("Médias24", {}, {"MA0000012445": Decimal("676")})
    assert secours.de("ATW", "MA0000012445") == Decimal("676")
    assert secours.de("ATW", None) is None
