# -*- coding: utf-8 -*-
"""
Module Lectures — journal des livres terminés et bilan annuel.

Un livre compte pour l'année et le mois de sa date de FIN de lecture. Une
relecture est une nouvelle ligne : elle compte comme un livre lu de plus.

Objectifs (nombre de livres) : un objectif annuel et un objectif mensuel,
stockés dans la table `params` comme l'objectif d'épargne du Budget.
"""
import json
import re
import urllib.error
import urllib.request
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from config import aujourdhui
from database import db
from securite import utilisateur_courant
from schemas import (ALireIn, ALireOut, FicheIsbn, GenreOut, LivreIn, LivreOut, NomIn, NoteIn, NoteOut,
                     ObjectifsLecture)

router = APIRouter(prefix="/api/lectures", tags=["lectures"],
                   dependencies=[Depends(utilisateur_courant)])

LIVRE_COLONNES = "id, titre, auteur, genre, date_debut, date_fin, pages, note, commentaire, isbn, couverture"
# Liste des livres avec leur nombre de notes / citations
LIVRES_AVEC_NOTES = f"""SELECT {LIVRE_COLONNES},
    (SELECT COUNT(*) FROM lectures_notes n WHERE n.livre_id = l.id)::int nb_notes FROM lectures_livres l"""
A_LIRE_COLONNES = "id, titre, auteur, genre, pages, isbn, couverture, commentaire, date_debut"


def _valeurs(l: LivreIn) -> tuple:
    return (l.titre.strip(), l.auteur.strip(), l.genre.strip(), l.date_debut, l.date_fin,
            l.pages, l.note, l.commentaire.strip(), _isbn_normalise(l.isbn), l.couverture.strip())


def _livre(c, livre_id: int):
    return c.execute(LIVRES_AVEC_NOTES + " WHERE id=%s", (livre_id,)).fetchone()


def _isbn_normalise(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def _clause_annee(annee: Optional[int]) -> tuple:
    if annee is None:
        return "", ()
    return " WHERE date_fin >= %s AND date_fin < %s", (date(annee, 1, 1), date(annee + 1, 1, 1))


# ---------------------------------------------------------------- livres
@router.get("/livres", response_model=List[LivreOut])
def lister_livres(annee: Optional[int] = None):
    clause, params = _clause_annee(annee)
    with db() as c:
        return c.execute(f"{LIVRES_AVEC_NOTES}{clause} ORDER BY date_fin DESC, id DESC", params).fetchall()


def _inserer_livre(c, l: LivreIn) -> dict:
    row = c.execute(
        """INSERT INTO lectures_livres (titre, auteur, genre, date_debut, date_fin, pages, note, commentaire, isbn, couverture)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", _valeurs(l)).fetchone()
    return row


@router.post("/livres", response_model=LivreOut, status_code=201)
def ajouter_livre(l: LivreIn):
    with db() as c:
        return _livre(c, _inserer_livre(c, l)["id"])


@router.put("/livres/{livre_id}", response_model=LivreOut)
def modifier_livre(livre_id: int, l: LivreIn):
    with db() as c:
        res = c.execute(
            """UPDATE lectures_livres SET titre=%s, auteur=%s, genre=%s, date_debut=%s, date_fin=%s,
                      pages=%s, note=%s, commentaire=%s, isbn=%s, couverture=%s
               WHERE id=%s""", (*_valeurs(l), livre_id))
        if res.rowcount == 0:
            raise HTTPException(404, "Livre introuvable")
        return _livre(c, livre_id)


@router.delete("/livres/{livre_id}", status_code=204)
def supprimer_livre(livre_id: int):
    with db() as c:
        if c.execute("DELETE FROM lectures_livres WHERE id=%s", (livre_id,)).rowcount == 0:
            raise HTTPException(404, "Livre introuvable")


# ---------------------------------------------------------------- à lire / en cours
def _valeurs_a_lire(a: ALireIn) -> tuple:
    return (a.titre.strip(), a.auteur.strip(), a.genre.strip(), a.pages, _isbn_normalise(a.isbn),
            a.couverture.strip(), a.commentaire.strip(), a.date_debut)


def _a_lire(c, a_lire_id: int):
    return c.execute(f"""SELECT {A_LIRE_COLONNES},
                         (SELECT COUNT(*) FROM lectures_notes n WHERE n.a_lire_id = a.id)::int nb_notes
                         FROM lectures_a_lire a WHERE id=%s""", (a_lire_id,)).fetchone()


@router.get("/a_lire", response_model=List[ALireOut])
def lister_a_lire():
    """Livres en cours d'abord (du plus récemment commencé), puis la liste à lire (ordre d'ajout)."""
    with db() as c:
        return c.execute(f"""SELECT {A_LIRE_COLONNES},
                             (SELECT COUNT(*) FROM lectures_notes n WHERE n.a_lire_id = a.id)::int nb_notes
                             FROM lectures_a_lire a
                             ORDER BY date_debut IS NULL, date_debut DESC, id""").fetchall()


@router.post("/a_lire", response_model=ALireOut, status_code=201)
def ajouter_a_lire(a: ALireIn):
    with db() as c:
        row = c.execute("""INSERT INTO lectures_a_lire (titre, auteur, genre, pages, isbn, couverture, commentaire, date_debut)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", _valeurs_a_lire(a)).fetchone()
        return _a_lire(c, row["id"])


@router.put("/a_lire/{a_lire_id}", response_model=ALireOut)
def modifier_a_lire(a_lire_id: int, a: ALireIn):
    with db() as c:
        if c.execute("""UPDATE lectures_a_lire SET titre=%s, auteur=%s, genre=%s, pages=%s, isbn=%s, couverture=%s,
                               commentaire=%s, date_debut=%s WHERE id=%s""",
                     (*_valeurs_a_lire(a), a_lire_id)).rowcount == 0:
            raise HTTPException(404, "Livre introuvable")
        return _a_lire(c, a_lire_id)


@router.delete("/a_lire/{a_lire_id}", status_code=204)
def supprimer_a_lire(a_lire_id: int):
    with db() as c:
        if c.execute("DELETE FROM lectures_a_lire WHERE id=%s", (a_lire_id,)).rowcount == 0:
            raise HTTPException(404, "Livre introuvable")


@router.post("/a_lire/{a_lire_id}/terminer", response_model=LivreOut, status_code=201)
def terminer_a_lire(a_lire_id: int, l: LivreIn):
    """Le livre passe dans le journal des livres lus, avec ses notes et citations."""
    with db() as c:
        if not c.execute("SELECT 1 FROM lectures_a_lire WHERE id=%s", (a_lire_id,)).fetchone():
            raise HTTPException(404, "Livre introuvable")
        livre_id = _inserer_livre(c, l)["id"]
        c.execute("UPDATE lectures_notes SET livre_id=%s, a_lire_id=NULL WHERE a_lire_id=%s", (livre_id, a_lire_id))
        c.execute("DELETE FROM lectures_a_lire WHERE id=%s", (a_lire_id,))
        return _livre(c, livre_id)


# ---------------------------------------------------------------- notes et citations
NOTE_COLONNES = "id, livre_id, a_lire_id, type, texte, page"


@router.get("/notes", response_model=List[NoteOut])
def lister_notes(livre_id: Optional[int] = None, a_lire_id: Optional[int] = None):
    """Notes d'un livre, dans l'ordre des pages puis de saisie."""
    if (livre_id is None) == (a_lire_id is None):
        raise HTTPException(400, "Indique soit livre_id, soit a_lire_id")
    colonne, valeur = ("livre_id", livre_id) if livre_id is not None else ("a_lire_id", a_lire_id)
    with db() as c:
        return c.execute(f"SELECT {NOTE_COLONNES} FROM lectures_notes WHERE {colonne}=%s "
                         "ORDER BY page NULLS LAST, id", (valeur,)).fetchall()


@router.post("/notes", response_model=NoteOut, status_code=201)
def ajouter_note(n: NoteIn):
    with db() as c:
        table, ident = ("lectures_livres", n.livre_id) if n.livre_id is not None else ("lectures_a_lire", n.a_lire_id)
        if not c.execute(f"SELECT 1 FROM {table} WHERE id=%s", (ident,)).fetchone():
            raise HTTPException(404, "Livre introuvable")
        return c.execute(f"""INSERT INTO lectures_notes (livre_id, a_lire_id, type, texte, page)
                             VALUES (%s,%s,%s,%s,%s) RETURNING {NOTE_COLONNES}""",
                         (n.livre_id, n.a_lire_id, n.type, n.texte.strip(), n.page)).fetchone()


@router.put("/notes/{note_id}", response_model=NoteOut)
def modifier_note(note_id: int, n: NoteIn):
    """Modifie le texte, le type et la page (le livre de rattachement ne change pas)."""
    with db() as c:
        row = c.execute(f"UPDATE lectures_notes SET type=%s, texte=%s, page=%s WHERE id=%s RETURNING {NOTE_COLONNES}",
                        (n.type, n.texte.strip(), n.page, note_id)).fetchone()
    if not row:
        raise HTTPException(404, "Note introuvable")
    return row


@router.delete("/notes/{note_id}", status_code=204)
def supprimer_note(note_id: int):
    with db() as c:
        if c.execute("DELETE FROM lectures_notes WHERE id=%s", (note_id,)).rowcount == 0:
            raise HTTPException(404, "Note introuvable")


# ---------------------------------------------------------------- recherche par ISBN (Open Library)
URL_OPEN_LIBRARY = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"


def valider_isbn(isbn: str) -> str:
    """ISBN-10 ou ISBN-13 sans tirets ni espaces, clé de contrôle vérifiée ; HTTPException 400 sinon."""
    v = _isbn_normalise(isbn)
    if len(v) == 13 and v.isdigit():
        ok = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(v)) % 10 == 0
    elif len(v) == 10 and v[:9].isdigit() and (v[9].isdigit() or v[9] == "X"):
        ok = sum((10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(v)) % 11 == 0
    else:
        ok = False
    if not ok:
        raise HTTPException(400, "ISBN invalide (10 ou 13 chiffres, clé de contrôle comprise)")
    return v


def lire_fiche_open_library(reponse: dict, isbn: str) -> Optional[dict]:
    """Réponse JSON d'Open Library → fiche du livre, ou None si l'ISBN est inconnu."""
    fiche = reponse.get(f"ISBN:{isbn}")
    if not fiche:
        return None
    auteurs = [a.get("name", "") for a in fiche.get("authors", []) if a.get("name")]
    titre = fiche.get("title", "")
    if fiche.get("subtitle"):
        titre += " : " + fiche["subtitle"]
    pages = fiche.get("number_of_pages")
    couverture = fiche.get("cover", {})
    return {"isbn": isbn, "titre": titre[:200], "auteur": ", ".join(auteurs)[:150],
            "pages": pages if isinstance(pages, int) and pages > 0 else None,
            # À défaut, l'image par ISBN (404 s'il n'y en a pas : le frontend masque alors l'image)
            "couverture": couverture.get("medium") or couverture.get("large") or couverture.get("small")
                          or f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"}


@router.get("/isbn/{isbn}", response_model=FicheIsbn)
def chercher_isbn(isbn: str):
    """Titre, auteur(s), pages et couverture d'après Open Library (appel fait par le serveur)."""
    v = valider_isbn(isbn)
    requete = urllib.request.Request(URL_OPEN_LIBRARY.format(isbn=v), headers={"User-Agent": "MonBudget/2.2"})
    try:
        with urllib.request.urlopen(requete, timeout=8) as r:
            reponse = json.load(r)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"[isbn] Open Library injoignable — {e}", flush=True)
        raise HTTPException(502, "Open Library est injoignable pour le moment : saisis le livre à la main")
    fiche = lire_fiche_open_library(reponse, v)
    if not fiche:
        raise HTTPException(404, "ISBN inconnu d'Open Library : saisis le livre à la main")
    return fiche


@router.get("/auteurs", response_model=List[str])
def lister_auteurs():
    """Auteurs déjà saisis, pour l'autocomplétion du formulaire."""
    with db() as c:
        rows = c.execute("SELECT DISTINCT auteur FROM lectures_livres WHERE auteur <> '' ORDER BY auteur").fetchall()
    return [r["auteur"] for r in rows]


# ---------------------------------------------------------------- genres
@router.get("/genres", response_model=List[GenreOut])
def lister_genres():
    with db() as c:
        return c.execute("SELECT id, nom FROM lectures_genres WHERE actif=1 ORDER BY nom").fetchall()


@router.post("/genres", status_code=201)
def ajouter_genre(g: NomIn):
    with db() as c:
        c.execute("""INSERT INTO lectures_genres(nom) VALUES(%s)
                     ON CONFLICT (nom) DO UPDATE SET actif=1""", (g.nom.strip(),))
    return {"ok": True}


@router.put("/genres/{genre_id}")
def modifier_genre(genre_id: int, g: NomIn):
    nouveau_nom = g.nom.strip()
    try:
        with db() as c:
            ancien = c.execute("SELECT nom FROM lectures_genres WHERE id=%s", (genre_id,)).fetchone()
            if not ancien:
                raise HTTPException(404, "Genre introuvable")
            c.execute("UPDATE lectures_genres SET nom=%s WHERE id=%s", (nouveau_nom, genre_id))
            if nouveau_nom != ancien["nom"]:
                # Le genre est stocké par son nom : les livres déjà saisis suivent le renommage
                c.execute("UPDATE lectures_livres SET genre=%s WHERE genre=%s", (nouveau_nom, ancien["nom"]))
    except UniqueViolation:
        raise HTTPException(409, f"Le genre « {nouveau_nom} » existe déjà")
    return {"ok": True}


@router.delete("/genres/{genre_id}")
def desactiver_genre(genre_id: int):
    with db() as c:
        if c.execute("UPDATE lectures_genres SET actif=0 WHERE id=%s", (genre_id,)).rowcount == 0:
            raise HTTPException(404, "Genre introuvable")
    return {"ok": True}


# ---------------------------------------------------------------- objectifs
def _objectifs(c) -> dict:
    rows = c.execute("SELECT cle, valeur FROM params WHERE cle IN "
                     "('objectif_lecture_annuel', 'objectif_lecture_mensuel')").fetchall()
    v = {r["cle"]: int(r["valeur"]) for r in rows}
    return {"annuel": v.get("objectif_lecture_annuel", 0), "mensuel": v.get("objectif_lecture_mensuel", 0)}


@router.get("/objectifs", response_model=ObjectifsLecture)
def obtenir_objectifs():
    with db() as c:
        return _objectifs(c)


@router.put("/objectifs", response_model=ObjectifsLecture)
def modifier_objectifs(o: ObjectifsLecture):
    with db() as c:
        c.execute("""INSERT INTO params(cle,valeur) VALUES('objectif_lecture_annuel',%s),('objectif_lecture_mensuel',%s)
                     ON CONFLICT (cle) DO UPDATE SET valeur=EXCLUDED.valeur""", (o.annuel, o.mensuel))
        return _objectifs(c)


# ---------------------------------------------------------------- bilan annuel
def _avancement(annee: int, aujourdhui: date) -> tuple:
    """(part de l'année écoulée entre 0 et 1, nombre de mois entamés) pour `annee`."""
    if annee < aujourdhui.year:
        return 1.0, 12
    if annee > aujourdhui.year:
        return 0.0, 0
    debut = date(annee, 1, 1)
    nb_jours = (date(annee + 1, 1, 1) - debut).days
    return ((aujourdhui - debut).days + 1) / nb_jours, aujourdhui.month


@router.get("/bilan")
def bilan(annee: int):
    """Résumé d'une année de lecture."""
    return calculer_bilan(annee, aujourdhui())


def calculer_bilan(annee: int, aujourdhui: date) -> dict:
    """`aujourdhui` est passé en paramètre pour que les tests fixent la date de référence."""
    clause, params = _clause_annee(annee)
    with db() as c:
        livres = c.execute(f"SELECT {LIVRE_COLONNES} FROM lectures_livres{clause} "
                           "ORDER BY date_fin DESC, id DESC", params).fetchall()
        nb_prec = c.execute("SELECT COUNT(*) n FROM lectures_livres WHERE date_fin >= %s AND date_fin < %s",
                            (date(annee - 1, 1, 1), date(annee, 1, 1))).fetchone()["n"]
        historique = c.execute("""SELECT EXTRACT(YEAR FROM date_fin)::int annee, COUNT(*) livres,
                                         COALESCE(SUM(pages),0)::int pages
                                  FROM lectures_livres GROUP BY 1 ORDER BY 1""").fetchall()
        obj = _objectifs(c)

    avec_pages = [l for l in livres if l["pages"]]
    avec_note = [l for l in livres if l["note"]]
    avec_duree = [l for l in livres if l["date_debut"]]
    nb_pages = sum(l["pages"] for l in avec_pages)

    par_mois = [{"m": m, "livres": 0, "pages": 0} for m in range(1, 13)]
    genres, auteurs = {}, {}
    for l in livres:
        mois = par_mois[l["date_fin"].month - 1]
        mois["livres"] += 1
        mois["pages"] += l["pages"] or 0
        g = genres.setdefault(l["genre"] or "Non classé", {"livres": 0, "pages": 0})
        g["livres"] += 1
        g["pages"] += l["pages"] or 0
        if l["auteur"]:
            auteurs[l["auteur"]] = auteurs.get(l["auteur"], 0) + 1

    part_ecoulee, nb_mois_ecoules = _avancement(annee, aujourdhui)
    est_courante = annee == aujourdhui.year
    nb_mois_objectif = (sum(1 for x in par_mois[:nb_mois_ecoules] if x["livres"] >= obj["mensuel"])
                        if obj["mensuel"] > 0 else 0)

    return {
        "annee": annee,
        "est_annee_courante": est_courante,
        "nb_livres": len(livres),
        "nb_pages": nb_pages,
        "pages_moyennes": round(nb_pages / len(avec_pages)) if avec_pages else 0,
        "note_moyenne": round(sum(l["note"] for l in avec_note) / len(avec_note), 2) if avec_note else None,
        "duree_moyenne_jours": round(sum((l["date_fin"] - l["date_debut"]).days + 1 for l in avec_duree)
                                     / len(avec_duree), 1) if avec_duree else None,
        "nb_livres_annee_precedente": nb_prec,
        "objectif_annuel": obj["annuel"],
        "objectif_mensuel": obj["mensuel"],
        # Livres qu'il faudrait avoir lus à ce jour pour tenir l'objectif annuel au rythme régulier
        "attendu_a_date": round(obj["annuel"] * part_ecoulee, 1),
        "nb_mois_ecoules": nb_mois_ecoules,
        "nb_mois_objectif": nb_mois_objectif,
        "livres_mois_courant": par_mois[aujourdhui.month - 1]["livres"] if est_courante else None,
        "par_mois": par_mois,
        "genres": sorted(({"genre": k, **v} for k, v in genres.items()), key=lambda x: -x["livres"]),
        "auteurs": sorted(({"auteur": k, "livres": v} for k, v in auteurs.items()),
                          key=lambda x: (-x["livres"], x["auteur"]))[:5],
        # À égalité, le plus récent (les livres sont triés du plus récent au plus ancien)
        "mieux_note": max(avec_note, key=lambda l: l["note"]) if avec_note else None,
        "plus_long": max(avec_pages, key=lambda l: l["pages"]) if avec_pages else None,
        "plus_court": min(avec_pages, key=lambda l: l["pages"]) if avec_pages else None,
        "historique": historique,
        "livres": livres,
    }
