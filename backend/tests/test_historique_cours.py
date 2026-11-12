# -*- coding: utf-8 -*-
"""
Tests de l'historique des cours : jours de bourse (week-ends et jours fériés exclus), valeur et coût
du portefeuille jour après jour (calcul seul), puis la clôture du jour notée en base (une ligne par
titre détenu, seulement les cours récupérés ce soir ou saisis à la main).

Lancement :
    cd backend
    pytest tests/test_historique_cours.py -v
    pytest tests/test_historique_cours.py -v -m "not base"     # sans base de données
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from routes.bourse import raison_fermeture, valeur_aux_dates
from routes.patrimoine import COURS_HISTORIQUE, COURS_SAISI, COURS_TRANSACTION, dernier_cours


def test_jours_de_bourse():
    assert raison_fermeture(date(2026, 11, 12), {}) is None                     # jeudi
    assert raison_fermeture(date(2026, 11, 14), {}) == "week-end"               # samedi
    assert raison_fermeture(date(2026, 11, 15), {}) == "week-end"               # dimanche
    assert raison_fermeture(date(2026, 11, 18), {}) == "Fête de l'indépendance"  # mercredi férié
    assert raison_fermeture(date(2027, 3, 10), {date(2027, 3, 10): "Aïd al-Fitr"}) == "Aïd al-Fitr"


def _tx(jour, titre, achat, quantite, cours, frais=0.0):
    return {"date": jour, "titre": titre, "achat": achat, "quantite": quantite, "cours": cours,
            "net": quantite * cours + (frais if achat else -frais)}


def test_valeur_et_cout_jour_apres_jour():
    transactions = [_tx(date(2026, 11, 2), "ATW", True, 10, 500, frais=20),
                    _tx(date(2026, 11, 4), "IAM", True, 20, 100),
                    _tx(date(2026, 11, 6), "ATW", False, 5, 560)]
    cours = {"ATW": [(date(2026, 11, 3), 520.0), (date(2026, 11, 5), 550.0)], "IAM": [(date(2026, 11, 5), 110.0)]}
    jours = [date(2026, 11, 1), date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)]
    points = valeur_aux_dates(transactions, cours, jours)
    assert points[0] == {"date": date(2026, 11, 1), "valeur": 0, "cout": 0}
    assert points[1]["valeur"] == 5200 and points[1]["cout"] == 5020
    # IAM sans cours relevé le 4 : prix de son achat
    assert points[2]["valeur"] == 5200 + 2000
    assert points[3]["valeur"] == 5500 + 2200
    # Vente de la moitié d'ATW au PRU (502) : le coût restant baisse d'autant
    assert points[4]["valeur"] == 5 * 550 + 2200 and points[4]["cout"] == 2510 + 2000


def test_titre_entierement_vendu_ne_compte_plus():
    transactions = [_tx(date(2026, 11, 2), "ATW", True, 10, 500), _tx(date(2026, 11, 3), "ATW", False, 10, 510)]
    assert valeur_aux_dates(transactions, {}, [date(2026, 11, 4)])[0]["valeur"] == 0


def test_reconstitution_prefere_le_cours_saisi_puis_le_cours_note():
    cours = sorted([(date(2026, 10, 31), COURS_TRANSACTION, 100.0), (date(2026, 10, 31), COURS_HISTORIQUE, 105.0),
                    (date(2026, 11, 30), COURS_HISTORIQUE, 111.0), (date(2026, 11, 30), COURS_SAISI, 112.0)])
    assert dernier_cours(cours, date(2026, 10, 31))[2] == 105.0
    assert dernier_cours(cours, date(2026, 11, 15))[2] == 105.0
    assert dernier_cours(cours, date(2026, 11, 30))[2] == 112.0


@pytest.mark.base
def test_cloture_notee_seulement_les_jours_de_bourse():
    from database import db
    from routes.bourse import noter_cours_du_jour
    jour, samedi, ferie = date(1901, 1, 2), date(1901, 1, 5), date(1901, 1, 3)     # mercredi, samedi, jeudi
    with db() as c:
        c.execute("DELETE FROM bourse_prix_historique WHERE date = ANY(%s)", ([jour, samedi, ferie],))
        c.execute("INSERT INTO bourse_jours_feries (date, libelle) VALUES (%s, 'ZZTEST') ON CONFLICT DO NOTHING", (ferie,))
        rows = c.execute("""SELECT p.titre, p.manuel FROM bourse_prix p WHERE p.cours_actuel > 0 AND p.titre IN (
                                SELECT titre FROM bourse_transactions GROUP BY titre
                                HAVING SUM(CASE WHEN type_operation='Achat' THEN quantite ELSE -quantite END) > 0)""").fetchall()
    detenus = {r["titre"] for r in rows}
    manuels = {r["titre"] for r in rows if r["manuel"]}
    try:
        assert noter_cours_du_jour(jour, list(detenus)) == len(detenus)
        assert noter_cours_du_jour(jour, list(detenus)) == len(detenus)    # second passage : remplacées, pas doublées
        assert noter_cours_du_jour(samedi, list(detenus)) == 0
        assert noter_cours_du_jour(ferie, list(detenus)) == 0
        # Sources en échec (aucun cours récupéré) : seuls les cours manuels sont notés
        with db() as c:
            c.execute("DELETE FROM bourse_prix_historique WHERE date=%s", (jour,))
        assert noter_cours_du_jour(jour, []) == len(manuels)
    finally:
        with db() as c:
            c.execute("DELETE FROM bourse_prix_historique WHERE date = ANY(%s)", ([jour, samedi, ferie],))
            c.execute("DELETE FROM bourse_jours_feries WHERE libelle = 'ZZTEST'")


# ---------------------------------------------------------------------------
# Cours en retard
# ---------------------------------------------------------------------------
def _titre(titre="ATW", manuel=False, maj_le=date(2026, 11, 2), cloture=None, achete=date(2026, 1, 5)):
    return {"titre": titre, "manuel": manuel, "maj_le": maj_le, "derniere_cloture": cloture, "achete_le": achete}


def test_retard_automatique_en_jours_de_bourse():
    from routes.bourse import detecter_retards
    debut = date(2026, 11, 2)
    # Jeudi 12 : clôture notée mardi 10, mercredi 11 manquée → 1 jour, pas encore d'alerte
    assert detecter_retards([_titre(cloture=date(2026, 11, 10))], date(2026, 11, 12), {}, debut) == []
    # Vendredi 13 : mercredi et jeudi manqués → alerte
    r = detecter_retards([_titre(cloture=date(2026, 11, 10))], date(2026, 11, 13), {}, debut)
    assert r == [{"titre": "ATW", "manuel": False, "depuis": date(2026, 11, 10), "jours": 2}]


def test_pas_d_alerte_le_lundi_ni_apres_un_ferie():
    from routes.bourse import detecter_retards
    debut = date(2026, 11, 2)
    # Lundi 16 : vendredi 13 noté, samedi et dimanche ne comptent pas
    assert detecter_retards([_titre(cloture=date(2026, 11, 13))], date(2026, 11, 16), {}, debut) == []
    # Jeudi 19 : clôture du mardi 17, mercredi 18 férié (Fête de l'indépendance) → 0 jour manqué
    assert detecter_retards([_titre(cloture=date(2026, 11, 17))], date(2026, 11, 19), {}, debut) == []
    # Jour férié variable saisi
    assert detecter_retards([_titre(cloture=date(2027, 3, 8))], date(2027, 3, 11), {date(2027, 3, 9): "Aïd", date(2027, 3, 10): "Aïd"},
                            debut) == []


def test_historique_neuf_ou_titre_tout_juste_achete():
    from routes.bourse import detecter_retards
    # La tâche du soir n'a encore jamais tourné : rien à signaler pour les titres automatiques
    assert detecter_retards([_titre()], date(2026, 11, 20), {}, None) == []
    # Historique lancé le mardi 10, aucune clôture pour ce titre depuis : 10, 11, 12 manqués le vendredi 13
    assert detecter_retards([_titre()], date(2026, 11, 13), {}, date(2026, 11, 10))[0]["jours"] == 3
    # Acheté hier : pas en retard
    assert detecter_retards([_titre(achete=date(2026, 11, 12))], date(2026, 11, 13), {}, date(2026, 11, 2)) == []


def test_cours_manuel_trop_ancien():
    from routes.bourse import detecter_retards
    # Saisi le lundi 2 : du 3 au 13, 8 jours de bourse le vendredi 13 (le 6, Marche verte, est férié) → alerte
    r = detecter_retards([_titre("IAM", manuel=True, maj_le=date(2026, 11, 2))], date(2026, 11, 13), {}, None)
    assert r == [{"titre": "IAM", "manuel": True, "depuis": date(2026, 11, 2), "jours": 8}]
    assert detecter_retards([_titre("IAM", manuel=True, maj_le=date(2026, 11, 10))], date(2026, 11, 13), {}, None) == []


# ---------------------------------------------------------------------------
# Cours passés importés
# ---------------------------------------------------------------------------
def test_ecart_d_un_autre_titre():
    from routes.bourse import premier_ecart
    notees = {date(2026, 11, 10): 680.0}
    assert premier_ecart({date(2026, 11, 10): 105.0}, notees, 0.10) == (date(2026, 11, 10), 105.0, 680.0)
    assert premier_ecart({date(2026, 11, 10): 700.0, date(2025, 1, 2): 500.0}, notees, 0.10) is None


@pytest.mark.base
def test_import_garde_les_clotures_notees():
    from fastapi import HTTPException
    from database import db
    from routes.bourse import importer_cours_passes
    from schemas import ImportIndiceIn
    jours = [date(1901, 1, 2), date(1901, 1, 3), date(1901, 1, 4)]
    with db() as c:
        titre = c.execute("SELECT code FROM bourse_titres ORDER BY id LIMIT 1").fetchone()["code"]
        c.execute("DELETE FROM bourse_prix_historique WHERE titre=%s AND date = ANY(%s)", (titre, jours))
        c.execute("INSERT INTO bourse_prix_historique (titre, date, cours) VALUES (%s, %s, 100)", (titre, jours[0]))
    try:
        with pytest.raises(HTTPException):       # 150 contre 100 noté : le fichier d'un autre titre
            importer_cours_passes(titre.lower(), ImportIndiceIn(valeurs=[{"date": jours[0], "valeur": 150}]))
        r = importer_cours_passes(titre, ImportIndiceIn(valeurs=[{"date": d, "valeur": 102} for d in jours]))
        assert r["importees"] == 2 and r["deja_notees"] == 1
        with db() as c:
            rows = c.execute("SELECT date, cours, source FROM bourse_prix_historique WHERE titre=%s AND date = ANY(%s) ORDER BY date",
                             (titre, jours)).fetchall()
        assert [(float(r["cours"]), r["source"]) for r in rows] == [(100, "auto"), (102, "import"), (102, "import")]
    finally:
        with db() as c:
            c.execute("DELETE FROM bourse_prix_historique WHERE titre=%s AND date = ANY(%s)", (titre, jours))
