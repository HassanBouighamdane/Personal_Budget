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
from datetime import date
from schemas import (CiblesIn, CibleSecteur, DividendeCreate, FraisBourseCreate, TitreBourseIn,
                     TransactionBourseCreate)
from routes.bourse import (_positions_et_gains, obtenir_dashboard, creer_transaction, remplir_tpcvm_manquantes,
                           supprimer_transaction, creer_dividende, ajouter_titre, modifier_titre,
                           modifier_transaction, modifier_dividende, creer_frais, modifier_frais,
                           calculer_positions, recapitulatif_fiscal, lister_cibles, remplacer_cibles,
                           calculer_calendrier_dividendes, lister_transactions, taux_rendement_annualise)

TITRE_TEST = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM bourse_transactions WHERE titre LIKE %s", (TITRE_TEST + "%",))
        c.execute("DELETE FROM bourse_dividendes WHERE titre LIKE %s", (TITRE_TEST + "%",))
        c.execute("DELETE FROM bourse_prix WHERE titre LIKE %s", (TITRE_TEST + "%",))
        c.execute("DELETE FROM bourse_titres WHERE code LIKE %s", (TITRE_TEST + "%",))
        c.execute("DELETE FROM bourse_frais WHERE libelle LIKE %s", (TITRE_TEST + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    # Le titre de test doit exister dans la liste des titres (clé étrangère fk_bourse_transactions_titre)
    with db() as c:
        c.execute("INSERT INTO bourse_titres(code, nom) VALUES (%s, 'Titre de test')", (TITRE_TEST,))
    yield
    _nettoyer()


def _acheter(date, qte, prix, frais=0):
    return creer_transaction(TransactionBourseCreate(
        date_operation=date, titre=TITRE_TEST, type_instrument="Action",
        type_operation="Achat", quantite=qte, cours_unitaire=prix, autres_frais=frais,
    ))


def _vendre(date, qte, prix, frais=0, tpcvm=0):
    return creer_transaction(TransactionBourseCreate(
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


# ---------------------------------------------------------------------------
# B1 — supprimer un achat dont dépendent des ventes postérieures
# ---------------------------------------------------------------------------
def test_suppression_achat_refusee_si_ventes_posterieures():
    achat = _acheter("2026-01-10", 10, 100)
    vente = _vendre("2026-02-10", 10, 120)
    with pytest.raises(HTTPException) as exc:
        supprimer_transaction(achat["id"])
    assert exc.value.status_code == 400
    # Dans l'ordre inverse (la vente d'abord), la suppression passe
    supprimer_transaction(vente["id"])
    supprimer_transaction(achat["id"])


def test_suppression_achat_acceptee_si_le_reste_couvre_les_ventes():
    _acheter("2026-01-10", 10, 100)
    petit = _acheter("2026-01-20", 5, 100)
    _vendre("2026-02-10", 10, 120)
    supprimer_transaction(petit["id"])   # les 10 de janvier couvrent la vente
    pos = _position_test(_positions_et_gains()[0])
    assert pos.quantite_detenue == 0.0


# ---------------------------------------------------------------------------
# Problème 4 — titre inconnu et dividende sans achat
# ---------------------------------------------------------------------------
def test_transaction_sur_titre_inconnu_refusee():
    with pytest.raises(HTTPException) as exc:
        creer_transaction(TransactionBourseCreate(
            date_operation="2026-01-10", titre=TITRE_TEST + "XX", type_operation="Achat", quantite=1, cours_unitaire=10,
        ))
    assert exc.value.status_code == 400


def test_dividende_refuse_sans_achat_prealable():
    _acheter("2026-03-10", 10, 100)
    with pytest.raises(HTTPException) as exc:
        creer_dividende(DividendeCreate(date_operation="2026-03-01", titre=TITRE_TEST, montant=50))
    assert exc.value.status_code == 400
    assert creer_dividende(DividendeCreate(date_operation="2026-06-01", titre=TITRE_TEST, montant=50))["montant"] == 50


# ---------------------------------------------------------------------------
# B2 — renommer un code de titre vers un code déjà pris
# ---------------------------------------------------------------------------
def test_renommer_titre_vers_un_code_existant_renvoie_409():
    autre = ajouter_titre(TitreBourseIn(code=TITRE_TEST + "B", nom="Autre"))
    with pytest.raises(HTTPException) as exc:
        modifier_titre(autre["id"], TitreBourseIn(code=TITRE_TEST, nom="Autre"))
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Modification des transactions, dividendes et frais
# ---------------------------------------------------------------------------
def _tx(date_op, type_op, qte, prix=100, titre=TITRE_TEST, tpcvm=0):
    return TransactionBourseCreate(date_operation=date_op, titre=titre, type_operation=type_op,
                                   quantite=qte, cours_unitaire=prix, tpcvm=tpcvm)


def test_modifier_une_transaction():
    achat = _acheter("2026-01-10", 10, 100)
    modifie = modifier_transaction(achat["id"], _tx("2026-01-12", "Achat", 12, prix=90))
    assert (modifie["quantite"], modifie["cours_unitaire"]) == (12, 90)
    assert _position_test(_positions_et_gains()[0]).pru == 90.0


def test_modification_refusee_si_les_ventes_ne_sont_plus_couvertes():
    achat = _acheter("2026-01-10", 10, 100)
    vente = _vendre("2026-02-10", 8, 120)
    with pytest.raises(HTTPException):
        modifier_transaction(achat["id"], _tx("2026-01-10", "Achat", 5))       # 5 < 8 vendus
    with pytest.raises(HTTPException):
        modifier_transaction(achat["id"], _tx("2026-03-01", "Achat", 10))      # achat après la vente
    with pytest.raises(HTTPException):
        modifier_transaction(vente["id"], _tx("2026-02-10", "Vente", 11))      # vente > détenu
    with db() as c:
        c.execute("INSERT INTO bourse_titres(code, nom) VALUES (%s, 'Autre')", (TITRE_TEST + "B",))
    with pytest.raises(HTTPException):
        modifier_transaction(achat["id"], _tx("2026-01-10", "Achat", 10, titre=TITRE_TEST + "B"))  # ventes orphelines


def test_modifier_dividende_et_frais():
    _acheter("2026-01-10", 10, 100)
    d = creer_dividende(DividendeCreate(date_operation="2026-06-01", titre=TITRE_TEST, montant=50))
    assert modifier_dividende(d["id"], DividendeCreate(date_operation="2026-06-02", titre=TITRE_TEST, montant=55))["montant"] == 55
    with pytest.raises(HTTPException):
        modifier_dividende(d["id"], DividendeCreate(date_operation="2025-06-02", titre=TITRE_TEST, montant=55))
    f = creer_frais(FraisBourseCreate(date_operation="2026-01-31", libelle=TITRE_TEST + " abonnement", montant=19))
    assert modifier_frais(f["id"], FraisBourseCreate(date_operation="2026-01-31", libelle=TITRE_TEST + " abo", montant=21))["montant"] == 21


# ---------------------------------------------------------------------------
# Rendement des dividendes, récapitulatif fiscal, cibles par secteur
# ---------------------------------------------------------------------------
def test_rendement_des_dividendes_sur_12_mois():
    _acheter("1901-01-10", 10, 100)
    creer_dividende(DividendeCreate(date_operation="1901-06-01", titre=TITRE_TEST, montant=50))
    with db() as c:
        c.execute("INSERT INTO bourse_prix (titre, cours_actuel) VALUES (%s, 125)", (TITRE_TEST,))
    pos = _position_test(calculer_positions(date(1901, 12, 31)))
    assert (pos.dividendes_12m, pos.rendement_cout, pos.rendement_marche) == (50, 0.05, 0.04)
    assert _position_test(calculer_positions(date(1902, 7, 1))).dividendes_12m == 0


def test_recapitulatif_fiscal_annuel():
    _acheter("1901-01-10", 10, 100)
    _vendre("1901-03-10", 5, 140, tpcvm=30)          # +200
    _vendre("1901-04-10", 5, 80)                     # −100
    creer_dividende(DividendeCreate(date_operation="1901-06-01", titre=TITRE_TEST, montant=40))
    creer_frais(FraisBourseCreate(date_operation="1901-02-01", libelle=TITRE_TEST + " garde", montant=12))
    r = recapitulatif_fiscal(1901)
    assert (r["nb_ventes"], r["plus_values_brutes"], r["moins_values_brutes"], r["resultat_cessions"]) == (2, 200, -100, 100)
    assert (r["tpcvm_retenue"], r["dividendes_nets"], r["frais_compte"]) == (30, 40, 12)
    assert r["tpcvm_theorique"] == round(100 * r["taux_tpcvm"], 2)
    ligne = next(t for t in r["par_titre"] if t["titre"] == TITRE_TEST)
    assert (ligne["nb_ventes"], ligne["gain_brut"], ligne["dividendes"]) == (2, 100, 40)


def test_cibles_par_secteur():
    avant = lister_cibles()
    try:
        r = remplacer_cibles(CiblesIn(cibles=[CibleSecteur(secteur="ZZTEST Banques", cible=0.4),
                                              CibleSecteur(secteur="ZZTEST Télécoms", cible=0)]))
        assert r == [{"secteur": "ZZTEST Banques", "cible": 0.4}]      # une cible à 0 est retirée
        with pytest.raises(ValueError):
            CiblesIn(cibles=[CibleSecteur(secteur="A", cible=0.7), CibleSecteur(secteur="B", cible=0.4)])
    finally:
        remplacer_cibles(CiblesIn(cibles=[CibleSecteur(**x) for x in avant]))


# ---------------------------------------------------------------------------
# Journal des décisions et calendrier des dividendes
# ---------------------------------------------------------------------------
def test_note_d_une_transaction_enregistree_et_modifiable():
    t = creer_transaction(TransactionBourseCreate(
        date_operation="2026-01-10", titre=TITRE_TEST, type_operation="Achat", quantite=10, cours_unitaire=100,
        note="  Rendement de 5 %, dette faible  "))
    assert t["note"] == "Rendement de 5 %, dette faible"
    modifier_transaction(t["id"], TransactionBourseCreate(
        date_operation="2026-01-10", titre=TITRE_TEST, type_operation="Achat", quantite=10, cours_unitaire=100, note="Révisé"))
    assert next(x for x in lister_transactions() if x["id"] == t["id"])["note"] == "Révisé"
    # Sans note : chaîne vide, pas d'erreur
    assert _acheter("2026-01-11", 1, 100)["note"] == ""


def test_rendement_des_dividendes_ramene_a_la_quantite_detenue_aujourd_hui():
    """Dividende de 50 DH reçu sur 10 actions (5 DH par action), puis 6 vendues : il n'en reste
    que 4, la position rapporte 20 DH par an et non 50."""
    _acheter("1901-01-10", 10, 100)
    creer_dividende(DividendeCreate(date_operation="1901-06-01", titre=TITRE_TEST, montant=50))
    _vendre("1901-07-01", 6, 120)
    with db() as c:
        c.execute("INSERT INTO bourse_prix (titre, cours_actuel) VALUES (%s, 125)", (TITRE_TEST,))
    pos = _position_test(calculer_positions(date(1901, 12, 31)))
    assert pos.dividendes_12m == 20
    assert (pos.rendement_cout, pos.rendement_marche) == (0.05, 0.04)    # 20 / (4 × 100) et 20 / (4 × 125)


# ---------------------------------------------------------------------------
# Rendement annualisé (TRI) : la date des apports compte
# ---------------------------------------------------------------------------
AUJ_TRI = date(2026, 11, 11)


def test_tri_d_un_placement_unique():
    assert round(taux_rendement_annualise([(date(2025, 11, 11), -10000), (AUJ_TRI, 11000)], AUJ_TRI), 4) == 0.1
    assert round(taux_rendement_annualise([(date(2024, 11, 11), -10000), (AUJ_TRI, 12100)], AUJ_TRI), 4) == 0.1
    assert round(taux_rendement_annualise([(date(2025, 11, 11), -10000), (AUJ_TRI, 5000)], AUJ_TRI), 4) == -0.5


def test_tri_un_apport_recent_ne_dilue_pas_le_rendement():
    """La performance simple tombe à 5 % (1000 sur 20 000 apportés), le TRI reste près de 10 % par an."""
    flux = [(date(2025, 11, 11), -10000), (date(2026, 11, 10), -10000), (AUJ_TRI, 21000)]
    assert 0.099 < taux_rendement_annualise(flux, AUJ_TRI) < 0.1


def test_tri_avec_un_retrait():
    flux = [(date(2024, 11, 11), -10000), (date(2025, 11, 11), 5500), (AUJ_TRI, 6050)]
    assert round(taux_rendement_annualise(flux, AUJ_TRI), 4) == 0.1


def test_tri_absent_sans_historique_suffisant():
    assert taux_rendement_annualise([(date(2026, 10, 1), -10000), (AUJ_TRI, 10500)], AUJ_TRI) is None   # moins de 3 mois
    assert taux_rendement_annualise([(AUJ_TRI, 1000)], AUJ_TRI) is None                                   # aucun apport
    assert taux_rendement_annualise([(date(2025, 1, 1), -1000), (AUJ_TRI, 0)], AUJ_TRI) is None           # compte vide


def _calendrier(auj):
    return [l for l in calculer_calendrier_dividendes(auj)["lignes"] if l["titre"] == TITRE_TEST]


def test_calendrier_dividende_par_action_sur_la_quantite_detenue_aujourd_hui():
    _acheter("2026-01-10", 10, 100)
    creer_dividende(DividendeCreate(date_operation="2026-06-15", titre=TITRE_TEST, montant=50))   # 5 DH par action
    _acheter("2026-08-01", 10, 100)                                                               # 20 actions désormais
    (ligne,) = _calendrier(date(2026, 10, 1))
    assert ligne["par_action"] == 5 and ligne["quantite"] == 20 and ligne["montant_prevu"] == 100
    assert ligne["date_prevue"] == date(2027, 6, 15)


def test_calendrier_apres_une_vente_partielle():
    _acheter("2026-01-10", 10, 100)
    creer_dividende(DividendeCreate(date_operation="2026-06-15", titre=TITRE_TEST, montant=50))
    _vendre("2026-07-01", 6, 120)
    assert _calendrier(date(2026, 10, 1))[0]["montant_prevu"] == 20          # 4 actions × 5 DH


def test_calendrier_ignore_les_titres_vendus_et_les_dividendes_de_plus_d_un_an():
    _acheter("2025-01-10", 10, 100)
    creer_dividende(DividendeCreate(date_operation="2025-06-15", titre=TITRE_TEST, montant=50))
    assert _calendrier(date(2026, 10, 1)) == []                              # dividende vieux de plus d'un an
    assert len(_calendrier(date(2026, 3, 1))) == 1
    _vendre("2026-02-01", 10, 120)
    assert _calendrier(date(2026, 3, 1)) == []                               # plus rien de détenu
