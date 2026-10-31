# -*- coding: utf-8 -*-
"""Cohérence des deux hébergements : Render installe backend/requirements.txt, Vercel lit
pyproject.toml. Un paquet ajouté d'un côté seulement casserait l'autre au déploiement."""
import re
import sys
import tomllib
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
# Utiles seulement sur Render (serveur) ou en développement (tests)
HORS_VERCEL = {"gunicorn", "pytest"}


def _nom(dependance: str) -> str:
    """« psycopg[binary] » → « psycopg », « psycopg-pool>=3.2 » → « psycopg-pool »."""
    return re.split(r"[\[<>=!~;\s]", dependance.strip(), maxsplit=1)[0].lower()


def test_memes_dependances_sur_render_et_vercel():
    lignes = (RACINE / "backend" / "requirements.txt").read_text().splitlines()
    render = {_nom(l.split("#")[0]) for l in lignes if l.split("#")[0].strip()} - HORS_VERCEL
    vercel = {_nom(d) for d in tomllib.loads((RACINE / "pyproject.toml").read_text())["project"]["dependencies"]}
    assert render == vercel


def test_point_d_entree_vercel():
    config = tomllib.loads((RACINE / "pyproject.toml").read_text())
    module, variable = config["tool"]["vercel"]["entrypoint"].split(":")
    assert (RACINE / (module.replace(".", "/") + ".py")).exists() and variable == "app"


def test_demarrage_ne_consomme_pas_de_numeros_de_colonnes():
    """init_db tourne à chaque démarrage à froid : une colonne ajoutée puis supprimée à chaque
    passage garde son numéro, et la table finit bloquée à la limite PostgreSQL de 1600 colonnes."""
    sys.path.insert(0, str(RACINE / "backend"))
    from database import db, init_db

    def numeros():
        with db() as c:
            return {l["table"]: l["dernier"] for l in c.execute("""
                SELECT r.relname AS table, max(a.attnum) AS dernier
                FROM pg_attribute a
                JOIN pg_class r ON r.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = r.relnamespace
                WHERE r.relkind = 'r' AND n.nspname = 'public'
                GROUP BY r.relname""").fetchall()}

    init_db()
    avant = numeros()
    init_db()
    assert numeros() == avant
