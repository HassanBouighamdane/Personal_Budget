
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

CATEGORIES_DEFAUT = [
    ("Alimentation & Courses", 1500), ("Restaurants & Cafés", 200),
    ("Transport & Carburant", 400), ("Loyer", 300),
    ("Factures & Abonnements", 700), ("Santé & Pharmacie", 100),
    ("Vêtements & Soins", 200), ("Loisirs & Sorties", 500),
    ("Famille & Cadeaux", 1500), ("Éducation & Formation", 200),
    ("Imprévus & Divers", 1000),
]
SOURCES_DEFAUT = [("Salaire",), ("Prime",), ("Freelance",), ("Remboursement",)]
PAIEMENTS_DEFAUT = [("Espèces",), ("Carte",), ("Virement",)]