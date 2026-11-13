# -*- coding: utf-8 -*-
"""
Tests des indices de référence : lecture de la page des indices, portefeuille virtuel (apports et
retraits placés dans l'indice), échantillonnage de la courbe, refus d'un fichier d'un autre indice ;
puis l'import en base (une valeur notée le soir n'est jamais remplacée). La suppression d'un import
n'est pas testée ici : elle viderait les valeurs importées de la vraie base.

Lancement :
    cd backend
    pytest tests/test_indices.py -v
    pytest tests/test_indices.py -v -m "not base"     # sans base de données
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from cours_bvc import lire_indices
from routes.indices import echantillonner, ecart_import, portefeuille_virtuel, valeur_au


def test_lecture_de_la_page_des_indices():
    page = ('...{"code":"ESGI","value":1321.450398,"previous_close":0},{"code":"MASI","value":17428.8994,"previous_close":0},'
            '{"code":"MASRN","value":50939.5456,"previous_close":0},{"code":"B\\u0026MC","value":24841.0433},'
            '{"code":"MASI","value":99999,"previous_close":0}...')
    v = lire_indices(page)
    assert v["MASI"] == Decimal("17428.8994")            # première occurrence gardée
    assert v["MASRN"] == Decimal("50939.5456")
    assert lire_indices("<html>rien</html>") == {}


VALEURS = [(date(2026, 2, 2), 48000.0), (date(2026, 6, 1), 50000.0), (date(2026, 9, 1), 52000.0), (date(2026, 11, 12), 50940.0)]


def test_valeur_au_jour_ou_la_veille():
    assert valeur_au(VALEURS, date(2026, 6, 1)) == (date(2026, 6, 1), 50000.0)
    assert valeur_au(VALEURS, date(2026, 6, 6)) == (date(2026, 6, 1), 50000.0)      # week-end : dernière connue
    assert valeur_au(VALEURS, date(2026, 1, 15)) is None


def test_portefeuille_virtuel():
    flux = [(date(2026, 2, 2), 9600.0), (date(2026, 6, 1), 5000.0), (date(2026, 9, 1), -2600.0)]
    v = portefeuille_virtuel(flux, VALEURS)
    # 0,2 + 0,1 − 0,05 = 0,25 part ; 0,25 × 50 940
    assert v["etat"] == "ok" and abs(v["parts"] - 0.25) < 1e-12
    assert v["valeur"] == 12735.0 and v["date_valeur"] == date(2026, 11, 12)
    assert [p["valeur"] for p in v["points"]] == [9600.0, 15000.0, 13000.0, 12735.0]


def test_apport_avant_l_historique_demande_un_import():
    v = portefeuille_virtuel([(date(2025, 12, 1), 1000.0), (date(2026, 3, 1), 500.0)], VALEURS)
    assert v["etat"] == "incomplet" and v["manque_avant"] == date(2025, 12, 1)
    assert portefeuille_virtuel([(date(2026, 3, 1), 500.0)], [])["etat"] == "vide"


def test_echantillonnage_garde_le_dernier_point():
    points = list(range(1000))
    e = echantillonner(points, 260)
    assert len(e) == 260 and e[0] == 0 and e[-1] == 999
    assert echantillonner(points[:10], 260) == points[:10]


def test_fichier_d_un_autre_indice_refuse():
    notees = {date(2026, 11, 10): 50900.0, date(2026, 11, 11): 50800.0}
    # Valeurs du MASI (cours seuls) importées pour le MASI Rentabilité Net
    assert ecart_import({date(2026, 11, 10): 17400.0}, notees) == (date(2026, 11, 10), 17400.0, 50900.0)
    assert ecart_import({date(2026, 11, 10): 50850.0, date(2026, 1, 5): 47000.0}, notees) is None
    assert ecart_import({date(2025, 1, 5): 47000.0}, notees) is None                # rien à comparer


@pytest.mark.base
def test_import_garde_les_valeurs_notees():
    from fastapi import HTTPException
    from database import db
    from routes.indices import importer
    from schemas import ImportIndiceIn
    jours = [date(1901, 1, 2), date(1901, 1, 3), date(1901, 1, 4)]
    with db() as c:
        c.execute("DELETE FROM indices_historique WHERE indice='MASIMS' AND date = ANY(%s)", (jours,))
        c.execute("INSERT INTO indices_historique (indice, date, valeur, source) VALUES ('MASIMS', %s, 1000, 'auto')", (jours[0],))
    try:
        with pytest.raises(HTTPException):     # 1 500 contre 1 000 noté : un autre indice
            importer("masims", ImportIndiceIn(valeurs=[{"date": jours[0], "valeur": 1500}]))
        r = importer("MASIMS", ImportIndiceIn(valeurs=[{"date": d, "valeur": 1010} for d in jours]))
        assert r["importees"] == 2 and r["deja_notees"] == 1
        with db() as c:
            assert float(c.execute("SELECT valeur FROM indices_historique WHERE indice='MASIMS' AND date=%s",
                                   (jours[0],)).fetchone()["valeur"]) == 1000
    finally:
        with db() as c:
            c.execute("DELETE FROM indices_historique WHERE indice='MASIMS' AND date = ANY(%s)", (jours,))


# ---------------------------------------------------------------------------
# Mode « titres » : achats placés dans l'indice, ventes et dividendes repris
# ---------------------------------------------------------------------------
def test_mode_titres_ventes_et_dividendes_reprennent_des_parts():
    # Achat de 9 600 le 02/02 (0,2 part), dividende de 500 le 01/06 (−0,01), vente créditée 2 600 le 01/09 (−0,05)
    flux = [(date(2026, 2, 2), 9600.0), (date(2026, 6, 1), -500.0), (date(2026, 9, 1), -2600.0)]
    v = portefeuille_virtuel(flux, VALEURS)
    assert v["etat"] == "ok" and abs(v["parts"] - 0.14) < 1e-12
    assert [p["valeur"] for p in v["points"]] == [9600.0, 9500.0, 7280.0, 7131.6]


def test_rendement_vu_du_placement():
    from routes.indices import _rendement
    # 10 000 placés il y a un an, valent 11 000 : +10 % par an
    auj = date(2026, 11, 12)
    assert abs(_rendement([(date(2025, 11, 12), 10000.0)], 11000.0, auj) - 0.10) < 1e-3
    assert _rendement([], 0.0, auj) is None


@pytest.mark.base
def test_les_deux_modes_coexistent():
    from routes import bourse
    from routes.indices import INDICE_DEFAUT, comparer
    compte, titres = comparer(INDICE_DEFAUT, mode="compte"), comparer(INDICE_DEFAUT, mode="titres")
    assert compte["mode"] == "compte" and titres["mode"] == "titres"
    d = bourse.obtenir_dashboard()
    assert compte["toi"]["valeur"] == d.patrimoine_total
    assert titres["toi"]["valeur"] == d.valeur_marche
    for r in (compte, titres):
        if r["etat"] == "ok":
            assert r["ecart"] == round(r["toi"]["valeur"] - r["reference"]["valeur"], 2)
