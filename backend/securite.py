# -*- coding: utf-8 -*-
"""Sécurité : hachage des mots de passe (PBKDF2) et sessions (cookie HttpOnly)."""
import hashlib
import secrets

from fastapi import HTTPException, Cookie

from database import db
from config import DUREE_SESSION_JOURS, LOGIN_MAX_ECHECS, LOGIN_FENETRE_MIN

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

def creer_session(utilisateur_id: int, duree_jours: int = DUREE_SESSION_JOURS) -> str:
    """Crée une session de `duree_jours` jours en base et retourne son token."""
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute("DELETE FROM sessions WHERE expire < NOW()")   # nettoyage
        c.execute("""INSERT INTO sessions(token, utilisateur_id, expire, duree_jours)
                     VALUES(%s, %s, NOW() + make_interval(days => %s), %s)""",
                  (token, utilisateur_id, duree_jours, duree_jours))
    return token

def supprimer_session(token: str):
    with db() as c:
        c.execute("DELETE FROM sessions WHERE token=%s", (token,))

def utilisateur_courant(session: str | None = Cookie(default=None)) -> dict:
    """Dépendance FastAPI : vérifie le cookie de session, sinon 401.

    Session glissante : dès qu'il reste moins de la moitié de sa durée, elle repart pour une
    durée entière. Elle n'expire donc qu'après une vraie période sans utilisation (1 jour, ou
    30 avec « Rester connecté »). C'est la base qui fait foi, pas la durée de vie du cookie."""
    if not session:
        raise HTTPException(401, "Non authentifié")
    with db() as c:
        row = c.execute("""SELECT u.id, u.nom,
                                  s.expire - NOW() < make_interval(days => s.duree_jours) / 2 AS a_prolonger
                           FROM sessions s
                           JOIN utilisateurs u ON u.id = s.utilisateur_id
                           WHERE s.token=%s AND s.expire > NOW()""", (session,)).fetchone()
        if row and row["a_prolonger"]:
            c.execute("UPDATE sessions SET expire = NOW() + make_interval(days => duree_jours) WHERE token=%s", (session,))
    if not row:
        raise HTTPException(401, "Session expirée")
    return {"id": row["id"], "nom": row["nom"]}

# ------------------------------------------------------------------ anti force brute
class LimiteurEchecs:
    """Compte les échecs de mot de passe par clé (ex : nom d'utilisateur) et bloque la clé
    après `max_echecs` échecs dans une fenêtre glissante de `fenetre_min` minutes.

    Les échecs sont gardés en base (table echecs_login) : sur Vercel, chaque instance a sa
    propre mémoire et repart de zéro à chaque démarrage, un compteur en mémoire ne limiterait
    presque rien. La table ne garde que les échecs de la fenêtre en cours."""

    def __init__(self, max_echecs: int, fenetre_min: int):
        self.max_echecs = max_echecs
        self.fenetre_min = fenetre_min

    def verifier(self, cle: str):
        """Lève une 429 si la clé est bloquée."""
        with db() as c:
            row = c.execute("""SELECT COUNT(*) n,
                                      CEIL(EXTRACT(EPOCH FROM MIN(le) + make_interval(mins => %s) - now()) / 60) reste
                               FROM echecs_login WHERE cle=%s AND le > now() - make_interval(mins => %s)""",
                            (self.fenetre_min, cle, self.fenetre_min)).fetchone()
        if row["n"] >= self.max_echecs:
            raise HTTPException(429, f"Trop de tentatives échouées. Réessaie dans {max(int(row['reste']), 1)} min.")

    def echec(self, cle: str):
        with db() as c:
            c.execute("DELETE FROM echecs_login WHERE le <= now() - make_interval(mins => %s)", (self.fenetre_min,))
            c.execute("INSERT INTO echecs_login(cle) VALUES(%s)", (cle[:200],))

    def reussite(self, cle: str):
        with db() as c:
            c.execute("DELETE FROM echecs_login WHERE cle=%s", (cle,))


limiteur_login = LimiteurEchecs(LOGIN_MAX_ECHECS, LOGIN_FENETRE_MIN)
