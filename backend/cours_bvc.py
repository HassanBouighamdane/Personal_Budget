# -*- coding: utf-8 -*-
"""Cours des titres de la Bourse de Casablanca.

Deux sources, essayées dans l'ordre :
  1. la page « Marché actions » du site officiel casablanca-bourse.com, qui embarque les
     cours en JSON et identifie les titres par leur code BVC (ATW, IAM...) ;
  2. en secours, le flux JSON de Médias24, qui identifie les titres par leur ISIN (colonne
     `isin` de bourse_titres). Protégé par Cloudflare, il refuse certains serveurs (HTTP 403).

Aucune des deux n'est une API documentée : elles peuvent changer ou devenir injoignables
sans préavis. L'appelant doit donc traiter toute exception comme « pas de cours aujourd'hui »
et conserver les derniers cours connus (la saisie manuelle reste toujours possible).
"""
import json
import re
import ssl
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, NamedTuple, Optional

CERT_INTERMEDIAIRE = Path(__file__).parent / "certs" / "sectigo_dv_r36.pem"

URL_OFFICIEL = "https://www.casablanca-bourse.com/live-market/actions"
URL_MEDIAS24 = "https://medias24.com/content/api?method=getAllStocks&format=json"
DELAI_REPONSE_S = 10

# Codes de l'application qui diffèrent du symbole officiel de la Bourse de Casablanca
SYMBOLES_OFFICIELS = {"DARI": "DRI", "DWAY": "DWY", "IBMC": "IBC", "NAKL": "NKL", "SAHM": "SAH"}


class Cours(NamedTuple):
    source: str
    par_code: Dict[str, Decimal]    # source officielle : symbole BVC → cours
    par_isin: Dict[str, Decimal]    # Médias24 : ISIN → cours

    def de(self, code: str, isin: Optional[str]) -> Optional[Decimal]:
        """Cours d'un titre, ou None s'il est absent de la source."""
        return self.par_code.get(SYMBOLES_OFFICIELS.get(code, code)) or self.par_isin.get(isin or "")


def _nombre(texte) -> Optional[Decimal]:
    """« 522.00 » ou « 1 250,00 » (espace éventuellement insécable) → Decimal ; None si illisible."""
    if texte is None:
        return None
    brut = "".join(str(texte).split()).replace(",", ".")
    try:
        return Decimal(brut)
    except InvalidOperation:
        return None


def lire_cours_officiel(page: str) -> Dict[str, Decimal]:
    """Page « Marché actions » → {symbole: dernier cours}. Les cours sont dans le JSON de
    configuration de la page (live_market.actions) ; sans échange du jour, le cours de référence."""
    bloc = re.search(r'<script[^>]*data-drupal-selector="drupal-settings-json"[^>]*>(.*?)</script>', page, re.S)
    if not bloc:
        return {}
    cours = {}
    for ligne in (json.loads(bloc.group(1)).get("live_market") or {}).get("actions") or []:
        symbole = str(ligne.get("symbol") or "").strip().upper()
        valeur = _nombre(ligne.get("dernierCours"))
        if not valeur or valeur <= 0:
            valeur = _nombre(ligne.get("reference"))
        if symbole and valeur and valeur > 0:
            cours[symbole] = valeur
    return cours


def lire_cours_medias24(contenu: dict) -> Dict[str, Decimal]:
    """Réponse du flux → {ISIN: dernier cours}. À défaut de cours du jour, la clôture précédente."""
    cours = {}
    for ligne in contenu.get("result") or []:
        isin = (ligne.get("ISIN") or "").strip().upper()
        valeur = _nombre(ligne.get("cours"))
        if not valeur or valeur <= 0:
            valeur = _nombre(ligne.get("cloture"))
        if isin and valeur and valeur > 0:
            cours[isin] = valeur
    return cours


def decrire_echec(e: Exception) -> str:
    """« HTTP 403 — détail » ou « TimeoutError — détail » : cause courte, puis de quoi diagnostiquer
    dans les logs (un 403 avec `cf-mitigated` = blocage Cloudflare de l'adresse du serveur)."""
    if isinstance(e, urllib.error.HTTPError):
        try:
            debut = e.read(300).decode("utf-8", "replace").replace("\n", " ")
        except Exception:
            debut = ""
        return (f"HTTP {e.code} — cf-mitigated={e.headers.get('cf-mitigated')} "
                f"server={e.headers.get('server')} corps={debut!r}")
    return f"{type(e).__name__} — {e}"


def _contexte_tls() -> ssl.SSLContext:
    """Vérification TLS normale, plus le certificat intermédiaire Sectigo que casablanca-bourse.com
    n'envoie pas (chaîne incomplète : un navigateur le retrouve seul, Python non). La vérification
    n'est pas désactivée : le certificat du site doit toujours être signé par cette autorité.
    À remplacer si le site change d'autorité de certification (intermédiaire valable jusqu'en 2036)."""
    contexte = ssl.create_default_context()
    contexte.load_verify_locations(cafile=str(CERT_INTERMEDIAIRE))
    contexte.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return contexte


def _telecharger(url: str) -> str:
    requete = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "text/html,application/json",
    })
    with urllib.request.urlopen(requete, timeout=DELAI_REPONSE_S, context=_contexte_tls()) as reponse:
        return reponse.read().decode("utf-8", "replace")


def telecharger_cours() -> Cours:
    """Lève une exception (causes des deux sources) si aucune ne donne de cours."""
    echecs = []
    for source, charger in (
        ("Bourse de Casablanca", lambda: Cours("Bourse de Casablanca", lire_cours_officiel(_telecharger(URL_OFFICIEL)), {})),
        ("Médias24", lambda: Cours("Médias24", {}, lire_cours_medias24(json.loads(_telecharger(URL_MEDIAS24))))),
    ):
        try:
            cours = charger()
            if cours.par_code or cours.par_isin:
                return cours
            echecs.append(f"{source} : réponse sans cours (format inattendu)")
        except Exception as e:
            echecs.append(f"{source} : {decrire_echec(e)}")
    raise RuntimeError(" | ".join(echecs))


# ---------------------------------------------------------------- indices
# Page « Indices » du site officiel : comme la page des actions, elle embarque les valeurs en JSON
# ({"code":"MASI","value":17428.8994,...}). Pas une API documentée non plus.
URL_INDICES = "https://www.casablanca-bourse.com/live-market/indices"
_INDICE = re.compile(r'\{"code":"([^"]+)","value":(-?\d+(?:\.\d+)?)')


def lire_indices(page: str) -> Dict[str, Decimal]:
    """Valeur de chaque indice de la page (code → valeur) ; un indice affiché deux fois garde sa première valeur."""
    valeurs = {}
    for code, valeur in _INDICE.findall(page):
        v = _nombre(valeur)
        if v and v > 0:
            valeurs.setdefault(code, v)
    return valeurs


def telecharger_indices() -> Dict[str, Decimal]:
    """Lève une exception si la page ne répond pas ou ne contient aucun indice."""
    valeurs = lire_indices(_telecharger(URL_INDICES))
    if not valeurs:
        raise RuntimeError("Page des indices sans valeur (format inattendu)")
    return valeurs
