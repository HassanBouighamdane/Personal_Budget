
# -*- coding: utf-8 -*-
"""Configuration : variables d'environnement (.env) et constantes."""
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Charge le fichier .env s'il existe
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass   # python-dotenv non installé : variables système uniquement

BASE_DIR = Path(__file__).parent
# Frontend React compilé (npm run build dans frontend-react/)
FRONT_DIR = BASE_DIR.parent / "frontend-react" / "dist"

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
DUREE_SESSION_JOURS = 1            # session ordinaire
DUREE_SESSION_LONGUE_JOURS = 30    # « Rester connecté » ; les deux se prolongent pendant l'utilisation

# Fuseau de l'utilisateur : le serveur (Render) tourne en UTC, ce qui décalerait « aujourd'hui »
# (mois en cours, projection, objectifs de lecture) autour de minuit.
FUSEAU = ZoneInfo(os.environ.get("FUSEAU", "Africa/Casablanca"))


def aujourdhui() -> date:
    """Date du jour dans le fuseau de l'utilisateur (et non celui du serveur)."""
    return datetime.now(FUSEAU).date()

# Rappels et résumé hebdomadaire (cf. messagerie.py) : un canal est actif dès que ses variables sont
# renseignées. Telegram : jeton du bot (@BotFather) et identifiant de la conversation.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
# E-mail : serveur SMTP (Gmail : smtp.gmail.com, port 587, mot de passe d'application)
SMTP_HOTE = os.environ.get("SMTP_HOTE", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_UTILISATEUR = os.environ.get("SMTP_UTILISATEUR", "").strip()
SMTP_MOT_DE_PASSE = os.environ.get("SMTP_MOT_DE_PASSE", "")
EMAIL_DESTINATAIRE = os.environ.get("EMAIL_DESTINATAIRE", "").strip() or SMTP_UTILISATEUR
# Secret exigé par /api/cron/quotidien (Vercel l'envoie tout seul dans l'en-tête Authorization)
CRON_SECRET = os.environ.get("CRON_SECRET", "").strip()

# Origines autorisées à appeler l'API depuis un AUTRE domaine (séparées par des virgules).
# Vide par défaut : le frontend est servi par ce même serveur, aucune autorisation n'est
# nécessaire. À renseigner seulement si le frontend est un jour hébergé ailleurs.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# Anti force brute sur /api/login : après LOGIN_MAX_ECHECS échecs pour un même nom
# d'utilisateur en LOGIN_FENETRE_MIN minutes, les tentatives sont bloquées pendant cette durée.
LOGIN_MAX_ECHECS = 10
LOGIN_FENETRE_MIN = 15

# (nom, budget mensuel, charge fixe). Une charge fixe (loyer, factures) tombe en une fois dans le
# mois : elle est exclue du budget journalier/hebdo et traitée à part dans la projection.
CATEGORIES_DEFAUT = [
    ("Alimentation & Courses", 1500, False), ("Restaurants & Cafés", 200, False),
    ("Transport & Carburant", 400, False), ("Loyer", 300, True),
    ("Factures & Abonnements", 700, True), ("Santé & Pharmacie", 100, False),
    ("Vêtements & Soins", 200, False), ("Loisirs & Sorties", 500, False),
    ("Famille & Cadeaux", 1500, False), ("Éducation & Formation", 200, False),
    ("Imprévus & Divers", 1000, False),
]
# (nom, revenu du travail) : un remboursement est de l'argent qui revient, pas gagné
SOURCES_DEFAUT = [("Salaire", True), ("Prime", True), ("Freelance", True), ("Remboursement", False)]

# Module Lectures : genres proposés au premier démarrage, objectifs par défaut (nombre de livres)
GENRES_DEFAUT = [
    ("Roman",), ("Développement personnel",), ("Essai",), ("Histoire",), ("Biographie",),
    ("Philosophie",), ("Science",), ("Économie & Finance",), ("Religion",), ("Poésie",),
]
OBJECTIF_LECTURE_ANNUEL_DEFAUT = 24
OBJECTIF_LECTURE_MENSUEL_DEFAUT = 2