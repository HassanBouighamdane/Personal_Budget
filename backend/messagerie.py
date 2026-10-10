# -*- coding: utf-8 -*-
"""Envoi des rappels et du résumé hebdomadaire : Telegram et/ou e-mail, selon les variables
d'environnement renseignées (cf. config.py). Bibliothèque standard uniquement."""
import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from config import (EMAIL_DESTINATAIRE, SMTP_HOTE, SMTP_MOT_DE_PASSE, SMTP_PORT, SMTP_UTILISATEUR,
                    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

LIMITE_TELEGRAM = 4000   # un message Telegram est limité à 4096 caractères


class EnvoiImpossible(Exception):
    """Aucun canal configuré, ou tous les envois ont échoué."""


def canaux() -> list:
    """Canaux configurés : 'telegram', 'email'."""
    return (["telegram"] if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else []) + \
           (["email"] if SMTP_HOTE and SMTP_UTILISATEUR and SMTP_MOT_DE_PASSE and EMAIL_DESTINATAIRE else [])


def _poster_telegram(champs: dict):
    corps = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "disable_web_page_preview": True, **champs}).encode()
    requete = urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=corps,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(requete, timeout=10):
        pass


def _telegram(sujet: str, texte: str, html: str | None = None, telegram: str | None = None):
    """`telegram` : version mise en forme (HTML de Telegram). Trop longue ou refusée, le texte brut part à sa place."""
    brut = {"text": f"{sujet}\n\n{texte}"[:LIMITE_TELEGRAM]}
    try:
        if telegram and len(telegram) <= LIMITE_TELEGRAM:
            try:
                return _poster_telegram({"text": telegram, "parse_mode": "HTML"})
            except urllib.error.HTTPError as e:
                if e.code != 400:   # 400 : mise en forme refusée (ou chat_id inconnu, que l'envoi brut signalera)
                    raise
                print("[messagerie] telegram : mise en forme refusée, envoi en texte brut", flush=True)
        _poster_telegram(brut)
    except urllib.error.HTTPError as e:
        # 401 : jeton invalide ; 400 : chat_id inconnu (il faut avoir écrit une fois au bot)
        raise RuntimeError(f"refus de Telegram (HTTP {e.code}) : vérifie le jeton et le chat_id")
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Telegram injoignable ({getattr(e, 'reason', e)})")


def _email(sujet: str, texte: str, html: str | None = None, telegram: str | None = None):
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = sujet, SMTP_UTILISATEUR, EMAIL_DESTINATAIRE
    message.set_content(texte)   # repli des messageries qui n'affichent pas le HTML
    if html:
        message.add_alternative(html, subtype="html")
    classe = smtplib.SMTP_SSL if SMTP_PORT == 465 else smtplib.SMTP
    with classe(SMTP_HOTE, SMTP_PORT, timeout=15) as serveur:
        if SMTP_PORT != 465:
            serveur.starttls()
        serveur.login(SMTP_UTILISATEUR, SMTP_MOT_DE_PASSE)
        serveur.send_message(message)


_ENVOIS = {"telegram": _telegram, "email": _email}


def envoyer(sujet: str, texte: str, html: str | None = None, telegram: str | None = None) -> list:
    """Envoie sur chaque canal configuré et renvoie ceux qui ont réussi. Lève EnvoiImpossible
    s'il n'y en a aucun ; un canal en échec n'empêche pas l'autre. `html` (e-mail) et `telegram`
    sont les versions mises en forme de `texte`, facultatives."""
    actifs = canaux()
    if not actifs:
        raise EnvoiImpossible("Aucun canal configuré : renseigne les variables Telegram ou SMTP")
    reussis, erreurs = [], []
    for canal in actifs:
        try:
            _ENVOIS[canal](sujet, texte, html, telegram)
            reussis.append(canal)
        except Exception as e:
            print(f"[messagerie] {canal} : échec — {e}", flush=True)
            erreurs.append(f"{canal} : {e}")
    if not reussis:
        raise EnvoiImpossible(" · ".join(erreurs))
    return reussis
