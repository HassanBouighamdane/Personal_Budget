# -*- coding: utf-8 -*-
"""
Tests des objectifs d'épargne par projet : avancement, rythme mensuel pour tenir la date limite,
argent repris, ordre d'affichage, suppression. Utilise la base configurée dans .env : les
données de test portent le préfixe ZZTEST.

Lancement :
    cd backend
    pytest tests/test_objectifs.py -v
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from database import db
from schemas import ProjetIn, VersementIn
from routes.objectifs import (
    ajouter_objectif, ajouter_versement, calculer, lister_objectifs, modifier_objectif, mois_jusqua,
    supprimer_objectif, supprimer_versement,
)

PREFIXE = "ZZTEST"
AUJ = date(2026, 11, 11)


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM objectifs WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _projet(nom="Voyage", cible=12000, limite=None, archive=False):
    return ajouter_objectif(ProjetIn(nom=f"{PREFIXE} {nom}", cible=cible, date_limite=limite, archive=archive))


def _verser(o, montant, jour="2026-11-01"):
    return ajouter_versement(o["id"], VersementIn(date_operation=jour, montant=montant))


def _ids(objectifs):
    return [o["id"] for o in objectifs if o["nom"].startswith(PREFIXE)]


# ---------------------------------------------------------------------------
# Calculs (sans base)
# ---------------------------------------------------------------------------
def test_mois_jusqu_a_la_date_limite_compte_le_mois_en_cours():
    assert mois_jusqua(AUJ, date(2026, 11, 30)) == 1
    assert mois_jusqua(AUJ, date(2026, 12, 31)) == 2
    assert mois_jusqua(AUJ, date(2027, 11, 1)) == 13


def test_rythme_mensuel_pour_tenir_la_date_limite():
    o = {"id": 1, "nom": "x", "cible": Decimal(12000), "date_limite": date(2027, 4, 30), "note": "", "archive": False}
    r = calculer(o, [{"montant": Decimal(3000)}], AUJ)
    assert (r["verse"], r["reste"], r["progression"]) == (3000, 9000, 0.25)
    assert (r["mois_restants"], r["par_mois"], r["en_retard"]) == (6, 1500, False)   # novembre à avril


def test_date_limite_depassee():
    o = {"id": 1, "nom": "x", "cible": Decimal(1000), "date_limite": date(2026, 10, 1), "note": "", "archive": False}
    r = calculer(o, [], AUJ)
    assert r["en_retard"] and r["par_mois"] is None
    # Atteint ou archivé : plus en retard
    assert not calculer(o, [{"montant": Decimal(1000)}], AUJ)["en_retard"]
    assert not calculer({**o, "archive": True}, [], AUJ)["en_retard"]


def test_objectif_depasse():
    o = {"id": 1, "nom": "x", "cible": Decimal(1000), "date_limite": None, "note": "", "archive": False}
    r = calculer(o, [{"montant": Decimal(1200)}], AUJ)
    assert r["atteint"] and r["reste"] == 0 and r["progression"] == 1.2 and r["par_mois"] is None


def test_nom_vide_et_montant_nul_refuses():
    with pytest.raises(ValidationError):
        ProjetIn(nom="   ", cible=100)
    with pytest.raises(ValidationError):
        ProjetIn(nom="x", cible=0)
    with pytest.raises(ValidationError):
        VersementIn(date_operation="2026-11-01", montant=0)


# ---------------------------------------------------------------------------
# Sur la base
# ---------------------------------------------------------------------------
def test_versements_et_argent_repris():
    o = _projet(cible=5000)
    o = _verser(o, 2000)
    o = _verser(o, 1500, "2026-11-05")
    assert (o["verse"], o["reste"]) == (3500, 1500)
    assert [float(v["montant"]) for v in o["versements"]] == [1500, 2000]     # le plus récent d'abord
    o = _verser(o, -500)
    assert o["verse"] == 3000
    with pytest.raises(HTTPException) as exc:
        _verser(o, -3500)                                                       # plus que ce qui est de côté
    assert exc.value.status_code == 400


def test_suppression_d_un_versement_ne_rend_pas_le_total_negatif():
    o = _verser(_verser(_projet(), 1000), -800)
    depot = next(v for v in o["versements"] if v["montant"] > 0)
    with pytest.raises(HTTPException):
        supprimer_versement(depot["id"])
    repris = next(v for v in o["versements"] if v["montant"] < 0)
    supprimer_versement(repris["id"])
    supprimer_versement(depot["id"])
    assert next(x for x in lister_objectifs() if x["id"] == o["id"])["verse"] == 0


def test_ordre_en_cours_par_date_limite_puis_archives():
    sans_date = _projet("Sans date")
    archive = _projet("Archivé", limite=date(2026, 12, 1), archive=True)
    loin = _projet("Loin", limite=date(2028, 1, 1))
    proche = _projet("Proche", limite=date(2027, 1, 1))
    assert _ids(lister_objectifs()) == [proche["id"], loin["id"], sans_date["id"], archive["id"]]


def test_modifier_archiver_et_supprimer():
    o = _verser(_projet(), 1000)
    o = modifier_objectif(o["id"], ProjetIn(nom=f"{PREFIXE} Voiture", cible=40000, archive=True))
    assert (o["nom"], o["cible"], o["archive"], o["verse"]) == (f"{PREFIXE} Voiture", 40000, True, 1000)
    supprimer_objectif(o["id"])                                                 # ses versements partent avec lui
    assert o["id"] not in _ids(lister_objectifs())
    with db() as c:
        assert not c.execute("SELECT 1 FROM objectifs_versements WHERE objectif_id=%s", (o["id"],)).fetchone()
    with pytest.raises(HTTPException) as exc:
        supprimer_objectif(o["id"])
    assert exc.value.status_code == 404


def test_modifie_le_mis_a_jour_par_le_declencheur():
    o = _projet()
    with db() as c:
        avant = c.execute("SELECT modifie_le FROM objectifs WHERE id=%s", (o["id"],)).fetchone()["modifie_le"]
    modifier_objectif(o["id"], ProjetIn(nom=f"{PREFIXE} Voyage", cible=13000))
    with db() as c:
        apres = c.execute("SELECT modifie_le FROM objectifs WHERE id=%s", (o["id"],)).fetchone()["modifie_le"]
    assert apres > avant
