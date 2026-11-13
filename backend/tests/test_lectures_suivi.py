# -*- coding: utf-8 -*-
"""
Tests du suivi de lecture : rythme et fin estimée, série de jours, page du jour, note du
jour, export Markdown, livres prêtés. Utilise la base configurée dans .env (préfixe ZZTEST) ;
la table des jours de lecture est sauvegardée puis restaurée.

Lancement :
    cd backend
    pytest tests/test_lectures_suivi.py -v
"""
import io
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

# Chaque test passe par la base (nettoyage automatique avant chaque test)
pytestmark = pytest.mark.base
from fastapi import HTTPException
from pydantic import ValidationError

from config import aujourdhui
from database import db
from schemas import ALireIn, LivreIn, NoteIn, PretLivreIn, ProgressionIn
from routes.lectures import (
    ajouter_a_lire, ajouter_livre, ajouter_note, ajouter_pret, calculer_serie, exporter_notes,
    exporter_toutes_les_notes, lister_a_lire, lister_prets, modifier_pret, nom_fichier, note_du_jour,
    noter_progression, notes_en_markdown, obtenir_serie, rythme, supprimer_pret, terminer_a_lire,
)

PREFIXE = "ZZTEST"


def _nettoyer():
    with db() as c:
        c.execute("DELETE FROM lectures_livres WHERE titre LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM lectures_a_lire WHERE titre LIKE %s", (PREFIXE + "%",))
        c.execute("DELETE FROM lectures_prets WHERE titre LIKE %s", (PREFIXE + "%",))


@pytest.fixture(autouse=True)
def isolation():
    with db() as c:
        jours = [r["date"] for r in c.execute("SELECT date FROM lectures_jours").fetchall()]
        c.execute("DELETE FROM lectures_jours")
    _nettoyer()
    yield
    _nettoyer()
    with db() as c:
        c.execute("DELETE FROM lectures_jours")
        for j in jours:
            c.execute("INSERT INTO lectures_jours(date) VALUES(%s)", (j,))


# ---------------------------------------------------------------- rythme
def test_rythme_depuis_le_debut_de_la_lecture():
    livre = {"date_debut": date(2026, 10, 1), "pages": 300}
    r = rythme(livre, [(date(2026, 10, 5), 60), (date(2026, 10, 11), 150)], date(2026, 10, 11))
    assert r["page_actuelle"] == 150 and r["pages_par_jour"] == 15      # 150 pages en 10 jours
    assert r["fin_estimee"] == date(2026, 10, 21)                       # 150 pages restantes à 15 par jour


def test_rythme_sans_date_de_debut_ni_nombre_de_pages():
    r = rythme({"date_debut": None, "pages": None}, [(date(2026, 10, 1), 40), (date(2026, 10, 5), 120)], date(2026, 10, 6))
    assert r["pages_par_jour"] == 20 and r["fin_estimee"] is None       # 80 pages en 4 jours ; fin inconnue


def test_rythme_sans_page_notee_ou_livre_fini():
    vide = rythme({"date_debut": date(2026, 10, 1), "pages": 300}, [], date(2026, 10, 2))
    assert vide == {"page_actuelle": None, "derniere_lecture": None, "pages_par_jour": None, "fin_estimee": None}
    fini = rythme({"date_debut": date(2026, 10, 1), "pages": 100}, [(date(2026, 10, 3), 100)], date(2026, 10, 3))
    assert fini["fin_estimee"] is None


def test_pas_de_rythme_sur_un_seul_jour():
    # Commencé (ou première page notée) le jour même : 92 pages en « un jour » serait faux
    r = rythme({"date_debut": date(2026, 10, 10), "pages": 133}, [(date(2026, 10, 10), 92)], date(2026, 10, 10))
    assert r["page_actuelle"] == 92 and r["pages_par_jour"] is None and r["fin_estimee"] is None


# ---------------------------------------------------------------- série
def test_serie_de_jours_consecutifs():
    j = lambda n: date(2026, 10, n)
    assert calculer_serie({j(8), j(9), j(10)}, j(10)) == {"serie": 3, "record": 3, "lu_aujourdhui": True}
    # Pas encore lu aujourd'hui : la série d'hier tient toujours
    assert calculer_serie({j(8), j(9)}, j(10)) == {"serie": 2, "record": 2, "lu_aujourdhui": False}
    # Un jour sauté : la série repart de zéro, le record reste
    assert calculer_serie({j(1), j(2), j(3), j(4), j(8)}, j(10)) == {"serie": 0, "record": 4, "lu_aujourdhui": False}
    assert calculer_serie(set(), j(10)) == {"serie": 0, "record": 0, "lu_aujourdhui": False}


# ---------------------------------------------------------------- page du jour
def test_noter_sa_page_demarre_le_livre_et_compte_un_jour_de_lecture():
    a = ajouter_a_lire(ALireIn(titre=f"{PREFIXE} Livre", pages=200))
    assert a["date_debut"] is None and a["page_actuelle"] is None
    a = noter_progression(a["id"], ProgressionIn(page=30))
    assert a["date_debut"] == aujourdhui() and a["page_actuelle"] == 30 and a["derniere_lecture"] == aujourdhui()
    assert obtenir_serie()["serie"] == 1 and obtenir_serie()["lu_aujourdhui"]
    # Une seconde saisie le même jour remplace la première
    assert noter_progression(a["id"], ProgressionIn(page=45))["page_actuelle"] == 45
    assert next(x for x in lister_a_lire() if x["id"] == a["id"])["page_actuelle"] == 45


def test_page_au_dela_du_livre_refusee():
    a = ajouter_a_lire(ALireIn(titre=f"{PREFIXE} Court", pages=100))
    with pytest.raises(HTTPException) as exc:
        noter_progression(a["id"], ProgressionIn(page=101))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        noter_progression(999999999, ProgressionIn(page=1))
    assert exc.value.status_code == 404


def test_la_serie_survit_au_livre_termine():
    a = ajouter_a_lire(ALireIn(titre=f"{PREFIXE} Fini", pages=50))
    noter_progression(a["id"], ProgressionIn(page=50))
    terminer_a_lire(a["id"], LivreIn(titre=f"{PREFIXE} Fini", date_fin=aujourdhui()))
    assert obtenir_serie()["serie"] == 1


# ---------------------------------------------------------------- note du jour
def test_note_du_jour_stable_dans_la_journee_et_defilable():
    livre = ajouter_livre(LivreIn(titre=f"{PREFIXE} Citations", auteur="Auteur", date_fin=date(1901, 1, 1)))
    for i in range(3):
        ajouter_note(NoteIn(livre_id=livre["id"], type="citation", texte=f"{PREFIXE} phrase {i}", page=i + 1))
    jour = date(2026, 10, 10)
    premiere = note_du_jour(jour)
    assert premiere == note_du_jour(jour) and premiere["titre"] and premiere["texte"]
    assert note_du_jour(jour, 1)["id"] != premiere["id"]


# ---------------------------------------------------------------- export Markdown
def test_fiche_markdown():
    md = notes_en_markdown(
        {"titre": "Sapiens", "auteur": "Harari", "date_fin": date(2026, 3, 12), "note": 4, "commentaire": "Très bon."},
        [{"type": "citation", "texte": "Ligne 1\nLigne 2", "page": 12}, {"type": "note", "texte": "Une idée", "page": None}])
    assert md.startswith("# Sapiens\n\n*Harari* · terminé le 12 mars 2026 · ★★★★☆\n")
    assert "## Mon avis\n\nTrès bon.\n" in md
    assert "> Ligne 1\n> Ligne 2 — p. 12\n" in md and "## Notes\n\n- Une idée\n" in md


def test_nom_de_fichier():
    assert nom_fichier("L'Étranger : récit", "x") == "l-etranger-recit.md"
    assert nom_fichier("سيكلوجية الجنس", "livre-3") == "سيكلوجية الجنس.md"     # titre non latin conservé
    assert nom_fichier("???", "livre-3") == "livre-3.md"
    assert "/" not in nom_fichier("../../etc/passwd", "x")


def test_export_d_un_livre_et_de_tous_les_livres():
    livre = ajouter_livre(LivreIn(titre=f"{PREFIXE} Export", date_fin=date(1901, 1, 1)))
    ajouter_note(NoteIn(livre_id=livre["id"], texte="À retenir"))
    en_cours = ajouter_a_lire(ALireIn(titre=f"{PREFIXE} En cours"))
    ajouter_note(NoteIn(a_lire_id=en_cours["id"], type="citation", texte="Une phrase"))
    reponse = exporter_notes(livre_id=livre["id"])
    assert "- À retenir" in reponse.body.decode() and "zztest-export.md" in reponse.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(exporter_toutes_les_notes().body)) as archive:
        assert {"zztest-export.md", "zztest-en-cours.md"} <= set(archive.namelist())
        assert "> Une phrase" in archive.read("zztest-en-cours.md").decode()
    with pytest.raises(HTTPException) as exc:
        exporter_notes(livre_id=999999999)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------- livres prêtés
def test_livres_pretes_puis_rendus():
    auj = aujourdhui()
    ancien = ajouter_pret(PretLivreIn(titre=f"{PREFIXE} A", personne="Sara", date_pret=auj - timedelta(days=40)))
    recent = ajouter_pret(PretLivreIn(titre=f"{PREFIXE} B", personne="Omar", date_pret=auj - timedelta(days=3)))
    assert ancien["jours"] == 40 and ancien["date_retour"] is None
    rendu = modifier_pret(ancien["id"], PretLivreIn(titre=f"{PREFIXE} A", personne="Sara", date_pret=auj - timedelta(days=40),
                                                    date_retour=auj - timedelta(days=10)))
    assert rendu["jours"] == 30                                   # durée du prêt, arrêtée au retour
    ordre = [p["id"] for p in lister_prets() if p["titre"].startswith(PREFIXE)]
    assert ordre == [recent["id"], ancien["id"]]                  # encore prêtés d'abord
    supprimer_pret(recent["id"])
    with pytest.raises(HTTPException) as exc:
        supprimer_pret(recent["id"])
    assert exc.value.status_code == 404


def test_validation_d_un_pret():
    with pytest.raises(ValidationError):
        PretLivreIn(titre="Livre", personne="  ", date_pret=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        PretLivreIn(titre="Livre", personne="Sara", date_pret=date(2026, 1, 2), date_retour=date(2026, 1, 1))
