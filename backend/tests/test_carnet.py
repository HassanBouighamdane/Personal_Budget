# -*- coding: utf-8 -*-
"""
Tests du module Carnet : reste dû d'une dette, remboursements refusés (trop élevés, avant le
prêt), échéances (jours restants, fenêtre de rappel, report d'une échéance récurrente).
Utilise la base configurée dans .env : les données de test portent le préfixe ZZTEST.

Lancement :
    cd backend
    pytest tests/test_carnet.py -v
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from database import db
from schemas import DetteIn, EcheanceIn, RemboursementIn
from routes.carnet import (
    ajouter_dette, ajouter_echeance, ajouter_mois, ajouter_remboursement, lire_dettes, lire_echeances,
    modifier_dette, reporter_echeance, supprimer_dette, supprimer_remboursement,
)

PREFIXE = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM dettes WHERE personne LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM echeances WHERE titre LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _dette(montant=1000, sens="pret", personne="Ali", jour=date(2026, 3, 1), **champs):
    return ajouter_dette(DetteIn(sens=sens, personne=f"{PREFIXE} {personne}", montant=montant, date_operation=jour, **champs))


def _echeance(jour, titre="Assurance", **champs):
    return ajouter_echeance(EcheanceIn(titre=f"{PREFIXE} {titre}", date_echeance=jour, **champs))


# ---------------------------------------------------------------- dettes
def test_reste_du_apres_remboursements_partiels():
    d = _dette(1000)
    assert d["reste"] == 1000 and d["rembourse"] == 0
    ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(2026, 3, 10), montant=300))
    d = ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(2026, 4, 2), montant=200.5))
    assert float(d["rembourse"]) == 500.5 and float(d["reste"]) == 499.5
    # Du plus récent au plus ancien
    assert [float(r["montant"]) for r in d["remboursements"]] == [200.5, 300]


def test_remboursement_superieur_au_reste_refuse():
    d = _dette(500)
    ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(2026, 3, 5), montant=400))
    with pytest.raises(HTTPException) as exc:
        ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(2026, 3, 6), montant=100.01))
    assert exc.value.status_code == 400
    # Le reste exact passe : la dette est soldée
    assert ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(2026, 3, 6), montant=100))["reste"] == 0


def test_remboursement_avant_le_pret_refuse():
    d = _dette(500, jour=date(2026, 3, 10))
    with pytest.raises(HTTPException) as exc:
        ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(2026, 3, 9), montant=50))
    assert exc.value.status_code == 400


def test_montant_ne_descend_pas_sous_le_rembourse():
    d = _dette(1000)
    ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(2026, 3, 5), montant=600))
    corps = dict(sens="pret", personne=f"{PREFIXE} Ali", date_operation=date(2026, 3, 1))
    with pytest.raises(HTTPException) as exc:
        modifier_dette(d["id"], DetteIn(montant=500, **corps))
    assert exc.value.status_code == 400
    assert float(modifier_dette(d["id"], DetteIn(montant=600, **corps))["reste"]) == 0


def test_supprimer_un_remboursement_rouvre_la_dette():
    d = _dette(200)
    d = ajouter_remboursement(d["id"], RemboursementIn(date_operation=date(2026, 3, 5), montant=200))
    supprimer_remboursement(d["remboursements"][0]["id"])
    with db() as c:
        assert float(lire_dettes(c, d["id"])[0]["reste"]) == 200


def test_dettes_en_cours_avant_les_soldees_et_par_echeance():
    soldee = _dette(100, personne="Soldee")
    ajouter_remboursement(soldee["id"], RemboursementIn(date_operation=date(2026, 3, 2), montant=100))
    sans = _dette(100, personne="SansEcheance")
    tard = _dette(100, personne="Tard", echeance=date(2026, 9, 1))
    tot = _dette(100, personne="Tot", echeance=date(2026, 5, 1))
    with db() as c:
        ordre = [d["id"] for d in lire_dettes(c) if d["personne"].startswith(PREFIXE)]
    assert ordre == [tot["id"], tard["id"], sans["id"], soldee["id"]]


def test_validation_dette():
    with pytest.raises(ValidationError):
        DetteIn(sens="pret", personne="   ", montant=10, date_operation=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        DetteIn(sens="pret", personne="Ali", montant=10, date_operation=date(2026, 1, 2), echeance=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        DetteIn(sens="don", personne="Ali", montant=10, date_operation=date(2026, 1, 1))


def test_dette_inexistante_404():
    for appel in (lambda: supprimer_dette(999999999),
                  lambda: ajouter_remboursement(999999999, RemboursementIn(date_operation=date(2026, 1, 1), montant=1)),
                  lambda: supprimer_remboursement(999999999)):
        with pytest.raises(HTTPException) as exc:
            appel()
        assert exc.value.status_code == 404


# ---------------------------------------------------------------- échéances
def test_jours_restants_et_fenetre_de_rappel():
    proche = _echeance(date(2026, 6, 20), titre="Proche", rappel_jours=30)
    loin = _echeance(date(2026, 12, 1), titre="Loin", rappel_jours=30)
    retard = _echeance(date(2026, 5, 30), titre="Retard", rappel_jours=0)
    with db() as c:
        e = {x["id"]: x for x in lire_echeances(c, date(2026, 6, 1))}
    assert (e[proche["id"]]["jours_restants"], e[proche["id"]]["a_rappeler"]) == (19, True)
    assert (e[loin["id"]]["jours_restants"], e[loin["id"]]["a_rappeler"]) == (183, False)
    assert (e[retard["id"]]["jours_restants"], e[retard["id"]]["a_rappeler"]) == (-2, True)


def test_reporter_une_echeance_recurrente():
    e = _echeance(date(2026, 1, 31), recurrence_mois=1)
    assert reporter_echeance(e["id"])["date_echeance"] == date(2026, 2, 28)
    annuelle = _echeance(date(2026, 10, 15), titre="Annuelle", recurrence_mois=12)
    assert reporter_echeance(annuelle["id"])["date_echeance"] == date(2027, 10, 15)


def test_reporter_une_echeance_ponctuelle_refuse():
    e = _echeance(date(2026, 1, 31))
    with pytest.raises(HTTPException) as exc:
        reporter_echeance(e["id"])
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        reporter_echeance(999999999)
    assert exc.value.status_code == 404


def test_ajouter_mois():
    assert ajouter_mois(date(2024, 1, 31), 1) == date(2024, 2, 29)     # année bissextile
    assert ajouter_mois(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert ajouter_mois(date(2026, 5, 15), 60) == date(2031, 5, 15)
