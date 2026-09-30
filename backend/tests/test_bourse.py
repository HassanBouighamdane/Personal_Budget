# -*- coding: utf-8 -*-
"""
Tests des calculs du module Bourse (PRU chronologique, frais, arrondi de la
performance, garde-fou sur les ventes). Utilise la vraie base configurée dans
.env : chaque test isole ses données sous un titre fictif (ZZTEST*) et les
supprime avant/après, pour ne jamais toucher aux données réelles.

Lancement :
    cd backend
    pytest tests/test_bourse.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

from database import db
from schemas import TransactionBourseCreate
from routes.bourse import _positions_et_gains, obtenir_dashboard, creer_transaction, remplir_tpcvm_manquantes

TITRE_TEST = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM bourse_transactions WHERE titre = %s", (TITRE_TEST,))
        c.execute("DELETE FROM bourse_prix WHERE titre = %s", (TITRE_TEST,))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _acheter(date, qte, prix, frais=0):
    creer_transaction(TransactionBourseCreate(
        date_operation=date, titre=TITRE_TEST, type_instrument="Action",
        type_operation="Achat", quantite=qte, cours_unitaire=prix, autres_frais=frais,
    ))


def _vendre(date, qte, prix, frais=0, tpcvm=0):
    creer_transaction(TransactionBourseCreate(
        date_operation=date, titre=TITRE_TEST, type_instrument="Action",
        type_operation="Vente", quantite=qte, cours_unitaire=prix, autres_frais=frais, tpcvm=tpcvm,
    ))


def _position_test(positions):
    return next(p for p in positions if p.titre == TITRE_TEST)


def _gain_test(gains):
    return next(g for g in gains if g.titre == TITRE_TEST)


# ---------------------------------------------------------------------------
# Bug #2 — PRU non chronologique
# ---------------------------------------------------------------------------
def test_pru_chronologique_apres_rachat():
    """Achat 10x100 (jan) -> vente 10x120 (fev) -> rachat 10x200 (mar).
    Avant correctif : PRU global = (1000+2000)/20 = 150 -> gain de vente = -300 (faux).
    Après correctif : le rachat de mars ne doit pas influencer le PRU utilisé pour
    la vente de février, qui a eu lieu avant lui."""
    _acheter("2026-01-10", 10, 100)
    _vendre("2026-02-10", 10, 120)
    _acheter("2026-03-10", 10, 200)

    positions, gains, _ = _positions_et_gains()
    pos = _position_test(positions)
    gain = _gain_test(gains)

    assert gain.pru == 100.0
    assert gain.gain_brut == 200.0          # et non -300
    assert pos.pru == 200.0                 # PRU du stock détenu = celui du rachat de mars, pas 150
    assert pos.valeur_comptable == 2000.0   # et non 1500
    assert pos.quantite_detenue == 10.0


def test_pru_intact_sans_vente():
    """Sans vente, la moyenne pondérée simple doit rester correcte (pas de régression)."""
    _acheter("2026-01-10", 10, 100)
    _acheter("2026-02-10", 10, 200)
    positions, gains, _ = _positions_et_gains()
    pos = _position_test(positions)
    assert pos.pru == 150.0   # (1000 + 2000) / 20
    assert not any(g.titre == TITRE_TEST for g in gains)


# ---------------------------------------------------------------------------
# Bug #1 — frais comptés deux fois dans le résultat de la période
# ---------------------------------------------------------------------------
def test_gain_net_compte_les_frais_une_seule_fois():
    """Achat 10x100 +10 DH frais, vente 10x120 +10 DH frais.
    Net achat = 1010, net vente = 1190. Gain brut = 1190-1010 = 180.
    TPCVM saisie = 27. Gain net = 153 (et non 133 comme avec le double comptage)."""
    _acheter("2026-01-10", 10, 100, frais=10)
    _vendre("2026-02-10", 10, 120, frais=10, tpcvm=27)

    _, gains, _ = _positions_et_gains()
    gain = _gain_test(gains)
    assert round(gain.gain_brut, 2) == 180.0
    assert round(gain.gain_net, 2) == 153.0


def test_resultat_periode_ne_double_compte_pas_les_frais():
    """Le résultat de la période ne doit varier que du gain net (153), pas de gain net
    moins les frais de transaction une deuxième fois (133)."""
    avant = obtenir_dashboard(mois=None, annee=None)
    _acheter("2026-01-10", 10, 100, frais=10)
    _vendre("2026-02-10", 10, 120, frais=10, tpcvm=27)
    apres = obtenir_dashboard(mois=None, annee=None)

    delta = round(apres.resultat_net_periode - avant.resultat_net_periode, 2)
    assert delta == 153.0


# ---------------------------------------------------------------------------
# TPCVM saisie manuellement
# ---------------------------------------------------------------------------
def test_tpcvm_saisie_utilisee_telle_quelle():
    """Gain brut 200 : la TPCVM saisie (31,50) est reprise sans recalcul (15 % donnerait 30),
    et déduite une seule fois des espèces encaissées."""
    avant = obtenir_dashboard(mois=None, annee=None)
    _acheter("2026-01-10", 10, 100)
    _vendre("2026-02-10", 10, 120, tpcvm=31.5)
    apres = obtenir_dashboard(mois=None, annee=None)

    _, gains, _ = _positions_et_gains()
    gain = _gain_test(gains)
    assert gain.tpcvm == 31.5
    assert gain.gain_net == 168.5
    # espèces : −1000 (achat) + 1200 − 31,50 (vente encaissée)
    assert round(apres.especes_disponibles - avant.especes_disponibles, 2) == 168.5


def test_tpcvm_ignoree_sur_un_achat():
    _acheter("2026-01-10", 10, 100)
    with db() as c:
        c.execute("UPDATE bourse_transactions SET tpcvm = NULL WHERE titre = %s", (TITRE_TEST,))
    creer_transaction(TransactionBourseCreate(
        date_operation="2026-01-11", titre=TITRE_TEST, type_instrument="Action",
        type_operation="Achat", quantite=1, cours_unitaire=100, tpcvm=50,
    ))
    with db() as c:
        vals = [r["tpcvm"] for r in c.execute(
            "SELECT tpcvm FROM bourse_transactions WHERE titre = %s AND date_operation = '2026-01-11'",
            (TITRE_TEST,)).fetchall()]
    assert vals == [0]


def test_remplissage_des_ventes_anciennes():
    """Une vente enregistrée avant la saisie manuelle (tpcvm NULL) reçoit une seule fois
    l'ancienne valeur calculée : taux 15 % × gain brut 200 = 30."""
    _acheter("2026-01-10", 10, 100)
    _vendre("2026-02-10", 10, 120)
    with db() as c:
        c.execute("UPDATE bourse_transactions SET tpcvm = NULL WHERE titre = %s AND type_operation = 'Vente'",
                  (TITRE_TEST,))
        taux = float(c.execute("SELECT taux_tpcvm FROM bourse_parametres LIMIT 1").fetchone()["taux_tpcvm"])
    remplir_tpcvm_manquantes()
    with db() as c:
        val = c.execute("SELECT tpcvm FROM bourse_transactions WHERE titre = %s AND type_operation = 'Vente'",
                        (TITRE_TEST,)).fetchone()["tpcvm"]
    assert float(val) == round(200 * taux, 2)


# ---------------------------------------------------------------------------
# Bug #3 — précision de la performance latente
# ---------------------------------------------------------------------------
def test_performance_latente_quatre_decimales():
    """(10 534 - 10 000) / 10 000 = 0,0534 -> 5,34 %, pas 5,00 % (arrondi à 2 décimales)."""
    _acheter("2026-01-10", 100, 100)
    with db() as c:
        c.execute(
            """INSERT INTO bourse_prix (titre, cours_actuel) VALUES (%s,%s)
               ON CONFLICT (titre) DO UPDATE SET cours_actuel = EXCLUDED.cours_actuel""",
            (TITRE_TEST, 105.34),
        )
    positions, _, _ = _positions_et_gains()
    pos = _position_test(positions)
    assert pos.performance_latente == 0.0534


# ---------------------------------------------------------------------------
# Bug #4 — vente supérieure à la quantité détenue
# ---------------------------------------------------------------------------
def test_vente_superieure_a_la_position_refusee():
    _acheter("2026-01-10", 5, 100)
    with pytest.raises(HTTPException) as exc:
        _vendre("2026-01-15", 10, 120)
    assert exc.value.status_code == 400


def test_vente_egale_a_la_position_acceptee():
    _acheter("2026-01-10", 5, 100)
    _vendre("2026-01-15", 5, 120)   # ne doit pas lever d'exception
    positions, _, _ = _positions_et_gains()
    pos = _position_test(positions)
    assert pos.quantite_detenue == 0.0


def test_vente_antidatee_entre_deux_achats_refusee_si_insuffisante():
    """Une vente insérée avec une date passée doit être validée par rapport à la
    quantité réellement détenue à CETTE date, pas à la quantité totale actuelle."""
    _acheter("2026-01-10", 5, 100)
    _acheter("2026-03-10", 5, 100)
    # Le 1er février, seules les 5 actions de janvier étaient détenues : vendre 8 doit échouer.
    with pytest.raises(HTTPException):
        _vendre("2026-02-01", 8, 120)
