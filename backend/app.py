# -*- coding: utf-8 -*-
"""
Mon Budget — Point d'entrée de l'application
============================================
Architecture modulaire :
    config.py            variables d'environnement, constantes
    database.py          connexion PostgreSQL, initialisation du schéma
    securite.py          hachage des mots de passe, sessions
    schemas.py            modèles Pydantic
    routes/auth.py        login, logout, mot de passe
    routes/configuration.py   catégories, sources, objectif
    routes/transactions.py    dépenses, revenus
    routes/rapports.py        résumés jour / semaine / mois / année
    routes/bourse.py          achats, ventes, commissions, TPCVM, positions, gains

Installation :  pip install -r requirements.txt
Lancement    :  python app.py
"""
import sys
from pathlib import Path

# Garantit que le dossier backend/ est dans le chemin des modules,
# quel que soit le dossier depuis lequel on lance l'application
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import FRONT_DIR, DATABASE_URL, PORT, CORS_ORIGINS
from database import init_db, _pool
from routes import auth, configuration, transactions, rapports, bourse

init_db()

app = FastAPI(title="Mon Budget — API", version="2.2")

# CORS fermé par défaut : le frontend est servi par ce même serveur (même origine), il n'en
# a pas besoin. N'ouvre l'API qu'aux origines listées explicitement dans CORS_ORIGINS.
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(configuration.router)
app.include_router(transactions.router)
app.include_router(rapports.router)
app.include_router(bourse.router)

# Frontend statique — monté APRÈS les routes /api pour garder leur priorité
if FRONT_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONT_DIR, html=True), name="frontend")

@app.on_event("shutdown")
def fermer_pool():
    _pool.close()

if __name__ == "__main__":
    import uvicorn
    print("=" * 56)
    print("  💰 Mon Budget v2.2 — module Bourse")
    print(f"     Interface : http://localhost:{PORT}")
    print(f"     API docs  : http://localhost:{PORT}/docs")
    print(f"     Base      : {DATABASE_URL.split('@')[-1]}")
    print("=" * 56)
    uvicorn.run(app, host="0.0.0.0", port=PORT)