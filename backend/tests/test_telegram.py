# -*- coding: utf-8 -*-
"""
Tests de la saisie par Telegram : lecture des messages (sans base), catégorie devinée, dépense
enregistrée puis annulée, catégorie demandée par boutons, message reçu deux fois, autre
conversation ignorée. Les appels à Telegram sont remplacés (monkeypatch) ; les données de test
sont datées de 1901 et portent le préfixe ZZTEST.

Lancement :
    cd backend
    pytest tests/test_telegram.py -v
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from database import db
from routes import telegram

PREFIXE = "ZZTEST"
CAT = f"{PREFIXE} Zqfood"
AUJ = date(1901, 5, 10)
CHAT = "424242"
UPDATE = -1_901_000          # identifiants négatifs : jamais ceux de vrais messages


# ---------------------------------------------------------------------------
# Lecture des messages (sans base)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("texte, attendu", [
    ("45 café", {"type": "depense", "montant": 45.0, "texte": "café", "jours": 0}),
    ("café 45,50 hier", {"type": "depense", "montant": 45.5, "texte": "café", "jours": 1}),
    ("avant hier 30 taxi", {"type": "depense", "montant": 30.0, "texte": "taxi", "jours": 2}),
    ("+8000 salaire", {"type": "revenu", "montant": 8000.0, "texte": "salaire"}),
    ("+ 8000 salaire", {"type": "revenu", "montant": 8000.0, "texte": "salaire"}),
    ("12dh pain", {"montant": 12.0, "texte": "pain"}),
])
def test_analyser_operations(texte, attendu):
    lu = telegram.analyser(texte)
    assert lu["commande"] == "operation"
    assert {k: lu[k] for k in attendu} == attendu


def test_analyser_tags_et_commandes():
    assert telegram.analyser("1200 courses #Turquie-2027 #maison")["tags"] == ["turquie-2027", "maison"]
    assert telegram.analyser("?")["commande"] == "reste"
    assert telegram.analyser("/reste")["commande"] == "reste"
    assert telegram.analyser("/start")["commande"] == "aide"
    assert telegram.analyser("solde") == {"commande": "solde", "montant": None}
    assert telegram.analyser("solde 12 500,50") == {"commande": "solde", "montant": 12500.5}
    assert telegram.analyser("solde beaucoup")["commande"] is None
    assert telegram.analyser("bonjour")["commande"] is None
    assert telegram.analyser("0 café")["commande"] is None


def test_mots_du_message_retrouves_dans_un_nom():
    assert telegram._correspond("Restaurants & Cafés", telegram._mots("café")) == 1
    assert telegram._correspond("Alimentation & Courses", telegram._mots("courses du mois")) == 1
    assert telegram._correspond("Transport & Carburant", telegram._mots("pain")) == 0


# ---------------------------------------------------------------------------
# Avec la base
# ---------------------------------------------------------------------------
def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM depenses WHERE categorie LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM telegram_messages WHERE update_id <= %s AND update_id > %s", (UPDATE, UPDATE - 100))
        c.execute("DELETE FROM categories WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture
def envois(monkeypatch):
    """Appels à Telegram notés au lieu d'être envoyés ; la conversation autorisée est CHAT."""
    _nettoyer()
    with db() as c:
        cid = c.execute("INSERT INTO categories(nom, budget) VALUES (%s, 500) RETURNING id", (CAT,)).fetchone()["id"]
        c.execute("INSERT INTO budgets_historique(categorie_id, mois_debut, budget, fixe) VALUES (%s, '1900-01', 500, false)", (cid,))
    monkeypatch.setattr(telegram, "TELEGRAM_CHAT_ID", CHAT)
    appels = []
    monkeypatch.setattr(telegram, "appel_telegram", lambda methode, champs: appels.append((methode, champs)) or {})
    yield appels
    _nettoyer()


def _message(n: int, texte: str, chat: str = CHAT) -> dict:
    return {"update_id": UPDATE - n, "message": {"message_id": 1, "chat": {"id": int(chat)}, "text": texte}}


def _clic(n: int, data: str) -> dict:
    return {"update_id": UPDATE - n, "callback_query": {"id": "q", "data": data,
                                                         "message": {"message_id": 7, "chat": {"id": int(CHAT)}}}}


def _depenses():
    with db() as c:
        return c.execute("SELECT id, date, categorie, description, montant FROM depenses WHERE categorie=%s ORDER BY id",
                         (CAT,)).fetchall()


@pytest.mark.base
def test_categorie_devinee_par_son_nom_puis_annulee(envois):
    telegram.traiter(_message(1, "45 zqfood hier"), AUJ)
    d = _depenses()
    assert len(d) == 1 and d[0]["montant"] == 45 and d[0]["date"] == "1901-05-09" and d[0]["description"] == "zqfood"
    methode, champs = envois[-1]
    assert methode == "sendMessage" and champs["text"].startswith("✓ 45 DH · " + CAT)
    assert "Reste 455 DH" in champs["text"]
    annuler = champs["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    telegram.traiter(_clic(2, annuler), AUJ)
    assert not _depenses()
    assert envois[-1][0] == "editMessageText" and envois[-1][1]["text"].startswith("↩️ Annulé")


@pytest.mark.base
def test_categorie_inconnue_demandee_par_boutons(envois):
    telegram.traiter(_message(1, "30 xqzwv"), AUJ)
    assert not _depenses()
    clavier = envois[-1][1]["reply_markup"]["inline_keyboard"]
    with db() as c:
        cid = c.execute("SELECT id FROM categories WHERE nom=%s", (CAT,)).fetchone()["id"]
    choix = next(b["callback_data"] for ligne in clavier for b in ligne if b["callback_data"].endswith(f":{cid}"))
    telegram.traiter(_clic(2, choix), AUJ)
    d = _depenses()
    assert len(d) == 1 and d[0]["montant"] == 30 and d[0]["description"] == "xqzwv"
    # Un second clic sur le même bouton n'enregistre rien de plus
    telegram.traiter(_clic(3, choix), AUJ)
    assert len(_depenses()) == 1


@pytest.mark.base
def test_message_recu_deux_fois_traite_une_fois(envois):
    telegram.traiter(_message(1, "12 zqfood"), AUJ)
    telegram.traiter(_message(1, "12 zqfood"), AUJ)
    assert len(_depenses()) == 1 and len(envois) == 1


@pytest.mark.base
def test_autre_conversation_ignoree(envois):
    telegram.traiter(_message(1, "12 zqfood", chat="999"), AUJ)
    assert not _depenses() and not envois
