# -*- coding: utf-8 -*-
"""
Tests du module Budget : cascade de renommage (catégories/sources)
et erreurs 404 sur les suppressions/modifications. Utilise la vraie base
configurée dans .env : chaque test isole ses données sous un préfixe fictif
(ZZTEST) et les supprime avant/après, pour ne jamais toucher aux données réelles.

Lancement :
    cd backend
    pytest tests/test_budget.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

from database import db
from schemas import CategorieIn, SourceIn, DepenseIn, RevenuIn
from config import aujourdhui
from routes.configuration import (
    ajouter_categorie, modifier_categorie, desactiver_categorie,
    ajouter_source, modifier_source, desactiver_source, travail,
)
from routes.transactions import (
    ajouter_depense, modifier_depense, supprimer_depense,
    ajouter_revenu, modifier_revenu, supprimer_revenu, transactions,
)

PREFIXE = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM depenses WHERE categorie LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM revenus WHERE source LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM categories WHERE nom LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM sources_revenus WHERE nom LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    _nettoyer()
    yield
    _nettoyer()


def _id_categorie(nom):
    with db() as c:
        return c.execute("SELECT id FROM categories WHERE nom=%s", (nom,)).fetchone()["id"]


# ---------------------------------------------------------------------------
# Point 6 — renommer une catégorie/source ne doit pas détacher
# les dépenses/revenus déjà saisis sous l'ancien nom.
# ---------------------------------------------------------------------------
def test_renommer_categorie_met_a_jour_les_depenses_existantes():
    ajouter_categorie(CategorieIn(nom=PREFIXE + "Cat", budget=100))
    cid = _id_categorie(PREFIXE + "Cat")
    ajouter_depense(DepenseIn(date="2026-01-15", categorie=PREFIXE + "Cat", montant=50, description=""))

    modifier_categorie(cid, CategorieIn(nom=PREFIXE + "CatRenommee", budget=100))

    with db() as c:
        row = c.execute("SELECT categorie FROM depenses WHERE categorie LIKE %s", (PREFIXE + "%",)).fetchone()
    assert row["categorie"] == PREFIXE + "CatRenommee"


def test_renommer_source_met_a_jour_les_revenus_existants():
    ajouter_source(SourceIn(nom=PREFIXE + "Src"))
    with db() as c:
        sid = c.execute("SELECT id FROM sources_revenus WHERE nom=%s", (PREFIXE + "Src",)).fetchone()["id"]
    ajouter_revenu(RevenuIn(date="2026-01-15", source=PREFIXE + "Src", montant=200))

    modifier_source(sid, SourceIn(nom=PREFIXE + "SrcRenommee"))

    with db() as c:
        row = c.execute("SELECT source FROM revenus WHERE source LIKE %s", (PREFIXE + "%",)).fetchone()
    assert row["source"] == PREFIXE + "SrcRenommee"



# ---------------------------------------------------------------------------
# Prix en heures de travail : seules les sources « revenu du travail » comptent
# ---------------------------------------------------------------------------
def _travail():
    with db() as c:
        return travail(c, aujourdhui())


def _mois_dernier() -> str:
    debut = aujourdhui().replace(day=1)
    return (debut.replace(year=debut.year - 1, month=12) if debut.month == 1 else debut.replace(month=debut.month - 1)).isoformat()


def test_taux_horaire_ignore_les_sources_hors_travail():
    ajouter_source(SourceIn(nom=PREFIXE + "Rembourse", travail=False))
    avant = _travail()
    ajouter_revenu(RevenuIn(date=_mois_dernier(), source=PREFIXE + "Rembourse", montant=10_000_000))
    assert _travail() == avant


def test_taux_horaire_compte_le_revenu_du_travail_du_mois_termine():
    ajouter_source(SourceIn(nom=PREFIXE + "Salaire"))          # revenu du travail par défaut
    avant = _travail()
    ajouter_revenu(RevenuIn(date=_mois_dernier(), source=PREFIXE + "Salaire", montant=10_000_000))
    apres = _travail()
    assert apres["revenu_mensuel"] > avant["revenu_mensuel"]
    assert apres["taux_horaire"] == round(apres["revenu_mensuel"] / apres["heures_mois"], 2)
    # Le mois en cours n'est pas terminé : il ne compte pas
    ajouter_revenu(RevenuIn(date=aujourdhui().isoformat(), source=PREFIXE + "Salaire", montant=10_000_000))
    assert _travail() == apres


def test_modifier_une_source_garde_son_drapeau_travail_si_absent():
    ajouter_source(SourceIn(nom=PREFIXE + "Src", travail=False))
    with db() as c:
        sid = c.execute("SELECT id FROM sources_revenus WHERE nom=%s", (PREFIXE + "Src",)).fetchone()["id"]
    modifier_source(sid, SourceIn(nom=PREFIXE + "Src2"))
    with db() as c:
        assert c.execute("SELECT travail FROM sources_revenus WHERE id=%s", (sid,)).fetchone()["travail"] is False
    modifier_source(sid, SourceIn(nom=PREFIXE + "Src2", travail=True))
    with db() as c:
        assert c.execute("SELECT travail FROM sources_revenus WHERE id=%s", (sid,)).fetchone()["travail"] is True

# ---------------------------------------------------------------------------
# Point 7 — 404 sur les modifications/suppressions inexistantes (comme le
# module Bourse), au lieu de renvoyer {ok: true} silencieusement.
# ---------------------------------------------------------------------------
def test_404_sur_depense_inexistante():
    with pytest.raises(HTTPException) as exc:
        supprimer_depense(9_999_999)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        modifier_depense(9_999_999, DepenseIn(date="2026-01-15", categorie="X", montant=1))
    assert exc.value.status_code == 404


def test_404_sur_revenu_inexistant():
    with pytest.raises(HTTPException) as exc:
        supprimer_revenu(9_999_999)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        modifier_revenu(9_999_999, RevenuIn(date="2026-01-15", source="X", montant=1))
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Modification d'une dépense / d'un revenu déjà saisi (tous les champs, y compris
# la date : la ligne peut changer de mois).
# ---------------------------------------------------------------------------
def test_modifier_depense():
    ajouter_categorie(CategorieIn(nom=PREFIXE + "Cat", budget=0))
    ajouter_categorie(CategorieIn(nom=PREFIXE + "Autre", budget=0))
    did = ajouter_depense(DepenseIn(date="2026-01-15", categorie=PREFIXE + "Cat", montant=50, description="avant"))["id"]

    modifier_depense(did, DepenseIn(date="2026-02-03", categorie=PREFIXE + "Autre", montant=75.5, description=" après "))

    with db() as c:
        row = c.execute("SELECT date,categorie,description,montant FROM depenses WHERE id=%s", (did,)).fetchone()
    assert (row["date"], row["categorie"], row["description"], row["montant"]) == \
           ("2026-02-03", PREFIXE + "Autre", "après", 75.5)


def test_modifier_revenu():
    rid = ajouter_revenu(RevenuIn(date="2026-01-15", source=PREFIXE + "Src", montant=200))["id"]

    modifier_revenu(rid, RevenuIn(date="2026-02-03", source=PREFIXE + "Autre", montant=250, description=" prime "))

    with db() as c:
        row = c.execute("SELECT date,source,description,montant FROM revenus WHERE id=%s", (rid,)).fetchone()
    assert (row["date"], row["source"], row["description"], row["montant"]) ==            ("2026-02-03", PREFIXE + "Autre", "prime", 250)


def test_404_sur_categorie_inexistante():
    with pytest.raises(HTTPException) as exc:
        modifier_categorie(9_999_999, CategorieIn(nom="X", budget=0))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        desactiver_categorie(9_999_999)
    assert exc.value.status_code == 404


def test_404_sur_source_inexistante():
    with pytest.raises(HTTPException) as exc:
        modifier_source(9_999_999, SourceIn(nom="X"))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        desactiver_source(9_999_999)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# B2 — renommer vers un nom déjà pris : 409 lisible au lieu d'une erreur 500
# ---------------------------------------------------------------------------
def test_renommer_categorie_vers_un_nom_existant_renvoie_409():
    ajouter_categorie(CategorieIn(nom=PREFIXE + "A", budget=0))
    ajouter_categorie(CategorieIn(nom=PREFIXE + "B", budget=0))
    with pytest.raises(HTTPException) as exc:
        modifier_categorie(_id_categorie(PREFIXE + "B"), CategorieIn(nom=PREFIXE + "A", budget=0))
    assert exc.value.status_code == 409


def test_renommer_source_vers_un_nom_existant_renvoie_409():
    ajouter_source(SourceIn(nom=PREFIXE + "A"))
    ajouter_source(SourceIn(nom=PREFIXE + "B"))
    with db() as c:
        sid = c.execute("SELECT id FROM sources_revenus WHERE nom=%s", (PREFIXE + "B",)).fetchone()["id"]
    with pytest.raises(HTTPException) as exc:
        modifier_source(sid, SourceIn(nom=PREFIXE + "A"))
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# B3 — une dépense doit porter une catégorie existante et active
# ---------------------------------------------------------------------------
def test_depense_sur_categorie_inconnue_refusee():
    with pytest.raises(HTTPException) as exc:
        ajouter_depense(DepenseIn(date="2026-01-15", categorie=PREFIXE + "Inconnue", montant=10))
    assert exc.value.status_code == 400


def test_depense_sur_categorie_desactivee_refusee_mais_modifiable():
    ajouter_categorie(CategorieIn(nom=PREFIXE + "Cat", budget=0))
    did = ajouter_depense(DepenseIn(date="2026-01-15", categorie=PREFIXE + "Cat", montant=10))["id"]
    desactiver_categorie(_id_categorie(PREFIXE + "Cat"))

    with pytest.raises(HTTPException) as exc:
        ajouter_depense(DepenseIn(date="2026-01-16", categorie=PREFIXE + "Cat", montant=10))
    assert exc.value.status_code == 400
    # Une dépense existante garde sa catégorie, même désactivée depuis
    modifier_depense(did, DepenseIn(date="2026-01-15", categorie=PREFIXE + "Cat", montant=12))


def test_categorie_fixe_enregistree():
    ajouter_categorie(CategorieIn(nom=PREFIXE + "Loyer", budget=3000, fixe=True))
    modifier_categorie(_id_categorie(PREFIXE + "Loyer"), CategorieIn(nom=PREFIXE + "Loyer", budget=3100, fixe=True))
    with db() as c:
        row = c.execute("SELECT budget, fixe FROM categories WHERE nom=%s", (PREFIXE + "Loyer",)).fetchone()
    assert (row["budget"], row["fixe"]) == (3100, True)


# ---------------------------------------------------------------------------
# Tags, suppression annulable, recherche, suggestions
# ---------------------------------------------------------------------------
from routes.transactions import (restaurer_depense, rechercher, analyser_recherche, suggestions,
                                 lister_tags, exporter_csv, importer, transactions)
from routes.configuration import historique_budget, supprimer_budget_mois
from routes.rapports import calculer_resume
from schemas import DepenseRestauree, ImportIn, LigneImport
from datetime import date


def _categorie(nom=PREFIXE + "Cat", budget=0, **kw):
    ajouter_categorie(CategorieIn(nom=nom, budget=budget, **kw))
    return nom


def test_tags_normalises():
    d = DepenseIn(date="2026-01-15", categorie="X", montant=1, tags=["  Voyage   Été ", "#voyage été", "Mariage"])
    assert d.tags == ["voyage été", "mariage"]


def test_suppression_puis_restauration_sous_le_meme_id():
    cat = _categorie()
    did = ajouter_depense(DepenseIn(date="2026-01-15", categorie=cat, montant=42, tags=["zztest"]))["id"]
    supprimee = supprimer_depense(did)
    # La catégorie est désactivée entre-temps : la restauration doit quand même passer
    desactiver_categorie(_id_categorie(cat))
    restaurer_depense(DepenseRestauree(**{**supprimee, "date": supprimee["date"]}))
    lignes = transactions("2026-01")["depenses"]
    assert any(l["id"] == did and l["montant"] == 42 and l["tags"] == ["zztest"] for l in lignes)


def test_analyse_de_la_recherche():
    assert analyser_recherche("#Voyage resto 250,5") == (["voyage"], "resto", 250.5)


def test_recherche_par_texte_tag_et_montant():
    cat = _categorie()
    ajouter_depense(DepenseIn(date="2025-03-02", categorie=cat, montant=250, description="zztest resto", tags=["zztest-voyage"]))
    ajouter_depense(DepenseIn(date="2026-01-15", categorie=cat, montant=80, description="zztest taxi", tags=["zztest-voyage"]))
    ajouter_revenu(RevenuIn(date="2026-01-20", source=PREFIXE + "Src", montant=100, tags=["zztest-voyage"]))

    r = rechercher("#zztest-voyage")
    assert (r["nb"], r["total_depenses"], r["total_revenus"]) == (3, 330, 100)
    assert r["resultats"][0]["date"] == "2026-01-20"            # du plus récent au plus ancien
    assert rechercher("zztest resto")["nb"] == 1
    assert rechercher("#zztest-voyage 80")["resultats"][0]["description"] == "zztest taxi"
    assert rechercher("")["nb"] == 0


def test_suggestions_par_categorie():
    cat = _categorie()
    for jour, desc, m in [("01", "Marjane", 300), ("05", "Épicerie", 40), ("09", "Marjane", 320)]:
        ajouter_depense(DepenseIn(date=f"2026-01-{jour}", categorie=cat, montant=m, description=desc))
    s = suggestions("depenses", cat)
    assert [x["description"] for x in s] == ["Marjane", "Épicerie"]
    assert s[0]["montant"] == 320                                 # dernier montant saisi


def test_liste_des_tags_avec_totaux():
    cat = _categorie()
    ajouter_depense(DepenseIn(date="2026-01-15", categorie=cat, montant=50, tags=["zztest-mariage"]))
    ajouter_depense(DepenseIn(date="2026-02-15", categorie=cat, montant=70, tags=["zztest-mariage"]))
    t = next(x for x in lister_tags() if x["tag"] == "zztest-mariage")
    assert (t["nb"], t["depenses"], t["premier"], t["dernier"]) == (2, 120, "2026-01-15", "2026-02-15")


# ---------------------------------------------------------------------------
# Export / import CSV
# ---------------------------------------------------------------------------
def test_export_csv():
    cat = _categorie()
    ajouter_depense(DepenseIn(date="1901-01-15", categorie=cat, montant=12.5, description='dit "bonjour"', tags=["a", "b"]))
    texte = exporter_csv("1901-01-01", "1901-12-31").body.decode("utf-8")
    assert texte.startswith("﻿type;date;")
    assert f'depense;1901-01-15;{cat};"dit ""bonjour""";12,50;a, b' in texte


def test_import_simulation_doublons_et_erreurs():
    cat = _categorie()
    ajouter_depense(DepenseIn(date="1901-01-15", categorie=cat, montant=12.5, description="Café"))
    lignes = [
        LigneImport(type="depense", date="1901-01-15", nom=cat, description="café ", montant=12.5),    # doublon
        LigneImport(type="depense", date="1901-01-16", nom=cat, description="Pain", montant=3),        # nouvelle
        LigneImport(type="depense", date="1901-01-16", nom=PREFIXE + "Inconnue", montant=3),           # erreur
        LigneImport(type="revenu", date="1901-01-31", nom=PREFIXE + "Src", montant=900),               # nouvelle
    ]
    apercu = importer(ImportIn(lignes=lignes, simulation=True))
    assert [s["statut"] for s in apercu["statuts"]] == ["doublon", "ajoutee", "erreur", "ajoutee"]
    assert transactions("1901-01")["revenus"] == []               # rien d'enregistré en simulation

    r = importer(ImportIn(lignes=lignes))
    assert (r["nb_ajoutees"], r["nb_doublons"], r["nb_erreurs"]) == (2, 1, 1)
    t = transactions("1901-01")
    assert len(t["depenses"]) == 2 and len(t["revenus"]) == 1
    # Réimporter le même fichier n'ajoute plus rien
    assert importer(ImportIn(lignes=lignes))["nb_ajoutees"] == 0


# ---------------------------------------------------------------------------
# Budgets par mois
# ---------------------------------------------------------------------------
def test_changer_un_budget_ne_reecrit_pas_les_mois_passes():
    cat = _categorie(budget=100, a_partir_de="1900-01")
    cid = _id_categorie(cat)
    modifier_categorie(cid, CategorieIn(nom=cat, budget=300, a_partir_de="1901-06"))

    def budget(mois):
        return next(b["budget"] for b in calculer_resume(mois, date(1902, 1, 1))["budget_vs_reel"] if b["cat"] == cat)
    assert budget("1901-05") == 100
    assert budget("1901-06") == 300
    assert [h["mois_debut"] for h in historique_budget(cid)] == ["1901-06", "1900-01"]

    supprimer_budget_mois(cid, "1901-06")
    assert budget("1901-06") == 100
    with pytest.raises(HTTPException):
        supprimer_budget_mois(cid, "1900-01")                    # le seul budget restant


def test_categorie_desactivee_garde_son_budget_dans_les_mois_passes():
    cat = _categorie(budget=100, a_partir_de="1900-01")
    desactiver_categorie(_id_categorie(cat))
    passe = calculer_resume("1901-05", date(1902, 1, 1))["budget_vs_reel"]
    assert any(b["cat"] == cat and b["budget"] == 100 for b in passe)
    courant = calculer_resume(date.today().strftime("%Y-%m"), date.today())["budget_vs_reel"]
    assert not any(b["cat"] == cat for b in courant)


def test_nouvelle_categorie_sans_budget_dans_le_passe():
    cat = _categorie(budget=100)                                  # à partir du mois en cours
    assert not any(b["cat"] == cat for b in calculer_resume("1901-05", date(1902, 1, 1))["budget_vs_reel"])


# ---------------------------------------------------------------------------
# Clés étrangères (database.CLES_ETRANGERES)
# ---------------------------------------------------------------------------
def test_une_source_libre_devient_une_source_retiree():
    """« Autre… » dans le formulaire : la source est créée retirée (hors listes et hors taux
    horaire), pour respecter la clé étrangère des revenus."""
    ajouter_revenu(RevenuIn(date="2026-01-15", source=PREFIXE + "Libre", montant=10))
    with db() as c:
        s = c.execute("SELECT actif, travail FROM sources_revenus WHERE nom=%s", (PREFIXE + "Libre",)).fetchone()
    assert s["actif"] == 0 and s["travail"] is False


def test_un_revenu_sans_source_est_enregistre_sans_source():
    rid = ajouter_revenu(RevenuIn(date="1901-01-15", source="  ", description=PREFIXE, montant=10))["id"]
    try:
        with db() as c:
            assert c.execute("SELECT source FROM revenus WHERE id=%s", (rid,)).fetchone()["source"] is None
        lignes = transactions("1901-01")["revenus"]
        assert [r["source"] for r in lignes if r["id"] == rid] == [""]   # l'API renvoie toujours un texte
    finally:
        with db() as c:
            c.execute("DELETE FROM revenus WHERE id=%s", (rid,))


def test_la_base_refuse_une_depense_sans_categorie_existante():
    """Même en écrivant directement en base (hors de l'application)."""
    from psycopg.errors import ForeignKeyViolation
    with pytest.raises(ForeignKeyViolation):
        with db() as c:
            c.execute("INSERT INTO depenses(date, categorie, montant) VALUES('2026-01-15', %s, 1)", (PREFIXE + "Fantome",))
