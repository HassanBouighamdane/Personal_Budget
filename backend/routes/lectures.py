# -*- coding: utf-8 -*-
"""
Module Lectures — journal des livres terminés et bilan annuel.

Un livre compte pour l'année et le mois de sa date de FIN de lecture. Une
relecture est une nouvelle ligne : elle compte comme un livre lu de plus.

Objectifs (nombre de livres) : un objectif annuel et un objectif mensuel,
stockés dans la table `params` comme l'objectif d'épargne du Budget.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from database import db
from securite import utilisateur_courant
from schemas import GenreOut, LivreIn, LivreOut, NomIn, ObjectifsLecture

router = APIRouter(prefix="/api/lectures", tags=["lectures"],
                   dependencies=[Depends(utilisateur_courant)])

LIVRE_COLONNES = "id, titre, auteur, genre, date_debut, date_fin, pages, note, commentaire"


def _valeurs(l: LivreIn) -> tuple:
    return (l.titre.strip(), l.auteur.strip(), l.genre.strip(), l.date_debut, l.date_fin,
            l.pages, l.note, l.commentaire.strip())


def _clause_annee(annee: Optional[int]) -> tuple:
    if annee is None:
        return "", ()
    return " WHERE date_fin >= %s AND date_fin < %s", (date(annee, 1, 1), date(annee + 1, 1, 1))


# ---------------------------------------------------------------- livres
@router.get("/livres", response_model=List[LivreOut])
def lister_livres(annee: Optional[int] = None):
    clause, params = _clause_annee(annee)
    with db() as c:
        return c.execute(f"SELECT {LIVRE_COLONNES} FROM lectures_livres{clause} "
                         "ORDER BY date_fin DESC, id DESC", params).fetchall()


@router.post("/livres", response_model=LivreOut, status_code=201)
def ajouter_livre(l: LivreIn):
    with db() as c:
        return c.execute(
            f"""INSERT INTO lectures_livres (titre, auteur, genre, date_debut, date_fin, pages, note, commentaire)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {LIVRE_COLONNES}""", _valeurs(l)).fetchone()


@router.put("/livres/{livre_id}", response_model=LivreOut)
def modifier_livre(livre_id: int, l: LivreIn):
    with db() as c:
        row = c.execute(
            f"""UPDATE lectures_livres SET titre=%s, auteur=%s, genre=%s, date_debut=%s, date_fin=%s,
                       pages=%s, note=%s, commentaire=%s
                WHERE id=%s RETURNING {LIVRE_COLONNES}""", (*_valeurs(l), livre_id)).fetchone()
    if not row:
        raise HTTPException(404, "Livre introuvable")
    return row


@router.delete("/livres/{livre_id}", status_code=204)
def supprimer_livre(livre_id: int):
    with db() as c:
        if c.execute("DELETE FROM lectures_livres WHERE id=%s", (livre_id,)).rowcount == 0:
            raise HTTPException(404, "Livre introuvable")


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
    return calculer_bilan(annee, date.today())


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
