# -*- coding: utf-8 -*-
"""
Tests des apports/retraits du compte Bourse. Utilise la base configurée dans
.env : les données de test portent le préfixe ZZTEST et sont supprimées
avant/après. ⚠️ À lancer sur une base de développement, jamais sur la prod. Les vérifications sur le dashboard se font par DIFFÉRENCE
(avant/après), pour ne pas dépendre des données réelles déjà présentes.

Lancement :
    cd backend
    pytest tests/test_mouvements.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

from database import db
from schemas import MouvementBourseCreate
from routes.bourse import creer_mouvement, supprimer_mouvement, obtenir_dashboard

PREFIXE = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM bourse_mouvements WHERE libelle LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _mouvement(type_mouvement, montant, date="2026-09-01"):
    return creer_mouvement(MouvementBourseCreate(
        date_operation=date, type_mouvement=type_mouvement, montant=montant, libelle=PREFIXE + " test",
    ))


def test_apport_augmente_especes_et_apports_nets_mais_pas_la_performance():
    avant = obtenir_dashboard()
    _mouvement("Apport", 1000)
    apres = obtenir_dashboard()
    assert round(apres.especes_disponibles - avant.especes_disponibles, 2) == 1000
    assert round(apres.apports_nets - avant.apports_nets, 2) == 1000
    assert round(apres.patrimoine_total - avant.patrimoine_total, 2) == 1000
    # Un apport n'est pas un gain : la performance globale ne bouge pas
    assert round(apres.performance_globale - avant.performance_globale, 2) == 0


def test_retrait_diminue_especes_et_apports_nets():
    avant = obtenir_dashboard()
    _mouvement("Retrait", 300)
    apres = obtenir_dashboard()
    assert round(apres.especes_disponibles - avant.especes_disponibles, 2) == -300
    assert round(apres.apports_nets - avant.apports_nets, 2) == -300
    assert round(apres.performance_globale - avant.performance_globale, 2) == 0


def test_filtre_de_periode_sur_les_apports():
    _mouvement("Apport", 700, date="2020-03-15")   # mois sans autre activité réelle
    d = obtenir_dashboard(mois="2020-03")
    assert d.apports_periode >= 700


def test_supprimer_mouvement_inexistant_404():
    with pytest.raises(HTTPException) as exc:
        supprimer_mouvement(999999999)
    assert exc.value.status_code == 404

