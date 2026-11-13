# -*- coding: utf-8 -*-
"""
Tests de sécurité : limiteur des échecs de connexion (en base), en-têtes HTTP et limites des saisies.
Le limiteur utilise la base configurée dans .env, avec des clés préfixées ZZTEST nettoyées après coup.

Lancement :
    cd backend
    pytest tests/test_securite.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app as application
from database import db
from schemas import CategorieIn, DepenseIn, LoginIn, RevenuIn, TitreBourseIn
from securite import LimiteurEchecs

CLE = "ZZTEST:limiteur"


@pytest.fixture
def limiteur():
    def nettoyer():
        with db() as c:
            c.execute("DELETE FROM echecs_login WHERE cle LIKE 'ZZTEST%'")
    nettoyer()
    yield LimiteurEchecs(max_echecs=3, fenetre_min=15)
    nettoyer()


@pytest.mark.base
def test_le_limiteur_bloque_apres_trop_d_echecs(limiteur):
    for _ in range(3):
        limiteur.verifier(CLE)
        limiteur.echec(CLE)
    with pytest.raises(HTTPException) as exc:
        limiteur.verifier(CLE)
    assert exc.value.status_code == 429 and "15 min" in exc.value.detail


@pytest.mark.base
def test_le_limiteur_est_partage_entre_instances(limiteur):
    """Deux instances (deux serveurs Vercel) voient les mêmes échecs : ils sont en base."""
    autre = LimiteurEchecs(max_echecs=3, fenetre_min=15)
    for _ in range(3):
        limiteur.echec(CLE)
    with pytest.raises(HTTPException):
        autre.verifier(CLE)


@pytest.mark.base
def test_une_reussite_remet_le_compteur_a_zero(limiteur):
    for _ in range(3):
        limiteur.echec(CLE)
    limiteur.reussite(CLE)
    limiteur.verifier(CLE)   # ne lève plus


@pytest.mark.base
def test_les_echecs_d_une_cle_ne_bloquent_pas_les_autres(limiteur):
    for _ in range(3):
        limiteur.echec(CLE)
    limiteur.verifier(CLE + "-autre")


@pytest.mark.base
def test_les_echecs_hors_fenetre_ne_comptent_plus(limiteur):
    with db() as c:
        for _ in range(3):
            c.execute("INSERT INTO echecs_login(cle, le) VALUES(%s, now() - interval '16 minutes')", (CLE,))
    limiteur.verifier(CLE)


# ---------------------------------------------------------------- en-têtes HTTP
def test_entetes_de_securite():
    client = TestClient(application.app)
    r = client.get("/api/me")          # 401, mais les en-têtes sont posés sur toutes les réponses
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "default-src 'self'" in csp
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]   # scripts : empreintes seulement
    assert "content-security-policy" not in client.get("/openapi.json").headers


# ---------------------------------------------------------------- limites des saisies
def test_un_nom_fait_d_espaces_est_refuse_et_les_noms_sont_nettoyes():
    with pytest.raises(ValidationError):
        CategorieIn(nom="   ", budget=0)
    assert CategorieIn(nom="  Courses ", budget=0).nom == "Courses"
    assert TitreBourseIn(code=" iam ", nom="Maroc Telecom").code == "iam"   # la route le met en majuscules


@pytest.mark.parametrize("fabrique", [
    lambda: DepenseIn(date="2026-01-01", categorie="x", montant=1e11),
    lambda: DepenseIn(date="2026-01-01", categorie="x" * 101, montant=1),
    lambda: RevenuIn(date="2026-01-01", montant=1, description="x" * 501),
    lambda: DepenseIn(date="2026-01-01", categorie="x", montant=1, tags=["t"] * 51),
    lambda: LoginIn(utilisateur="admin", mot_de_passe="x" * 201),
])
def test_saisies_trop_longues_ou_trop_grandes_refusees(fabrique):
    with pytest.raises(ValidationError):
        fabrique()
