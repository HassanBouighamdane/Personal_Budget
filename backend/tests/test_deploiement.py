# -*- coding: utf-8 -*-
"""Cohérence des deux hébergements : Render installe backend/requirements.txt, Vercel lit
pyproject.toml. Un paquet ajouté d'un côté seulement casserait l'autre au déploiement."""
import re
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
