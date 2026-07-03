# -*- coding: utf-8 -*-
"""Routes d'authentification : login, logout, session, mot de passe."""
from fastapi import APIRouter, HTTPException, Depends, Response, Cookie

from database import db
from securite import (hacher_mdp, verifier_mdp, creer_session,
                      supprimer_session, utilisateur_courant)
from schemas import LoginIn, MdpIn
from config import DUREE_SESSION_JOURS, COOKIE_SECURE

router = APIRouter(prefix="/api", tags=["authentification"])

@router.post("/login")
def login(donnees: LoginIn, response: Response):
    with db() as c:
        u = c.execute("SELECT id, mdp_hash FROM utilisateurs WHERE nom=%s",
                      (donnees.utilisateur.strip(),)).fetchone()
    if not u or not verifier_mdp(donnees.mot_de_passe, u["mdp_hash"]):
        raise HTTPException(401, "Identifiants incorrects")
    token = creer_session(u["id"])
    response.set_cookie("session", token, httponly=True, samesite="lax",
                        secure=COOKIE_SECURE, max_age=DUREE_SESSION_JOURS * 86400)
    return {"ok": True}

@router.post("/logout")
def logout(response: Response, session: str | None = Cookie(default=None)):
    if session:
        supprimer_session(session)
    response.delete_cookie("session")
    return {"ok": True}

@router.get("/me")
def me(u: dict = Depends(utilisateur_courant)):
    return {"utilisateur": u["nom"]}

@router.put("/mot_de_passe")
def changer_mdp(donnees: MdpIn, u: dict = Depends(utilisateur_courant)):
    with db() as c:
        row = c.execute("SELECT mdp_hash FROM utilisateurs WHERE id=%s", (u["id"],)).fetchone()
        if not verifier_mdp(donnees.actuel, row["mdp_hash"]):
            raise HTTPException(400, "Mot de passe actuel incorrect")
        c.execute("UPDATE utilisateurs SET mdp_hash=%s WHERE id=%s",
                  (hacher_mdp(donnees.nouveau), u["id"]))
        c.execute("DELETE FROM sessions WHERE utilisateur_id=%s", (u["id"],))
    return {"ok": True, "message": "Mot de passe changé, reconnecte-toi"}