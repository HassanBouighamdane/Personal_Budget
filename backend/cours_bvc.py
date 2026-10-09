# -*- coding: utf-8 -*-
"""Cours des titres de la Bourse de Casablanca, lus sur le flux JSON public de Médias24.

Le flux n'est ni officiel ni documenté : il peut changer ou devenir injoignable sans
préavis. L'appelant doit donc traiter toute exception comme « pas de cours aujourd'hui »
et conserver les derniers cours connus (la saisie manuelle reste toujours possible).

Les titres y sont identifiés par leur ISIN, pas par le code BVC (ATW, IAM...) : le
rapprochement se fait via la colonne `isin` de bourse_titres.
"""
import json
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

URL_COURS = "https://medias24.com/content/api?method=getAllStocks&format=json"
DELAI_REPONSE_S = 10


def _nombre(texte) -> Optional[Decimal]:
    """« 522.00 » ou « 1 250,00 » (espace éventuellement insécable) → Decimal ; None si illisible."""
    if texte is None:
        return None
    brut = "".join(str(texte).split()).replace(",", ".")
    try:
        return Decimal(brut)
    except InvalidOperation:
        return None


def lire_cours(contenu: dict) -> Dict[str, Decimal]:
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


def telecharger_cours() -> Dict[str, Decimal]:
    """Lève une exception si le flux est injoignable ou illisible."""
    requete = urllib.request.Request(URL_COURS, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(requete, timeout=DELAI_REPONSE_S) as reponse:
        cours = lire_cours(json.loads(reponse.read().decode("utf-8")))
    if not cours:
        raise ValueError("Flux des cours vide ou au format inattendu")
    return cours
