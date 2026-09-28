
# -*- coding: utf-8 -*-
"""Configuration : variables d'environnement (.env) et constantes."""
import os
from pathlib import Path

# Charge le fichier .env s'il existe
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass   # python-dotenv non installé : variables système uniquement

BASE_DIR = Path(__file__).parent
FRONT_DIR = BASE_DIR.parent / "frontend"

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL manquant : renseigne-le dans backend/.env "
        "(ex : postgresql://user:motdepasse@hote:5432/nom_base)."
    )

PORT = int(os.environ.get("PORT", 8500))                       # Render fournit PORT automatiquement
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"   # true en production HTTPS
ADMIN_UTILISATEUR = os.environ.get("ADMIN_UTILISATEUR")
ADMIN_MOT_DE_PASSE = os.environ.get("ADMIN_MOT_DE_PASSE")
DUREE_SESSION_JOURS = 1

# Origines autorisées à appeler l'API depuis un AUTRE domaine (séparées par des virgules).
# Vide par défaut : le frontend est servi par ce même serveur, aucune autorisation n'est
# nécessaire. À renseigner seulement si le frontend est un jour hébergé ailleurs.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# Anti force brute sur /api/login : après LOGIN_MAX_ECHECS échecs pour un même nom
# d'utilisateur en LOGIN_FENETRE_MIN minutes, les tentatives sont bloquées pendant cette durée.
LOGIN_MAX_ECHECS = 10
LOGIN_FENETRE_MIN = 15

CATEGORIES_DEFAUT = [
    ("Alimentation & Courses", 1500), ("Restaurants & Cafés", 200),
    ("Transport & Carburant", 400), ("Loyer", 300),
    ("Factures & Abonnements", 700), ("Santé & Pharmacie", 100),
    ("Vêtements & Soins", 200), ("Loisirs & Sorties", 500),
    ("Famille & Cadeaux", 1500), ("Éducation & Formation", 200),
    ("Imprévus & Divers", 1000),
]
SOURCES_DEFAUT = [("Salaire",), ("Prime",), ("Freelance",), ("Remboursement",)]