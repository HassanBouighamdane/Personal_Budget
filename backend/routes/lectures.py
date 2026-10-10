# -*- coding: utf-8 -*-
"""
Module Lectures — journal des livres terminés et bilan annuel.

Un livre compte pour l'année et le mois de sa date de FIN de lecture. Une
relecture est une nouvelle ligne : elle compte comme un livre lu de plus.

Objectifs (nombre de livres) : un objectif annuel et un objectif mensuel,
stockés dans la table `params` comme l'objectif d'épargne du Budget.
"""
import io
import json
import math
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from psycopg.errors import UniqueViolation

from config import aujourdhui
from database import db
from securite import utilisateur_courant
from schemas import (ALireIn, ALireOut, FicheIsbn, GenreOut, LivreIn, LivreOut, NomIn, NoteIn, NoteOut,
                     ObjectifsLecture, PretLivreIn, PretLivreOut, ProgressionIn)

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


def rythme(livre: dict, points: list, auj: date) -> dict:
    """Suivi d'un livre en cours d'après ses pages notées (`points` : [(date, page)] triés).
    Le rythme part du début de la lecture (page 0 à `date_debut`) et va jusqu'à la dernière
    page notée ; la fin estimée prolonge ce rythme à partir d'aujourd'hui. Pas de rythme sur moins
    d'un jour : un livre marqué commencé aujourd'hui alors qu'on est déjà page 92 ferait « 92 p. / jour »."""
    if not points:
        return {"page_actuelle": None, "derniere_lecture": None, "pages_par_jour": None, "fin_estimee": None}
    dernier_jour, page = points[-1]
    debut, page_debut = points[0]
    if livre["date_debut"] and livre["date_debut"] <= debut:
        debut, page_debut = livre["date_debut"], 0
    jours = (dernier_jour - debut).days
    par_jour = (page - page_debut) / jours if jours > 0 else 0
    fin = None
    if livre["pages"] and par_jour > 0 and page < livre["pages"]:
        fin = auj + timedelta(days=math.ceil((livre["pages"] - page) / par_jour))
    return {"page_actuelle": page, "derniere_lecture": dernier_jour,
            "pages_par_jour": round(par_jour, 1) if par_jour > 0 else None, "fin_estimee": fin}


def _avec_rythme(c, livres: list, auj: date) -> list:
    points = {}
    for r in c.execute("SELECT a_lire_id, date, page FROM lectures_progression ORDER BY date").fetchall():
        points.setdefault(r["a_lire_id"], []).append((r["date"], r["page"]))
    return [{**l, **rythme(l, points.get(l["id"], []), auj)} for l in livres]


def _a_lire(c, a_lire_id: int):
    row = c.execute(f"""SELECT {A_LIRE_COLONNES},
                        (SELECT COUNT(*) FROM lectures_notes n WHERE n.a_lire_id = a.id)::int nb_notes
                        FROM lectures_a_lire a WHERE id=%s""", (a_lire_id,)).fetchone()
    return row and _avec_rythme(c, [row], aujourdhui())[0]


@router.get("/a_lire", response_model=List[ALireOut])
def lister_a_lire():
    """Livres en cours d'abord (du plus récemment commencé), puis la liste à lire (ordre d'ajout)."""
    with db() as c:
        rows = c.execute(f"""SELECT {A_LIRE_COLONNES},
                             (SELECT COUNT(*) FROM lectures_notes n WHERE n.a_lire_id = a.id)::int nb_notes
                             FROM lectures_a_lire a
                             ORDER BY date_debut IS NULL, date_debut DESC, id""").fetchall()
        return _avec_rythme(c, rows, aujourdhui())


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
        if l.date_fin == aujourdhui():   # finir un livre aujourd'hui, c'est avoir lu aujourd'hui
            c.execute("INSERT INTO lectures_jours(date) VALUES(%s) ON CONFLICT DO NOTHING", (l.date_fin,))
        return _livre(c, livre_id)


@router.put("/a_lire/{a_lire_id}/progression", response_model=ALireOut)
def noter_progression(a_lire_id: int, p: ProgressionIn):
    """Note la page atteinte aujourd'hui (une seule valeur par jour : la dernière saisie). Un livre
    de la liste « à lire » passe en cours ; une page en avance compte comme un jour de lecture."""
    auj = aujourdhui()
    with db() as c:
        livre = c.execute("SELECT pages, date_debut FROM lectures_a_lire WHERE id=%s", (a_lire_id,)).fetchone()
        if not livre:
            raise HTTPException(404, "Livre introuvable")
        if livre["pages"] and p.page > livre["pages"]:
            raise HTTPException(400, f"Ce livre n'a que {livre['pages']} pages")
        avant = c.execute("SELECT page FROM lectures_progression WHERE a_lire_id=%s AND date < %s ORDER BY date DESC LIMIT 1",
                          (a_lire_id, auj)).fetchone()
        c.execute("""INSERT INTO lectures_progression(a_lire_id, date, page) VALUES(%s,%s,%s)
                     ON CONFLICT (a_lire_id, date) DO UPDATE SET page=EXCLUDED.page""", (a_lire_id, auj, p.page))
        if not livre["date_debut"]:
            c.execute("UPDATE lectures_a_lire SET date_debut=%s WHERE id=%s", (auj, a_lire_id))
        if p.page > (avant["page"] if avant else 0):
            c.execute("INSERT INTO lectures_jours(date) VALUES(%s) ON CONFLICT DO NOTHING", (auj,))
        return _a_lire(c, a_lire_id)


def calculer_serie(jours: set, auj: date) -> dict:
    """Jours de lecture consécutifs. La série en cours tient encore si l'on a lu hier :
    il reste la journée d'aujourd'hui pour la prolonger."""
    fin = auj if auj in jours else auj - timedelta(days=1)
    n = 0
    while fin - timedelta(days=n) in jours:
        n += 1
    record = courant = 0
    precedent = None
    for j in sorted(jours):
        courant = courant + 1 if precedent and (j - precedent).days == 1 else 1
        record, precedent = max(record, courant), j
    return {"serie": n, "record": record, "lu_aujourdhui": auj in jours}


@router.get("/serie")
def obtenir_serie():
    with db() as c:
        jours = {r["date"] for r in c.execute("SELECT date FROM lectures_jours").fetchall()}
    return calculer_serie(jours, aujourdhui())


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
    requete = urllib.request.Request(URL_OPEN_LIBRARY.format(isbn=v), headers={"User-Agent": "Carnet/2.2"})
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


# ---------------------------------------------------------------- note ou citation du jour
NOTE_AVEC_LIVRE = """SELECT n.id, n.type, n.texte, n.page,
                            COALESCE(l.titre, a.titre) titre, COALESCE(l.auteur, a.auteur) auteur
                     FROM lectures_notes n
                     LEFT JOIN lectures_livres l ON l.id = n.livre_id
                     LEFT JOIN lectures_a_lire a ON a.id = n.a_lire_id"""


def note_du_jour(auj: date, decalage: int = 0) -> Optional[dict]:
    """Une note ou citation tirée de tous les livres : la même toute la journée, une autre le
    lendemain. `decalage` en fait défiler d'autres (bouton « Une autre »)."""
    with db() as c:
        nb = c.execute("SELECT COUNT(*) n FROM lectures_notes").fetchone()["n"]
        if not nb:
            return None
        # Multiplier par un nombre premier disperse les jours consécutifs dans la liste
        rang = (auj.toordinal() * 7919 + decalage) % nb
        return c.execute(NOTE_AVEC_LIVRE + " ORDER BY n.id OFFSET %s LIMIT 1", (rang,)).fetchone()


@router.get("/note_du_jour")
def obtenir_note_du_jour(decalage: int = 0):
    return note_du_jour(aujourdhui(), decalage)


# ---------------------------------------------------------------- export des notes en Markdown
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def notes_en_markdown(livre: dict, notes: list) -> str:
    """Fiche d'un livre : en-tête, avis, puis citations et notes dans l'ordre des pages."""
    infos = [f"*{livre['auteur']}*"] if livre.get("auteur") else []
    if livre.get("date_fin"):
        d = livre["date_fin"]
        infos.append(f"terminé le {d.day} {MOIS[d.month - 1]} {d.year}")
    elif livre.get("date_debut"):
        infos.append("en cours de lecture")
    if livre.get("note"):
        infos.append("★" * livre["note"] + "☆" * (5 - livre["note"]))
    lignes = [f"# {livre['titre']}", ""]
    if infos:
        lignes += [" · ".join(infos), ""]
    if livre.get("commentaire"):
        lignes += ["## Mon avis", "", livre["commentaire"], ""]
    page = lambda n: f" — p. {n['page']}" if n["page"] else ""
    citations = [n for n in notes if n["type"] == "citation"]
    autres = [n for n in notes if n["type"] != "citation"]
    if citations:
        lignes += ["## Citations", ""]
        for n in citations:
            lignes += ["> " + n["texte"].replace("\n", "\n> ") + page(n), ""]
    if autres:
        lignes += ["## Notes", ""]
        for n in autres:
            lignes += ["- " + n["texte"].replace("\n", "\n  ") + page(n)]
        lignes.append("")
    return "\n".join(lignes)


def nom_fichier(titre: str, repli: str) -> str:
    """Nom de fichier sûr tiré du titre : sans accents ni ponctuation. Un titre sans lettre
    latine (arabe, par exemple) garde ses caractères, privés seulement de ce qu'un système
    de fichiers refuse."""
    ascii_ = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode()
    nom = re.sub(r"[^A-Za-z0-9]+", "-", ascii_).strip("-").lower()
    if len(nom) < 3:
        nom = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", titre).strip()
    return (nom or repli)[:80] + ".md"


def _livre_et_notes(c, livre_id: Optional[int], a_lire_id: Optional[int]) -> tuple:
    if livre_id is not None:
        livre = c.execute(f"SELECT {LIVRE_COLONNES} FROM lectures_livres WHERE id=%s", (livre_id,)).fetchone()
        colonne, valeur = "livre_id", livre_id
    else:
        livre = c.execute(f"SELECT {A_LIRE_COLONNES} FROM lectures_a_lire WHERE id=%s", (a_lire_id,)).fetchone()
        colonne, valeur = "a_lire_id", a_lire_id
    if not livre:
        raise HTTPException(404, "Livre introuvable")
    notes = c.execute(f"SELECT {NOTE_COLONNES} FROM lectures_notes WHERE {colonne}=%s ORDER BY page NULLS LAST, id",
                      (valeur,)).fetchall()
    return livre, notes


def _telechargement(contenu, type_mime: str, nom: str) -> Response:
    # filename* porte le vrai nom (UTF-8) ; filename, sa version ASCII pour les vieux navigateurs
    ascii_ = nom.encode("ascii", "ignore").decode().strip() or "notes"
    return Response(contenu, media_type=type_mime, headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{urllib.parse.quote(nom)}"})


@router.get("/notes/export")
def exporter_notes(livre_id: Optional[int] = None, a_lire_id: Optional[int] = None):
    """Les notes et citations d'un livre dans un fichier Markdown."""
    if (livre_id is None) == (a_lire_id is None):
        raise HTTPException(400, "Indique soit livre_id, soit a_lire_id")
    with db() as c:
        livre, notes = _livre_et_notes(c, livre_id, a_lire_id)
    return _telechargement(notes_en_markdown(livre, notes), "text/markdown; charset=utf-8",
                           nom_fichier(livre["titre"], f"livre-{livre['id']}"))


@router.get("/notes/export_tout")
def exporter_toutes_les_notes():
    """Archive ZIP : un fichier Markdown par livre qui a au moins une note ou un avis."""
    with db() as c:
        cibles = c.execute("""SELECT DISTINCT livre_id, a_lire_id FROM lectures_notes
                              UNION SELECT id, NULL FROM lectures_livres WHERE commentaire <> ''""").fetchall()
        fiches = [_livre_et_notes(c, r["livre_id"], r["a_lire_id"]) for r in cibles]
    if not fiches:
        raise HTTPException(404, "Aucune note à exporter")
    tampon, noms = io.BytesIO(), set()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for livre, notes in sorted(fiches, key=lambda f: f[0]["titre"].lower()):
            nom = nom_fichier(livre["titre"], f"livre-{livre['id']}")
            if nom in noms:   # deux livres de même titre (relecture)
                nom = f"{nom[:-3]}-{livre['id']}.md"
            noms.add(nom)
            archive.writestr(nom, notes_en_markdown(livre, notes))
    return _telechargement(tampon.getvalue(), "application/zip", "notes-de-lecture.zip")


# ---------------------------------------------------------------- livres prêtés
PRET_COLONNES = "id, titre, personne, date_pret, date_retour, note"


def _pret(p: dict, auj: date) -> dict:
    return {**p, "jours": ((p["date_retour"] or auj) - p["date_pret"]).days}


def _valeurs_pret(p: PretLivreIn) -> tuple:
    return (p.titre, p.personne, p.date_pret, p.date_retour, p.note.strip())


@router.get("/prets", response_model=List[PretLivreOut])
def lister_prets():
    """Livres encore prêtés d'abord (du plus ancien prêt au plus récent), puis les rendus."""
    auj = aujourdhui()
    with db() as c:
        rows = c.execute(f"""SELECT {PRET_COLONNES} FROM lectures_prets
                             ORDER BY date_retour IS NOT NULL, date_retour DESC, date_pret, id""").fetchall()
    return [_pret(r, auj) for r in rows]


@router.post("/prets", response_model=PretLivreOut, status_code=201)
def ajouter_pret(p: PretLivreIn):
    with db() as c:
        row = c.execute(f"""INSERT INTO lectures_prets (titre, personne, date_pret, date_retour, note)
                            VALUES (%s,%s,%s,%s,%s) RETURNING {PRET_COLONNES}""", _valeurs_pret(p)).fetchone()
    return _pret(row, aujourdhui())


@router.put("/prets/{pret_id}", response_model=PretLivreOut)
def modifier_pret(pret_id: int, p: PretLivreIn):
    with db() as c:
        row = c.execute(f"""UPDATE lectures_prets SET titre=%s, personne=%s, date_pret=%s, date_retour=%s, note=%s
                            WHERE id=%s RETURNING {PRET_COLONNES}""", (*_valeurs_pret(p), pret_id)).fetchone()
    if not row:
        raise HTTPException(404, "Prêt introuvable")
    return _pret(row, aujourdhui())


@router.delete("/prets/{pret_id}", status_code=204)
def supprimer_pret(pret_id: int):
    with db() as c:
        if c.execute("DELETE FROM lectures_prets WHERE id=%s", (pret_id,)).rowcount == 0:
            raise HTTPException(404, "Prêt introuvable")


@router.get("/titres", response_model=List[str])
def lister_titres():
    """Titres déjà saisis (lus, en cours, à lire), pour l'autocomplétion du prêt."""
    with db() as c:
        rows = c.execute("SELECT titre FROM lectures_livres UNION SELECT titre FROM lectures_a_lire ORDER BY 1").fetchall()
    return [r["titre"] for r in rows]
