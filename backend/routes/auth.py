# -*- coding: utf-8 -*-
"""Routes d'authentification : login, logout, session, mot de passe."""
from fastapi import APIRouter, HTTPException, Depends, Response, Cookie

from database import db
from securite import (hacher_mdp, verifier_mdp, creer_session,
                      supprimer_session, utilisateur_courant, limiteur_login)
from schemas import LoginIn, MdpIn
from config import DUREE_SESSION_JOURS, COOKIE_SECURE

router = APIRouter(prefix="/api", tags=["authentification"])

@router.post("/login")
def login(donnees: LoginIn, response: Response):
    nom = donnees.utilisateur.strip()
    cle = "login:" + nom.lower()
    limiteur_login.verifier(cle)   # 429 si trop d'échecs récents pour ce nom
    with db() as c:
        u = c.execute("SELECT id, mdp_hash FROM utilisateurs WHERE nom=%s", (nom,)).fetchone()
    if not u or not verifier_mdp(donnees.mot_de_passe, u["mdp_hash"]):
        limiteur_login.echec(cle)
        raise HTTPException(401, "Identifiants incorrects")
    limiteur_login.reussite(cle)
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
    # Même protection : une session volée ne doit pas permettre de deviner le mot de passe actuel
    cle = f"mdp:{u['id']}"
    limiteur_login.verifier(cle)
    with db() as c:
        row = c.execute("SELECT mdp_hash FROM utilisateurs WHERE id=%s", (u["id"],)).fetchone()
        if not verifier_mdp(donnees.actuel, row["mdp_hash"]):
            limiteur_login.echec(cle)
            raise HTTPException(400, "Mot de passe actuel incorrect")
        limiteur_login.reussite(cle)
        c.execute("UPDATE utilisateurs SET mdp_hash=%s WHERE id=%s",
                  (hacher_mdp(donnees.nouveau), u["id"]))
        c.execute("DELETE FROM sessions WHERE utilisateur_id=%s", (u["id"],))
    return {"ok": True, "message": "Mot de passe changé, reconnecte-toi"}