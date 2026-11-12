# -*- coding: utf-8 -*-
"""
Carnet — Point d'entrée de l'application
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
    routes/lectures.py        livres lus, objectifs, bilan annuel
    routes/carnet.py          dettes et prêts, échéances
    routes/objectifs.py       objectifs d'épargne par projet et leurs versements
    routes/patrimoine.py      patrimoine net, autres actifs, réserve de sécurité, zakat
    routes/sauvegarde.py      téléchargement de la sauvegarde complète
    routes/rappels.py         rappels du jour et résumé hebdomadaire (Telegram / e-mail)
    routes/alertes.py         dépenses inhabituelles (catégorie, hausse d'un montant récurrent, doublon)
    routes/telegram.py        saisie rapide des dépenses en écrivant au bot Telegram

Installation :  pip install -r requirements.txt   (en local ; Vercel lit pyproject.toml)
Lancement    :  python app.py
Hébergement  :  Vercel (pyproject.toml + vercel.json, cf. DEPLOY_VERCEL.md)
"""
import base64
import hashlib
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Garantit que le dossier backend/ est dans le chemin des modules,
# quel que soit le dossier depuis lequel on lance l'application
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg.errors import ForeignKeyViolation
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import FRONT_DIR, DATABASE_URL, PORT, CORS_ORIGINS
from database import init_db, message_cle_etrangere, migrations_a_faire, _pool
from routes import (alertes, auth, configuration, transactions, rapports, bourse, lectures, carnet, objectifs, patrimoine,
                    indices, previsions, rappels, recurrences, sauvegarde, telegram)

@asynccontextmanager
async def cycle_de_vie(_app: FastAPI):
    """Au démarrage du serveur (et non à l'import du module) : schéma de la base et migrations,
    une seule fois par version déployée. Importer `app` (tests, analyse du build Vercel) ne
    touche donc pas la base de données."""
    with migrations_a_faire() as a_faire:
        if a_faire:
            init_db()
            bourse.remplir_tpcvm_manquantes()
    yield
    _pool.close()


app = FastAPI(title="Carnet — API", version="2.2", lifespan=cycle_de_vie)

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

def _empreintes_scripts_en_ligne() -> str:
    """Empreintes sha256 des <script> écrits dans index.html (le thème appliqué avant le premier
    affichage) : la CSP n'autorise que ceux-là, sans ouvrir 'unsafe-inline' à tout script."""
    try:
        html = (FRONT_DIR / "index.html").read_text(encoding="utf-8")
    except OSError:
        return ""
    corps = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, flags=re.S)
    return " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(c.encode()).digest()).decode()}'" for c in corps)


# Couvertures de livres : images venues d'autres sites (https:). Styles en ligne : Mantine en écrit
# dans l'attribut style. Polices : Google Fonts.
CSP = "; ".join([
    "default-src 'self'",
    f"script-src 'self' {_empreintes_scripts_en_ligne()}".strip(),
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com data:",
    "img-src 'self' data: blob: https:",
    # Le service worker (PWA) met les polices en cache : il les télécharge lui-même
    "connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com",
    "worker-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
ENTETES_SECURITE = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
# La documentation interactive de FastAPI charge ses scripts depuis un CDN : pas de CSP pour elle
SANS_CSP = ("/docs", "/redoc", "/openapi.json")


@app.exception_handler(ForeignKeyViolation)
async def cle_etrangere(_request: Request, e: ForeignKeyViolation):
    """Filet de sécurité : une route qui n'a pas traduit l'erreur elle-même (references_valides)
    renvoie quand même une 400 lisible, pas une 500."""
    return JSONResponse({"detail": message_cle_etrangere(e)}, status_code=400)


@app.middleware("http")
async def entetes_securite(request: Request, call_next):
    reponse = await call_next(request)
    for nom, valeur in ENTETES_SECURITE.items():
        reponse.headers.setdefault(nom, valeur)
    if not request.url.path.startswith(SANS_CSP):
        reponse.headers.setdefault("Content-Security-Policy", CSP)
    return reponse


app.include_router(auth.router)
app.include_router(configuration.router)
app.include_router(transactions.router)
app.include_router(rapports.router)
app.include_router(bourse.router)
app.include_router(indices.router)
app.include_router(lectures.router)
app.include_router(carnet.router)
app.include_router(objectifs.router)
app.include_router(patrimoine.router)
app.include_router(recurrences.router)
app.include_router(previsions.router)
app.include_router(sauvegarde.router)
app.include_router(rappels.router)
app.include_router(rappels.cron)
app.include_router(alertes.router)
app.include_router(telegram.router)
app.include_router(telegram.webhook)

# Frontend statique — monté APRÈS les routes /api pour garder leur priorité
if (FRONT_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=FRONT_DIR, html=True), name="frontend")
else:
    print(f"⚠️  Frontend introuvable ({FRONT_DIR}) : lance « npm run build » dans frontend-react/. L'API reste disponible.")

if __name__ == "__main__":
    import uvicorn
    print("=" * 56)
    print("  📒 Carnet v2.2 — module Bourse")
    print(f"     Interface : http://localhost:{PORT}")
    print(f"     API docs  : http://localhost:{PORT}/docs")
    print(f"     Base      : {DATABASE_URL.split('@')[-1]}")
    print("=" * 56)
    uvicorn.run(app, host="0.0.0.0", port=PORT)