# -*- coding: utf-8 -*-
"""
Tests du module Lectures : bilan annuel (totaux, objectifs annuel et mensuel,
relectures, records), validation des dates, renommage des genres et 404.
Utilise la vraie base configurée dans .env : les livres de test portent un
titre préfixé ZZTEST et sont datés de 1901, une année sans données réelles ;
les objectifs sont sauvegardés puis restaurés.

Lancement :
    cd backend
    pytest tests/test_lectures.py -v
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from database import db
from schemas import LivreIn, NomIn, ObjectifsLecture
from routes.lectures import (
    ajouter_livre, modifier_livre, supprimer_livre, calculer_bilan,
    ajouter_genre, modifier_genre, obtenir_objectifs, modifier_objectifs,
)

PREFIXE = "ZZTEST"
ANNEE = 1901


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM lectures_livres WHERE titre LIKE %s OR genre LIKE %s", (PREFIXE + "%", PREFIXE + "%"))
        c.execute("DELETE FROM lectures_genres WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    objectifs = obtenir_objectifs()
    _nettoyer()
    modifier_objectifs(ObjectifsLecture(annuel=12, mensuel=1))
    yield
    _nettoyer()
    modifier_objectifs(ObjectifsLecture(**objectifs))


def _livre(mois, jour=15, titre="Livre", **champs):
    return ajouter_livre(LivreIn(titre=f"{PREFIXE} {titre}", date_fin=date(ANNEE, mois, jour), **champs))


def test_bilan_totaux_et_moyennes():
    _livre(1, titre="A", pages=200, note=4, auteur="Camus", genre="Roman")
    _livre(1, titre="B", pages=400, note=5, auteur="Camus", genre="Roman")
    _livre(3, titre="C", auteur="Hugo")   # sans pages ni note : ignoré dans les moyennes
    b = calculer_bilan(ANNEE, date(ANNEE + 5, 1, 1))
    assert b["nb_livres"] == 3
    assert b["nb_pages"] == 600
    assert b["pages_moyennes"] == 300
    assert b["note_moyenne"] == 4.5
    assert [m["livres"] for m in b["par_mois"]][:3] == [2, 0, 1]
    assert b["auteurs"][0] == {"auteur": "Camus", "livres": 2}
    assert b["genres"][0]["genre"] == "Roman" and b["genres"][1]["genre"] == "Non classé"
    assert b["plus_long"]["titre"].endswith("B") and b["plus_court"]["titre"].endswith("A")
    assert b["mieux_note"]["note"] == 5


def test_relecture_compte_deux_fois():
    _livre(2, titre="Relu")
    _livre(9, titre="Relu")
    assert calculer_bilan(ANNEE, date(ANNEE + 1, 6, 1))["nb_livres"] == 2


def test_un_livre_compte_pour_l_annee_de_sa_date_de_fin():
    ajouter_livre(LivreIn(titre=f"{PREFIXE} Chevauchement", date_debut=date(ANNEE - 1, 12, 20), date_fin=date(ANNEE, 1, 5)))
    assert calculer_bilan(ANNEE, date(ANNEE + 1, 1, 1))["nb_livres"] == 1
    b = calculer_bilan(ANNEE, date(ANNEE + 1, 1, 1))
    assert b["duree_moyenne_jours"] == 17   # du 20/12 au 05/01 inclus


def test_objectif_annuel_attendu_a_date_en_cours_d_annee():
    # 1901 n'est pas bissextile : au 2 juillet (183e jour), la moitié de l'année est écoulée
    b = calculer_bilan(ANNEE, date(ANNEE, 7, 2))
    assert b["est_annee_courante"] is True
    assert b["attendu_a_date"] == round(12 * 183 / 365, 1)
    assert b["nb_mois_ecoules"] == 7


def test_objectif_annuel_annee_passee_et_future():
    assert calculer_bilan(ANNEE, date(ANNEE + 1, 3, 1))["attendu_a_date"] == 12
    futur = calculer_bilan(ANNEE, date(ANNEE - 1, 3, 1))
    assert futur["attendu_a_date"] == 0 and futur["nb_mois_ecoules"] == 0


def test_objectif_mensuel_ne_compte_que_les_mois_ecoules():
    modifier_objectifs(ObjectifsLecture(annuel=24, mensuel=2))
    _livre(1, titre="J1"); _livre(1, titre="J2")   # janvier : atteint
    _livre(2, titre="F1")                          # février : non atteint
    _livre(5, titre="M1"); _livre(5, titre="M2")   # mai : atteint mais pas encore écoulé au 31/03
    b = calculer_bilan(ANNEE, date(ANNEE, 3, 31))
    assert b["nb_mois_objectif"] == 1
    assert b["livres_mois_courant"] == 0           # mars
    assert calculer_bilan(ANNEE, date(ANNEE + 1, 1, 1))["nb_mois_objectif"] == 2


def test_objectif_mensuel_a_zero_desactive():
    modifier_objectifs(ObjectifsLecture(annuel=0, mensuel=0))
    _livre(1)
    assert calculer_bilan(ANNEE, date(ANNEE + 1, 1, 1))["nb_mois_objectif"] == 0


def test_date_debut_apres_date_fin_refusee():
    with pytest.raises(ValidationError):
        LivreIn(titre="X", date_debut=date(ANNEE, 5, 2), date_fin=date(ANNEE, 5, 1))


def test_note_hors_bornes_refusee():
    with pytest.raises(ValidationError):
        LivreIn(titre="X", date_fin=date(ANNEE, 5, 1), note=6)


def test_modifier_et_supprimer_livre():
    l = _livre(4, pages=100)
    modifie = modifier_livre(l["id"], LivreIn(titre=f"{PREFIXE} Nouveau", date_fin=date(ANNEE, 6, 1), pages=150))
    assert modifie["titre"] == f"{PREFIXE} Nouveau" and modifie["pages"] == 150
    supprimer_livre(l["id"])
    assert calculer_bilan(ANNEE, date(ANNEE + 1, 1, 1))["nb_livres"] == 0


def test_404_sur_livre_inexistant():
    with pytest.raises(HTTPException) as e:
        supprimer_livre(-1)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        modifier_livre(-1, LivreIn(titre="X", date_fin=date(ANNEE, 1, 1)))
    assert e.value.status_code == 404


def test_renommer_genre_met_a_jour_les_livres():
    ajouter_genre(NomIn(nom=f"{PREFIXE}Genre"))
    _livre(1, genre=f"{PREFIXE}Genre")
    with db() as c:
        gid = c.execute("SELECT id FROM lectures_genres WHERE nom=%s", (f"{PREFIXE}Genre",)).fetchone()["id"]
    modifier_genre(gid, NomIn(nom=f"{PREFIXE}Renomme"))
    b = calculer_bilan(ANNEE, date(ANNEE + 1, 1, 1))
    assert b["genres"][0]["genre"] == f"{PREFIXE}Renomme"


def test_renommer_genre_vers_un_nom_existant_409():
    ajouter_genre(NomIn(nom=f"{PREFIXE}A"))
    ajouter_genre(NomIn(nom=f"{PREFIXE}B"))
    with db() as c:
        gid = c.execute("SELECT id FROM lectures_genres WHERE nom=%s", (f"{PREFIXE}A",)).fetchone()["id"]
    with pytest.raises(HTTPException) as e:
        modifier_genre(gid, NomIn(nom=f"{PREFIXE}B"))
    assert e.value.status_code == 409
