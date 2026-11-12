# -*- coding: utf-8 -*-
"""Envoi des rappels et du résumé hebdomadaire : Telegram et/ou e-mail, selon les variables
d'environnement renseignées (cf. config.py). Bibliothèque standard uniquement."""
import json
import secrets
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
    _expedier(message)


def _expedier(message: EmailMessage):
    classe = smtplib.SMTP_SSL if SMTP_PORT == 465 else smtplib.SMTP
    with classe(SMTP_HOTE, SMTP_PORT, timeout=15) as serveur:
        if SMTP_PORT != 465:
            serveur.starttls()
        serveur.login(SMTP_UTILISATEUR, SMTP_MOT_DE_PASSE)
        serveur.send_message(message)


_ENVOIS = {"telegram": _telegram, "email": _email}


def appel_telegram(methode: str, champs: dict, timeout: int = 10) -> dict:
    """Appel quelconque de l'API du bot (sendMessage, editMessageText, setWebhook...) ; renvoie son
    `result`. RuntimeError avec la description de Telegram en cas de refus."""
    requete = urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{methode}",
                                     data=json.dumps(champs).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as r:
            return json.loads(r.read() or b"{}").get("result")
    except urllib.error.HTTPError as e:
        try:
            raison = json.loads(e.read()).get("description", "")
        except Exception:
            raison = ""
        raise RuntimeError(f"refus de Telegram (HTTP {e.code}){' : ' + raison if raison else ''}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Telegram injoignable ({getattr(e, 'reason', e)})")


def _sur_chaque_canal(envoi, seulement: list | None = None) -> list:
    """Appelle `envoi(canal)` pour chaque canal configuré (parmi `seulement` s'il est donné) et
    renvoie ceux qui ont réussi. Lève EnvoiImpossible s'il n'y en a aucun ; un canal en échec
    n'empêche pas l'autre."""
    actifs = [c for c in canaux() if seulement is None or c in seulement]
    if not actifs:
        raise EnvoiImpossible("Aucun canal configuré : renseigne les variables Telegram ou SMTP")
    reussis, erreurs = [], []
    for canal in actifs:
        try:
            envoi(canal)
            reussis.append(canal)
        except Exception as e:
            print(f"[messagerie] {canal} : échec — {e}", flush=True)
            erreurs.append(f"{canal} : {e}")
    if not reussis:
        raise EnvoiImpossible(" · ".join(erreurs))
    return reussis


def envoyer(sujet: str, texte: str, html: str | None = None, telegram: str | None = None,
            seulement: list | None = None) -> list:
    """Envoie le message sur chaque canal configuré, ou sur ceux de `seulement`. `html` (e-mail)
    et `telegram` sont les versions mises en forme de `texte`, facultatives."""
    return _sur_chaque_canal(lambda canal: _ENVOIS[canal](sujet, texte, html, telegram), seulement)


# ---------------------------------------------------------------- envoi d'un fichier joint
def _telegram_fichier(sujet: str, texte: str, nom: str, contenu: bytes):
    """sendDocument : formulaire multipart construit à la main (bibliothèque standard uniquement)."""
    limite = secrets.token_hex(16)
    champs = {"chat_id": TELEGRAM_CHAT_ID, "caption": f"{sujet}\n{texte}"[:1000]}
    corps = b"".join(f'--{limite}\r\nContent-Disposition: form-data; name="{cle}"\r\n\r\n{valeur}\r\n'.encode()
                     for cle, valeur in champs.items())
    corps += (f'--{limite}\r\nContent-Disposition: form-data; name="document"; filename="{nom}"\r\n'
              "Content-Type: application/octet-stream\r\n\r\n").encode() + contenu + f"\r\n--{limite}--\r\n".encode()
    requete = urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument", data=corps,
                                     headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    try:
        with urllib.request.urlopen(requete, timeout=30):
            pass
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"refus de Telegram (HTTP {e.code})")
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Telegram injoignable ({getattr(e, 'reason', e)})")


def _email_fichier(sujet: str, texte: str, nom: str, contenu: bytes):
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = sujet, SMTP_UTILISATEUR, EMAIL_DESTINATAIRE
    message.set_content(texte)
    message.add_attachment(contenu, maintype="application", subtype="octet-stream", filename=nom)
    _expedier(message)


_ENVOIS_FICHIER = {"telegram": _telegram_fichier, "email": _email_fichier}


def envoyer_fichier(sujet: str, texte: str, nom: str, contenu: bytes) -> list:
    """Envoie un fichier joint sur chaque canal configuré ; mêmes règles que `envoyer`."""
    return _sur_chaque_canal(lambda canal: _ENVOIS_FICHIER[canal](sujet, texte, nom, contenu))
