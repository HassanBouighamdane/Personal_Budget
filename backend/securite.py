# -*- coding: utf-8 -*-
"""Sécurité : hachage des mots de passe (PBKDF2) et sessions (cookie HttpOnly)."""
import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, Cookie

from database import db
from config import DUREE_SESSION_JOURS

def hacher_mdp(mdp: str) -> str:
    """Hache un mot de passe : PBKDF2-SHA256, 200 000 itérations, sel aléatoire."""
    sel = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", mdp.encode(), bytes.fromhex(sel), 200_000)
    return f"{sel}${h.hex()}"

def verifier_mdp(mdp: str, stocke: str) -> bool:
    try:
        sel, h = stocke.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", mdp.encode(), bytes.fromhex(sel), 200_000)
        return secrets.compare_digest(calc.hex(), h)
    except Exception:
        return False

def creer_session(utilisateur_id: int) -> str:
    """Crée une session en base et retourne son token."""
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute("DELETE FROM sessions WHERE expire < NOW()")   # nettoyage
        c.execute("INSERT INTO sessions(token,utilisateur_id,expire) VALUES(%s,%s,%s)",
                  (token, utilisateur_id, datetime.now() + timedelta(days=DUREE_SESSION_JOURS)))
    return token

def supprimer_session(token: str):
    with db() as c:
        c.execute("DELETE FROM sessions WHERE token=%s", (token,))

def utilisateur_courant(session: str | None = Cookie(default=None)) -> dict:
    """Dépendance FastAPI : vérifie le cookie de session, sinon 401."""
    if not session:
        raise HTTPException(401, "Non authentifié")
    with db() as c:
        row = c.execute("""SELECT u.id, u.nom FROM sessions s
                           JOIN utilisateurs u ON u.id = s.utilisateur_id
                           WHERE s.token=%s AND s.expire > NOW()""", (session,)).fetchone()
    if not row:
        raise HTTPException(401, "Session expirée")
    return row