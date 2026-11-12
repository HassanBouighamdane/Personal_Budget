# -*- coding: utf-8 -*-
"""Cohérence des dépendances : backend/requirements.txt sert en local (et aux tests), Vercel lit
pyproject.toml. Un paquet ajouté d'un côté seulement marcherait en local mais casserait le déploiement."""
import re
import sys
import tomllib
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
# Utile seulement en développement (tests)
HORS_VERCEL = {"pytest"}


def _nom(dependance: str) -> str:
    """« psycopg[binary] » → « psycopg », « psycopg-pool>=3.2 » → « psycopg-pool »."""
    return re.split(r"[\[<>=!~;\s]", dependance.strip(), maxsplit=1)[0].lower()


def test_memes_dependances_en_local_et_sur_vercel():
    lignes = (RACINE / "backend" / "requirements.txt").read_text().splitlines()
    local = {_nom(l.split("#")[0]) for l in lignes if l.split("#")[0].strip()} - HORS_VERCEL
    vercel = {_nom(d) for d in tomllib.loads((RACINE / "pyproject.toml").read_text())["project"]["dependencies"]}
    assert local == vercel


def test_point_d_entree_vercel():
    config = tomllib.loads((RACINE / "pyproject.toml").read_text())
    module, variable = config["tool"]["vercel"]["entrypoint"].split(":")
    assert (RACINE / (module.replace(".", "/") + ".py")).exists() and variable == "app"


def test_le_frontend_est_construit_au_deploiement():
    """dist/ n'est plus versionné : Vercel doit le construire, par le script de pyproject.toml,
    et aucune « buildCommand » de vercel.json ne doit le remplacer."""
    import json
    config = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    script = config["tool"]["vercel"]["scripts"]["build"].split()
    assert script[0] == "python" and (RACINE / script[1]).exists()
    assert "buildCommand" not in json.loads((RACINE / "vercel.json").read_text(encoding="utf-8"))


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


def test_migrations_une_seule_fois_par_version(monkeypatch):
    """Démarrage à froid : init_db ne tourne qu'une fois par version déployée, et une version dont
    les migrations ont échoué n'est pas notée (la suivante réessaie)."""
    sys.path.insert(0, str(RACINE / "backend"))
    import database
    from database import db, init_db, migrations_a_faire

    init_db()
    monkeypatch.setattr(database, "VERSION_DEPLOYEE", "test-version-migrations")
    with db() as c:
        c.execute("DELETE FROM migrations_appliquees WHERE version = 'test-version-migrations'")
    try:
        try:
            with migrations_a_faire() as a_faire:
                assert a_faire
                raise RuntimeError("échec simulé")
        except RuntimeError:
            pass
        with migrations_a_faire() as a_faire:
            assert a_faire            # l'échec n'a pas été noté
        with migrations_a_faire() as a_faire:
            assert not a_faire        # cette fois, c'est fait
    finally:
        with db() as c:
            c.execute("DELETE FROM migrations_appliquees WHERE version = 'test-version-migrations'")
