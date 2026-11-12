# -*- coding: utf-8 -*-
"""
Tests des provisions : une échéance avec un montant crée un objectif d'épargne du même montant pour
la même date ; il suit les modifications de l'échéance, passe à la période suivante quand elle est
reportée, et disparaît avec elle s'il est vide. Données de test : préfixe ZZTEST.

Lancement :
    cd backend
    pytest tests/test_provisions.py -v
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from pydantic import ValidationError

from config import aujourdhui
from database import db
from schemas import EcheanceIn, VersementIn
from routes.carnet import ajouter_echeance, lister_echeances, modifier_echeance, reporter_echeance, supprimer_echeance
from routes.objectifs import ajouter_versement, lister_objectifs

PREFIXE = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM echeances WHERE titre LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM objectifs WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _dans(jours: int) -> date:
    return aujourdhui() + timedelta(days=jours)


def _echeance(montant=1200, provisionner=True, recurrence=12, jours=120, titre="Assurance"):
    return ajouter_echeance(EcheanceIn(titre=f"{PREFIXE} {titre}", date_echeance=_dans(jours), montant=montant,
                                       provisionner=provisionner, recurrence_mois=recurrence))


def _objectif(oid):
    return next((o for o in lister_objectifs() if o["id"] == oid), None)


def test_provision_cree_un_objectif():
    e = _echeance()
    assert e["montant"] == 1200 and e["objectif_id"]
    o = _objectif(e["objectif_id"])
    assert o["nom"] == f"{PREFIXE} Assurance" and o["cible"] == 1200 and o["date_limite"] == _dans(120)
    assert o["echeance_id"] == e["id"] and o["par_mois"] > 0
    assert e["provision"]["cible"] == 1200 and e["provision"]["verse"] == 0


def test_provision_sans_montant_refusee():
    with pytest.raises(ValidationError):
        EcheanceIn(titre=f"{PREFIXE} X", date_echeance=_dans(10), provisionner=True)


def test_montant_sans_provision_ne_cree_rien():
    e = _echeance(provisionner=False)
    assert e["montant"] == 1200 and e["objectif_id"] is None and e["provision"] is None


def test_l_objectif_suit_l_echeance_puis_disparait_s_il_est_vide():
    e = _echeance()
    m = modifier_echeance(e["id"], EcheanceIn(titre=f"{PREFIXE} Assurance auto", date_echeance=_dans(200), montant=1500,
                                              provisionner=True, recurrence_mois=12))
    o = _objectif(m["objectif_id"])
    assert m["objectif_id"] == e["objectif_id"] and o["cible"] == 1500 and o["date_limite"] == _dans(200)
    sans = modifier_echeance(e["id"], EcheanceIn(titre=f"{PREFIXE} Assurance auto", date_echeance=_dans(200), montant=1500,
                                                 recurrence_mois=12))
    assert sans["objectif_id"] is None and _objectif(e["objectif_id"]) is None


def test_objectif_avec_argent_garde_quand_l_echeance_est_supprimee():
    e = _echeance()
    ajouter_versement(e["objectif_id"], VersementIn(date_operation=aujourdhui(), montant=300))
    supprimer_echeance(e["id"])
    assert _objectif(e["objectif_id"])["verse"] == 300


def test_report_archive_l_objectif_et_en_ouvre_un_nouveau():
    e = _echeance(jours=10)
    ajouter_versement(e["objectif_id"], VersementIn(date_operation=aujourdhui(), montant=1200))
    r = reporter_echeance(e["id"])
    assert r["date_echeance"].year == _dans(10).year + 1
    ancien, nouveau = _objectif(e["objectif_id"]), _objectif(r["objectif_id"])
    assert ancien["archive"] and ancien["verse"] == 1200
    assert nouveau["id"] != ancien["id"] and not nouveau["archive"] and nouveau["verse"] == 0
    assert nouveau["date_limite"] == r["date_echeance"] and nouveau["cible"] == 1200


def test_report_d_un_objectif_vide_le_decale_seulement():
    e = _echeance(jours=10)
    r = reporter_echeance(e["id"])
    assert r["objectif_id"] == e["objectif_id"]
    assert _objectif(e["objectif_id"])["date_limite"] == r["date_echeance"]


def test_liste_avec_provisions():
    e = _echeance()
    trouvee = next(x for x in lister_echeances() if x["id"] == e["id"])
    assert trouvee["provision"]["objectif_id"] == e["objectif_id"]
