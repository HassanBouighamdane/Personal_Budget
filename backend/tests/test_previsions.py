# -*- coding: utf-8 -*-
"""
Tests des prévisions de trésorerie (calcul seul, sans base) : revenus par médiane ou récurrence,
dépenses au plus grand de récurrence / budget fixe / moyenne, déjà saisi déduit, échéances
récurrentes, emprunts, réserve des objectifs et alertes.

Lancement :
    cd backend
    pytest tests/test_previsions.py -v
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routes.previsions import dates_echeance, fenetre_historique, projeter, reste_depenses, reste_revenus

AUJ = date(2026, 11, 12)
FENETRE = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def _donnees(**k):
    d = {"depart": 10000.0, "fenetre": FENETRE, "hist_depenses": {}, "hist_revenus": {}, "deja_depenses": {},
         "deja_revenus": {}, "futur_depenses": {}, "futur_revenus": {}, "categories": {}, "recurrences": [],
         "echeances": [], "dettes": [], "objectifs": []}
    d.update(k)
    return d


def _rec(type_, nom, montant, debut="2026-01", dernier=None):
    return {"type": type_, "categorie": nom if type_ == "depense" else None, "source": nom if type_ == "revenu" else None,
            "montant": montant, "debut": debut, "dernier_mois": dernier, "actif": True}


def test_fenetre_sans_mois_avant_la_premiere_operation():
    assert fenetre_historique(AUJ, "2026-01") == FENETRE
    assert fenetre_historique(AUJ, "2026-09") == ["2026-09", "2026-10"]
    assert fenetre_historique(AUJ, None) == []


def test_revenu_par_mediane_sans_la_prime():
    hist = {"Salaire": {m: 9000.0 for m in FENETRE} | {"2026-07": 15000.0}}
    assert reste_revenus("Salaire", [], hist, FENETRE, "2026-12") == (9000.0, "moyenne")
    # Une source irrégulière (2 mois sur 6) : médiane nulle
    assert reste_revenus("Cadeau", [], {"Cadeau": {"2026-05": 500.0, "2026-08": 300.0}}, FENETRE, "2026-12")[0] == 0


def test_revenu_par_recurrence_en_priorite():
    hist = {"Salaire": {m: 9000.0 for m in FENETRE}}
    recs = [_rec("revenu", "Salaire", 9500.0, debut="2027-01")]
    assert reste_revenus("Salaire", recs, hist, FENETRE, "2026-12") == (9000.0, "moyenne")    # pas encore commencée
    assert reste_revenus("Salaire", recs, hist, FENETRE, "2027-01") == (9500.0, "recurrence")


def test_recurrence_faite_ou_passee_n_est_plus_attendue():
    recs = [_rec("revenu", "Salaire", 9000.0, dernier="2026-11")]
    hist = {"Salaire": {m: 9000.0 for m in FENETRE}}
    assert reste_revenus("Salaire", recs, hist, FENETRE, "2026-11") == (0, "recurrence")      # passé : pas de salaire
    assert reste_revenus("Salaire", recs, hist, FENETRE, "2026-12") == (9000.0, "recurrence")
    # Loyer généré à 4 600 : plus rien d'attendu, même si la moyenne est à 4 500
    loyer = [_rec("depense", "Loyer", 4600.0, dernier="2026-11")]
    hist_loyer = {"Loyer": {m: 4500.0 for m in FENETRE}}
    assert reste_depenses("Loyer", None, loyer, hist_loyer, FENETRE, "2026-11", deja=4600.0)[0] == 0
    # Pas encore généré : la récurrence, une seule fois
    assert reste_depenses("Loyer", None, loyer, hist_loyer, FENETRE, "2026-12") == (4600.0, "recurrence")
    # Médiane d'une source sans récurrence, moins ce qui est déjà arrivé
    assert reste_revenus("Prime", [], {"Prime": {m: 1000.0 for m in FENETRE}}, FENETRE, "2026-11", deja=400.0) == (600.0, "moyenne")


def test_depense_au_plus_grand_sans_double_compte():
    hist = {"Loyer": {m: 4500.0 for m in FENETRE}, "Courses": {m: 2000.0 + 100 * i for i, m in enumerate(FENETRE)}}
    info_loyer = {"budget": 4000.0, "fixe": True, "actif": True}
    assert reste_depenses("Loyer", info_loyer, [_rec("depense", "Loyer", 4800.0)], hist, FENETRE, "2026-12") == (4800.0, "recurrence")
    assert reste_depenses("Loyer", info_loyer, [], hist, FENETRE, "2026-12") == (4500.0, "moyenne")
    assert reste_depenses("Courses", {"budget": 3000.0, "fixe": False, "actif": True}, [], hist, FENETRE, "2026-12")[0] == 2250.0
    assert reste_depenses("Factures", {"budget": 600.0, "fixe": True, "actif": True}, [], {}, FENETRE, "2026-12") == (600.0, "budget")
    assert reste_depenses("Ancienne", {"budget": 0.0, "fixe": False, "actif": False}, [], {"Ancienne": {"2026-05": 900.0}},
                            FENETRE, "2026-12")[0] == 0


def test_echeance_recurrente_dans_l_horizon():
    e = {"date_echeance": date(2026, 3, 15), "recurrence_mois": 6}
    assert dates_echeance(e, AUJ, date(2027, 12, 31)) == [date(2027, 3, 15), date(2027, 9, 15)]
    assert dates_echeance({"date_echeance": date(2027, 1, 10), "recurrence_mois": None}, AUJ, date(2027, 5, 31)) == [date(2027, 1, 10)]


def test_solde_mois_par_mois():
    d = _donnees(hist_revenus={"Salaire": {m: 9000.0 for m in FENETRE}},
                 hist_depenses={"Courses": {m: 3000.0 for m in FENETRE}},
                 categories={"Courses": {"budget": 0.0, "fixe": False, "actif": True}},
                 # Ce mois-ci : salaire déjà reçu, 1 000 de courses déjà faites
                 deja_revenus={"2026-11": {"Salaire": 9000.0}}, deja_depenses={"2026-11": {"Courses": 1000.0}})
    p = projeter(d, AUJ, 2)
    nov, dec, jan = p["mois"]
    assert (nov["revenus"], nov["depenses"], nov["solde"]) == (0, 2000, 8000)
    assert (dec["revenus"], dec["depenses"], dec["solde"]) == (9000, 3000, 14000)
    assert jan["solde"] == 20000
    assert p["point_bas"] == {"mois": "2026-11", "solde": 8000}
    assert p["epargne_prevue"] == 6000
    assert nov["bas"] == nov["solde"]          # dépenses passées constantes : aucune incertitude


def test_saisi_d_avance_ajoute_une_fois():
    # Loyer de décembre déjà saisi (daté du 1er décembre) : compté une fois, pas en plus de la moyenne
    d = _donnees(hist_depenses={"Loyer": {m: 4500.0 for m in FENETRE}},
                 categories={"Loyer": {"budget": 4500.0, "fixe": True, "actif": True}},
                 deja_depenses={"2026-11": {"Loyer": 4500.0}, "2026-12": {"Loyer": 4500.0}},
                 futur_depenses={"2026-12": {"Loyer": 4500.0}})
    p = projeter(d, AUJ, 1)
    assert p["mois"][0]["depenses"] == 0
    assert p["mois"][1]["depenses"] == 4500
    assert p["mois"][1]["detail"]["depenses"][0]["base"] == "saisi"


def test_echeances_dettes_et_alerte_plancher():
    d = _donnees(depart=3000.0,
                 echeances=[{"titre": "Assurance", "date_echeance": date(2026, 12, 20), "recurrence_mois": 12, "montant": 2500,
                             "objectif_id": None}],
                 dettes=[{"sens": "emprunt", "personne": "Ali", "reste": 1000.0, "echeance": date(2026, 10, 1)},
                         {"sens": "pret", "personne": "Sara", "reste": 800.0, "echeance": date(2026, 12, 1)}])
    p = projeter(d, AUJ, 2, plancher=1000)
    nov, dec, _ = p["mois"]
    assert nov["dettes"] == 1000 and nov["detail"]["dettes"][0]["en_retard"]   # en retard : dans le mois en cours
    assert dec["echeances"] == 2500 and dec["solde"] == -500                   # le prêt à Sara n'est pas compté
    assert [a["type"] for a in p["alertes"]] == ["plancher"]


def test_comptes_epargne_comptes_dans_l_argent_disponible():
    """3000 virés vers le compte épargne : liquidités −178, mais 2822 disponibles. Pas dans le
    rouge, mais le compte courant seul ne suffit pas : la réserve est entamée."""
    p = projeter(_donnees(depart=-178.0, epargne=3000.0), AUJ, 1)
    assert (p["depart"], p["depart_liquidites"], p["depart_epargne"]) == (2822, -178, 3000)
    assert p["mois"][0]["solde"] == 2822 and [a["type"] for a in p["alertes"]] == ["reserve"]
    # Un virement vers le compte épargne déplace l'argent : la prévision ne bouge pas
    assert projeter(_donnees(depart=2822.0, epargne=0.0), AUJ, 1)["mois"] == p["mois"]


def test_alerte_reserve_entamee():
    """Compte courant 2000, épargne 3000, 1500 de plus dépensés que gagnés chaque mois."""
    d = _donnees(depart=2000.0, epargne=3000.0, hist_depenses={"Loyer": {m: 1500.0 for m in FENETRE}})
    p = projeter(d, AUJ, 3)
    assert [m["solde"] for m in p["mois"]] == [3500, 2000, 500, -1000]
    # Plancher à −2000 : jamais dans le rouge « réglé », mais la réserve est entamée dès décembre
    p = projeter(d, AUJ, 3, plancher=-2000)
    (a,) = p["alertes"]
    assert a["type"] == "reserve" and a["mois"] == "2026-12"
    assert "4 000" in a["detail"].replace(" ", " ").replace("\xa0", " ")          # 3000 − (−1000)
    # Sous le plancher : seule l'alerte plancher, plus grave
    assert [a["type"] for a in projeter(d, AUJ, 3)["alertes"]] == ["plancher"]
    # Compte courant qui tient seul : pas d'alerte
    assert projeter(_donnees(depart=5000.0, epargne=3000.0), AUJ, 3)["alertes"] == []


def test_objectifs_reserve_et_provision():
    d = _donnees(depart=5000.0,
                 objectifs=[{"id": 1, "nom": "Assurance", "reserve": 1000.0, "par_mois": 500.0, "date_limite": date(2026, 12, 20)},
                            {"id": 2, "nom": "Voyage", "reserve": 2000.0, "par_mois": 1500.0, "date_limite": date(2027, 1, 31)}],
                 echeances=[{"titre": "Assurance", "date_echeance": date(2026, 12, 20), "recurrence_mois": None, "montant": 2000,
                             "objectif_id": 1}])
    p = projeter(d, AUJ, 2)
    nov, dec, jan = p["mois"]
    assert nov["reserve"] == 1500 + 3500
    # Décembre : 2 000 versés pour l'assurance, puis payés (réserve vidée) ; le voyage continue
    assert dec["reserve"] == 0 + 5000 and dec["solde"] == 3000
    assert jan["reserve"] == 6500 and jan["libre"] == 3000 - 6500
    types = [a["type"] for a in p["alertes"]]
    assert "objectifs" in types and "rythme" in types
