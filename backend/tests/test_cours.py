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

from cours_bvc import lire_cours


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
