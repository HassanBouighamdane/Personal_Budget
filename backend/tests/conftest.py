# -*- coding: utf-8 -*-
"""
Base des tests : jamais la base réelle.

Les tests marqués `base` (ou dont le module porte `pytestmark = pytest.mark.base`) écrivent dans
la base. Ils tournent sur TEST_DATABASE_URL (variable d'environnement, ou ligne de backend/.env),
une base à part, par exemple une branche Neon de la base principale. Sans elle, ils sont sautés ;
si elle est égale au DATABASE_URL de backend/.env (la base réelle), pytest refuse de démarrer.
La base de test est d'abord mise au niveau du code (init_db), une fois par session.

Ce fichier est lu avant tout module de test, donc avant `config` : DATABASE_URL est remplacé
ici, et l'application ne voit que la base de test (ou une adresse factice sans elle).

Lancement :
    cd backend
    pytest -q                   # tout (tests de base sautés sans TEST_DATABASE_URL)
    pytest -q -m "not base"     # seulement les calculs sans base
"""
import os
from pathlib import Path

import pytest

try:
    from dotenv import dotenv_values
    _ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    _ENV = {}

SANS_BASE = "postgresql://sans-base@127.0.0.1:1/sans-base"

_test = (os.environ.get("TEST_DATABASE_URL") or _ENV.get("TEST_DATABASE_URL") or "").strip()
_reelle = {(os.environ.get("DATABASE_URL") or "").strip(), (_ENV.get("DATABASE_URL") or "").strip()} - {""}
_REFUS = None
if _test and _test in _reelle:
    _REFUS = ("TEST_DATABASE_URL est égal à DATABASE_URL : les tests écriraient dans la base réelle. "
              "Utilise une base à part (par exemple une branche Neon).")
# Avant l'import de `config` : l'application ne voit que la base de test, ou une adresse factice
os.environ["DATABASE_URL"] = _test if _test and not _REFUS else SANS_BASE


def pytest_configure(config):
    config.addinivalue_line("markers", "base: test qui lit ou écrit dans la base de test (TEST_DATABASE_URL)")
    if _REFUS:
        pytest.exit(_REFUS, returncode=2)
    if not _test:
        # Filet : un test qui ouvre une connexion sans porter le marqueur `base` est sauté, lui aussi
        # (pytest.skip lève une BaseException, que les `except Exception` du code laissent passer)
        import database

        def sans_base(*_, **__):
            pytest.skip("TEST_DATABASE_URL absent : ce test passe par la base")
        database._pool.close()
        database._pool.connection = sans_base


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "base" in item.keywords:
            if _test:
                item.fixturenames.insert(0, "_base_de_test_a_jour")
            else:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL absent : test de base sauté"))


@pytest.fixture(scope="session")
def _base_de_test_a_jour():
    """Tables et colonnes du code testé, une fois par session (une base en retard sur le code
    échouerait sinon avec UndefinedColumn)."""
    # Sous le verrou des migrations de l'application : un déploiement Vercel qui démarre sur la même
    # base au même moment (push sur preview) lance lui aussi init_db, et deux init_db simultanés
    # s'interbloquent (DeadlockDetected). Le verrou est tenu jusqu'au commit de `c`, après init_db.
    from psycopg.errors import DeadlockDetected
    from database import VERROU_MIGRATIONS, db, init_db
    for essai in range(3):
        try:
            with db() as c:
                c.execute("SELECT pg_advisory_xact_lock(%s)", (VERROU_MIGRATIONS,))
                init_db()
            return
        except DeadlockDetected:
            if essai == 2:
                raise
