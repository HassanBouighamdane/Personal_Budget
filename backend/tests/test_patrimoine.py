# -*- coding: utf-8 -*-
"""
Tests du patrimoine net, de la réserve de sécurité et de l'estimation de la zakat.
Utilise la base configurée dans .env : les vérifications se font par DIFFÉRENCE (avant/après)
pour ne pas dépendre des données réelles ; les réglages sont sauvegardés puis restaurés.

Lancement :
    cd backend
    pytest tests/test_patrimoine.py -v
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

from config import aujourdhui
from database import db
from schemas import ActifIn, DetteIn, ReglagesPatrimoine
from routes.carnet import ajouter_dette
from routes.patrimoine import (COURS_SAISI, COURS_TRANSACTION, JOURS_HAWL, PARAMS, ajouter_actif, calculer_patrimoine,
                               charger_operations, dernier_cours, fins_de_mois, historique_patrimoine,
                               liberte_financiere, mois_avant_liberte, modifier_actif, modifier_reglages,
                               noter_patrimoine, patrimoine_aux_dates, supprimer_actif)

PREFIXE = "ZZTEST"
AUJ = aujourdhui()


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM actifs WHERE nom LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM dettes WHERE personne LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    with db() as c:
        reglages = c.execute("SELECT cle, valeur FROM params WHERE cle = ANY(%s)", (list(PARAMS),)).fetchall()
    _nettoyer()
    yield
    _nettoyer()
    with db() as c:
        c.execute("DELETE FROM params WHERE cle = ANY(%s)", (list(PARAMS),))
        for r in reglages:
            c.execute("INSERT INTO params(cle, valeur) VALUES(%s,%s)", (r["cle"], r["valeur"]))


def _actif(valeur, verse=0, type="Or / argent", zakat=False, nom="Actif"):
    return ajouter_actif(ActifIn(nom=f"{PREFIXE} {nom}", type=type, valeur=valeur, verse=verse, zakat=zakat, maj_le=AUJ))


def _ecart(avant, apres, cle):
    return round(apres[cle] - avant[cle], 2)


def test_actif_achete_avec_son_epargne_ne_compte_que_sa_plus_value():
    avant = calculer_patrimoine(AUJ)
    _actif(valeur=12000, verse=10000)
    apres = calculer_patrimoine(AUJ)
    assert _ecart(avant, apres, "autres_actifs") == 12000
    assert _ecart(avant, apres, "liquidites") == -10000        # l'argent versé a quitté les liquidités
    assert _ecart(avant, apres, "total") == 2000               # seul le gain de valeur enrichit


def test_actif_detenu_avant_l_application_s_ajoute_en_entier():
    avant = calculer_patrimoine(AUJ)
    _actif(valeur=5000)
    assert _ecart(avant, calculer_patrimoine(AUJ), "total") == 5000


def test_un_pret_deplace_l_argent_sans_changer_le_patrimoine():
    avant = calculer_patrimoine(AUJ)
    ajouter_dette(DetteIn(sens="pret", personne=f"{PREFIXE} Ali", montant=800, date_operation=AUJ))
    ajouter_dette(DetteIn(sens="emprunt", personne=f"{PREFIXE} Banque", montant=300, date_operation=AUJ))
    apres = calculer_patrimoine(AUJ)
    assert _ecart(avant, apres, "creances") == 800 and _ecart(avant, apres, "dettes") == 300
    assert _ecart(avant, apres, "liquidites") == -500          # 800 sortis, 300 entrés
    assert _ecart(avant, apres, "total") == 0


def test_solde_de_depart():
    modifier_reglages(ReglagesPatrimoine(solde_depart=0))
    avant = calculer_patrimoine(AUJ)
    modifier_reglages(ReglagesPatrimoine(solde_depart=7000))
    apres = calculer_patrimoine(AUJ)
    assert _ecart(avant, apres, "liquidites") == 7000 and _ecart(avant, apres, "total") == 7000


def test_reserve_compte_les_comptes_epargne_seulement():
    avant = calculer_patrimoine(AUJ)["reserve"]["disponible"]
    _actif(valeur=4000, type="Compte épargne", nom="Livret")
    _actif(valeur=9000, type="Immobilier", nom="Terrain")
    assert round(calculer_patrimoine(AUJ)["reserve"]["disponible"] - avant, 2) == 4000


def test_zakat_assiette_nisab_et_montant():
    modifier_reglages(ReglagesPatrimoine(solde_depart=0, prix_or_gramme=0))
    assert calculer_patrimoine(AUJ)["zakat"]["nisab"] is None and not calculer_patrimoine(AUJ)["zakat"]["atteint"]
    avant = calculer_patrimoine(AUJ)["zakat"]["detail"]["actifs"]
    _actif(valeur=100000, zakat=True, nom="Or")
    _actif(valeur=500000, zakat=False, type="Immobilier", nom="Maison")     # hors assiette
    modifier_reglages(ReglagesPatrimoine(prix_or_gramme=1000))
    z = calculer_patrimoine(AUJ)["zakat"]
    assert round(z["detail"]["actifs"] - avant, 2) == 100000
    assert z["nisab"] == 85000 and z["atteint"]
    assert z["montant"] == round(z["assiette"] * 0.025, 2)
    # Un prix de l'or qui met le nisab hors d'atteinte : rien n'est dû
    modifier_reglages(ReglagesPatrimoine(prix_or_gramme=10_000_000))
    z = calculer_patrimoine(AUJ)["zakat"]
    assert not z["atteint"] and z["montant"] == 0


def test_echeance_du_hawl():
    debut = AUJ - timedelta(days=300)
    modifier_reglages(ReglagesPatrimoine(prix_or_gramme=1000, debut_hawl=debut))
    z = calculer_patrimoine(AUJ)["zakat"]
    assert z["debut_hawl"] == debut and z["echeance"] == debut + timedelta(days=JOURS_HAWL)
    assert z["jours_restants"] == JOURS_HAWL - 300
    modifier_reglages(ReglagesPatrimoine(prix_or_gramme=1000))               # date retirée
    assert calculer_patrimoine(AUJ)["zakat"]["echeance"] is None


def test_modifier_et_supprimer_un_actif():
    a = _actif(valeur=1000)
    assert float(modifier_actif(a["id"], ActifIn(nom=f"{PREFIXE} Actif", valeur=1500, maj_le=AUJ))["valeur"]) == 1500
    supprimer_actif(a["id"])
    for appel in (lambda: supprimer_actif(a["id"]), lambda: modifier_actif(a["id"], ActifIn(nom="x", valeur=1, maj_le=AUJ))):
        with pytest.raises(HTTPException) as exc:
            appel()
        assert exc.value.status_code == 404


# ---------------------------------------------------------------- liberté financière
def test_objectif_vaut_25_fois_les_depenses_annuelles_a_4_pourcent():
    l = liberte_financiere(120000, 5000, 2500, 0.04, 0.04, date(2026, 10, 10))
    assert l["depense_annuelle"] == 60000 and l["cible"] == 1_500_000
    assert l["progression"] == 0.08 and l["annees_couvertes"] == 2.0


def test_date_atteinte_et_effet_double_d_une_economie():
    l = liberte_financiere(120000, 5000, 2500, 0.04, 0.04, date(2026, 10, 10))
    mois = round(l["annees_restantes"] * 12)
    assert 20 * 12 < mois < 30 * 12
    assert l["date_atteinte"] == date(2026 + (9 + mois) // 12, (9 + mois) % 12 + 1, 1)
    assert l["annees_gagnees"] > 0                   # plus d'épargne ET un objectif plus bas


def test_mois_avant_liberte():
    assert mois_avant_liberte(100, 0, 100, 0.04) == 0               # déjà atteint
    assert mois_avant_liberte(0, 100, 1200, 0) == 12                # sans rendement : 12 versements
    assert mois_avant_liberte(0, 0, 1000, 0.04) is None             # sans épargne ni patrimoine : jamais
    assert mois_avant_liberte(-1000, 100, 1000, 0) == 20            # une dette à rembourser d'abord


def test_le_logement_et_la_voiture_ne_comptent_pas():
    avant = calculer_patrimoine(AUJ)["liberte"]
    _actif(valeur=300000, type="Immobilier", nom="Maison")
    _actif(valeur=80000, type="Véhicule", nom="Voiture")
    _actif(valeur=5000, type="Or / argent", nom="Or")
    apres = calculer_patrimoine(AUJ)["liberte"]
    assert round(apres["exclus"] - avant["exclus"], 2) == 380000
    assert round(apres["patrimoine"] - avant["patrimoine"], 2) == 5000


def test_reglages_liberte_conserves_si_absents():
    modifier_reglages(ReglagesPatrimoine(taux_retrait=0.035, rendement=0.05))
    modifier_reglages(ReglagesPatrimoine(solde_depart=0))          # ne touche pas aux réglages de liberté
    l = calculer_patrimoine(AUJ)["liberte"]
    assert l["taux_retrait"] == 0.035 and l["rendement"] == 0.05


def test_patrimoine_note_une_fois_par_jour():
    """Une ligne par jour : un second calcul le même jour la remplace. Datée de 1901 pour ne pas
    toucher à la vraie courbe."""
    jour = date(1901, 1, 1)
    p = calculer_patrimoine(AUJ)
    try:
        noter_patrimoine(jour, p)
        noter_patrimoine(jour, {**p, "total": p["total"] + 100})
        lignes = [l for l in historique_patrimoine() if l["date"] == jour]
        assert len(lignes) == 1 and lignes[0]["total"] == round(p["total"] + 100, 2)
        assert lignes[0]["bourse"] == round(p["bourse"], 2)
        assert all(l["date"] != jour for l in historique_patrimoine(jours=30))   # hors des 30 derniers jours
    finally:
        with db() as c:
            c.execute("DELETE FROM patrimoine_historique WHERE date = %s", (jour,))


# ---------------------------------------------------------------- mois passés reconstitués
def test_fins_de_mois():
    assert fins_de_mois(date(2025, 11, 15), date(2026, 2, 28)) == [date(2025, 11, 30), date(2025, 12, 31), date(2026, 1, 31)]
    assert fins_de_mois(date(2024, 2, 3), date(2024, 3, 1)) == [date(2024, 2, 29)]      # année bissextile
    assert fins_de_mois(date(2026, 11, 2), date(2026, 11, 11)) == []                     # mois pas encore fini


def test_dernier_cours_prefere_le_cours_saisi_a_date_egale():
    cours = sorted([(date(2025, 1, 10), COURS_TRANSACTION, 100.0), (date(2025, 1, 31), COURS_TRANSACTION, 110.0),
                    (date(2025, 1, 31), COURS_SAISI, 120.0)])
    assert dernier_cours(cours, date(2025, 1, 9)) is None
    assert dernier_cours(cours, date(2025, 1, 20))[2] == 100.0
    assert dernier_cours(cours, date(2025, 1, 31))[2] == 120.0


def test_patrimoine_aux_dates_ne_compte_que_les_operations_passees():
    j1, j2 = date(2025, 1, 31), date(2025, 2, 28)
    d = {
        "solde_depart": 1000.0,
        "budget": [("2025-01-05", 5000.0), ("2025-01-20", -1500.0), ("2025-02-03", 4000.0)],
        "actifs": [{"depuis": date(2025, 2, 10), "valeur": 2000.0, "verse": 500.0}],
        "dettes": [{"sens": "pret", "date": date(2025, 1, 15), "montant": 300.0,
                    "remboursements": [(date(2025, 2, 1), 100.0)]}],
        "mouvements": [(date(2025, 1, 10), 2000.0)],                          # apport au compte Bourse
        "flux_bourse": [(date(2025, 1, 12), -1000.0), (date(2025, 2, 20), 50.0)],   # achat, dividende
        "transactions": [{"date": date(2025, 1, 12), "titre": "ZZT", "quantite": 10.0}],
        "cours": {"ZZT": [(date(2025, 1, 12), COURS_TRANSACTION, 100.0), (date(2025, 2, 28), COURS_SAISI, 130.0)]},
    }
    p1, p2 = patrimoine_aux_dates([j1, j2], d)
    # Fin janvier : 1000 + 3500 épargnés − 2000 apportés − 300 prêtés ; Bourse = 10 × 100 + 1000 d'espèces
    assert p1["liquidites"] == 2200 and p1["bourse"] == 2000 and p1["creances"] == 300 and p1["autres_actifs"] == 0
    assert p1["total"] == 2200 + 2000 + 300
    # Fin février : +4000 de revenu, 500 versés dans l'actif, 100 remboursés ; cours saisi 130, dividende 50
    assert p2["liquidites"] == 1000 + 7500 - 2000 - 500 - 200
    assert p2["bourse"] == 10 * 130 + 1000 + 50 and p2["creances"] == 200 and p2["autres_actifs"] == 2000
    assert p2["total"] == p2["liquidites"] + p2["bourse"] + 2000 + 200


def test_reconstitution_d_aujourd_hui_retrouve_le_patrimoine_hors_cours():
    """Recalculé pour aujourd'hui à partir des seules opérations datées, le patrimoine retombe sur
    calculer_patrimoine (sauf la valeur des titres, qui dépend des cours)."""
    d = charger_operations()
    p = calculer_patrimoine(AUJ)
    r = patrimoine_aux_dates([AUJ], d)[0]
    for k in ("liquidites", "creances", "dettes", "autres_actifs"):
        assert abs(r[k] - p[k]) < 0.05, k
