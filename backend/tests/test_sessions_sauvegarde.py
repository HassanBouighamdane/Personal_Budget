# -*- coding: utf-8 -*-
"""
Tests des sessions (durée, prolongation pendant l'utilisation, expiration) et de la sauvegarde
complète (contenu exporté, lecture d'un fichier, ordre de restauration). Utilise la base
configurée dans .env. La restauration elle-même n'est pas rejouée ici : elle remplace le
contenu des tables.

Lancement :
    cd backend
    pytest tests/test_sessions_sauvegarde.py -v
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

import sauvegarde
from config import DUREE_SESSION_LONGUE_JOURS
from database import db
from securite import creer_session, supprimer_session, utilisateur_courant


@pytest.fixture
def utilisateur():
    with db() as c:
        return c.execute("SELECT id, nom FROM utilisateurs ORDER BY id LIMIT 1").fetchone()


@pytest.fixture
def session(utilisateur):
    jetons = []

    def creer(duree_jours):
        jetons.append(creer_session(utilisateur["id"], duree_jours))
        return jetons[-1]
    yield creer
    for jeton in jetons:
        supprimer_session(jeton)


def _jours_restants(jeton) -> float:
    with db() as c:
        return c.execute("SELECT EXTRACT(EPOCH FROM expire - NOW()) / 86400 j FROM sessions WHERE token=%s", (jeton,)).fetchone()["j"]


def _vieillir(jeton, jours_restants):
    with db() as c:
        c.execute("UPDATE sessions SET expire = NOW() + make_interval(secs => %s) WHERE token=%s", (jours_restants * 86400, jeton))


# ---------------------------------------------------------------- sessions
def test_session_longue_dure_30_jours(session, utilisateur):
    jeton = session(DUREE_SESSION_LONGUE_JOURS)
    assert 29.9 < _jours_restants(jeton) <= 30
    assert utilisateur_courant(jeton) == {"id": utilisateur["id"], "nom": utilisateur["nom"]}
    assert 29.9 < _jours_restants(jeton) <= 30            # encore fraîche : pas d'écriture inutile


def test_session_prolongee_quand_il_reste_moins_de_la_moitie(session):
    jeton = session(30)
    _vieillir(jeton, 20)
    utilisateur_courant(jeton)
    assert 19.9 < _jours_restants(jeton) <= 20            # plus de la moitié restante : inchangée
    _vieillir(jeton, 10)
    utilisateur_courant(jeton)
    assert 29.9 < _jours_restants(jeton) <= 30            # utilisée : repartie pour 30 jours


def test_session_ordinaire_prolongee_d_un_jour_seulement(session):
    jeton = session(1)
    _vieillir(jeton, 0.25)
    utilisateur_courant(jeton)
    assert 0.99 < _jours_restants(jeton) <= 1


def test_session_expiree_ou_absente_refusee(session):
    jeton = session(30)
    _vieillir(jeton, -0.01)
    for valeur in (jeton, None, "jeton-inconnu"):
        with pytest.raises(HTTPException) as exc:
            utilisateur_courant(valeur)
        assert exc.value.status_code == 401
    assert _jours_restants(jeton) < 0                     # une session expirée n'est pas ranimée


# ---------------------------------------------------------------- sauvegarde
def test_la_sauvegarde_contient_toutes_les_tables_sauf_comptes_et_sessions():
    donnees = sauvegarde.exporter()
    tables = set(donnees["tables"])
    assert {"depenses", "revenus", "categories", "params", "bourse_transactions", "lectures_livres", "lectures_notes",
            "dettes", "echeances", "actifs"} <= tables
    assert not tables & {"utilisateurs", "sessions"}
    assert "mdp_hash" not in sauvegarde.en_json(donnees).decode()


def test_la_sauvegarde_se_relit_brute_ou_compressee():
    donnees = sauvegarde.exporter()
    brut = sauvegarde.en_json(donnees)
    assert sauvegarde.lire(brut)["tables"].keys() == donnees["tables"].keys()
    nom, compresse = sauvegarde.fichier_compresse()
    assert nom.startswith("carnet-") and nom.endswith(".json.gz")
    assert sauvegarde.lire(compresse)["tables"] == json.loads(brut)["tables"]


def test_fichier_qui_n_est_pas_une_sauvegarde_refuse():
    for contenu in (b'{"autre": 1}', b'[]', gzip.compress(b'{"application": "Carnet"}'),
                    json.dumps({"application": "Carnet", "format": 99, "tables": {}}).encode()):
        with pytest.raises(ValueError):
            sauvegarde.lire(contenu)


def test_sauvegarde_faite_sous_l_ancien_nom_toujours_lisible():
    ancienne = json.dumps({"application": "Mon Budget", "format": 1, "tables": {"depenses": []}}).encode()
    assert sauvegarde.lire(ancienne)["tables"] == {"depenses": []}
    assert sauvegarde.exporter()["application"] == "Carnet"


def test_ordre_de_restauration_parents_avant_enfants():
    with db() as c:
        ordre = sauvegarde._ordre_d_insertion(c, sauvegarde._tables(c))
    for enfant, parent in (("budgets_historique", "categories"), ("dettes_remboursements", "dettes"),
                           ("lectures_notes", "lectures_livres"), ("lectures_notes", "lectures_a_lire"),
                           ("lectures_progression", "lectures_a_lire")):
        assert ordre.index(parent) < ordre.index(enfant)
