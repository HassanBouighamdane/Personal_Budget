# -*- coding: utf-8 -*-
"""Routes des transactions : dépenses et revenus (création, modification, suppression avec
annulation, liste), recherche dans tout l'historique, suggestions, tags, export et import CSV."""
import csv
import io
import re
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from psycopg.errors import UniqueViolation

from database import db, references_valides
from securite import utilisateur_courant
from schemas import DepenseIn, DepenseRestauree, ImportIn, RevenuIn, RevenuRestaure

router = APIRouter(prefix="/api", tags=["transactions"],
                   dependencies=[Depends(utilisateur_courant)])

COLS_DEP = "id,date,categorie,description,montant,tags"
COLS_REV = "id,date,COALESCE(source,'') source,COALESCE(description,'') description,montant,tags"


def _verifier_categorie(c, nom: str, actuelle: str | None = None):
    """Refuse une catégorie désactivée (une catégorie inexistante, la clé étrangère la refuse
    déjà). Une dépense modifiée peut garder sa catégorie actuelle, même désactivée depuis."""
    if nom == actuelle:
        return
    if not c.execute("SELECT 1 FROM categories WHERE nom=%s AND actif=1", (nom,)).fetchone():
        raise HTTPException(400, f"Catégorie inconnue ou désactivée : « {nom} »")


def _source(c, nom: str) -> str | None:
    """Source d'un revenu : None si vide. Une source libre (« Autre… » dans le formulaire) est
    ajoutée aux sources comme RETIRÉE (absente des listes, hors taux horaire) : la clé étrangère
    est respectée et la renommer plus tard renommera aussi ses revenus."""
    nom = nom.strip()
    if not nom:
        return None
    c.execute("""INSERT INTO sources_revenus(nom, actif, travail) VALUES(%s, 0, false)
                 ON CONFLICT (nom) DO NOTHING""", (nom,))
    return nom

@router.post("/depenses")
def ajouter_depense(d: DepenseIn):
    categorie = d.categorie.strip()
    with db() as c:
        _verifier_categorie(c, categorie)
        row = c.execute("INSERT INTO depenses(date,categorie,description,montant,tags) "
                        "VALUES(%s,%s,%s,%s,%s) RETURNING id",
                        (d.date, categorie, d.description.strip(), d.montant, d.tags)).fetchone()
    return {"id": row["id"]}

@router.put("/depenses/{did}")
def modifier_depense(did: int, d: DepenseIn):
    categorie = d.categorie.strip()
    with db() as c:
        ancienne = c.execute("SELECT categorie FROM depenses WHERE id=%s", (did,)).fetchone()
        if not ancienne:
            raise HTTPException(404, "Dépense introuvable")
        _verifier_categorie(c, categorie, ancienne["categorie"])
        c.execute("UPDATE depenses SET date=%s, categorie=%s, description=%s, montant=%s, tags=%s WHERE id=%s",
                  (d.date, categorie, d.description.strip(), d.montant, d.tags, did))
    return {"ok": True}

@router.delete("/depenses/{did}")
def supprimer_depense(did: int):
    """Renvoie la ligne supprimée : le frontend la renvoie à /depenses/restaurer pour « Annuler »."""
    with db() as c:
        row = c.execute(f"DELETE FROM depenses WHERE id=%s RETURNING {COLS_DEP}", (did,)).fetchone()
    if not row:
        raise HTTPException(404, "Dépense introuvable")
    return row

@router.post("/depenses/restaurer")
def restaurer_depense(d: DepenseRestauree):
    """Annule une suppression : la dépense revient sous son identifiant d'origine. Sa catégorie
    peut avoir été désactivée depuis (cas d'une ancienne dépense), elle doit seulement exister
    (clé étrangère)."""
    try:
        with references_valides(), db() as c:
            c.execute("INSERT INTO depenses(id,date,categorie,description,montant,tags) VALUES(%s,%s,%s,%s,%s,%s)",
                      (d.id, d.date, d.categorie, d.description, d.montant, d.tags))
    except UniqueViolation:
        raise HTTPException(409, "Cette dépense existe déjà")
    return {"id": d.id}

@router.post("/revenus")
def ajouter_revenu(r: RevenuIn):
    with db() as c:
        row = c.execute("INSERT INTO revenus(date,source,description,montant,tags) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                        (r.date, _source(c, r.source), r.description.strip(), r.montant, r.tags)).fetchone()
    return {"id": row["id"]}

@router.put("/revenus/{rid}")
def modifier_revenu(rid: int, r: RevenuIn):
    with db() as c:
        res = c.execute("UPDATE revenus SET date=%s, source=%s, description=%s, montant=%s, tags=%s WHERE id=%s",
                        (r.date, _source(c, r.source), r.description.strip(), r.montant, r.tags, rid))
        if res.rowcount == 0:
            raise HTTPException(404, "Revenu introuvable")
    return {"ok": True}

@router.delete("/revenus/{rid}")
def supprimer_revenu(rid: int):
    with db() as c:
        row = c.execute(f"DELETE FROM revenus WHERE id=%s RETURNING {COLS_REV}", (rid,)).fetchone()
    if not row:
        raise HTTPException(404, "Revenu introuvable")
    return row

@router.post("/revenus/restaurer")
def restaurer_revenu(r: RevenuRestaure):
    try:
        with db() as c:
            c.execute("INSERT INTO revenus(id,date,source,description,montant,tags) VALUES(%s,%s,%s,%s,%s,%s)",
                      (r.id, r.date, _source(c, r.source), r.description, r.montant, r.tags))
    except UniqueViolation:
        raise HTTPException(409, "Ce revenu existe déjà")
    return {"id": r.id}

@router.get("/transactions")
def transactions(mois: str):
    try:
        datetime.strptime(mois, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "Format de mois attendu : AAAA-MM")
    like = mois + "-%"
    with db() as c:
        dep = c.execute(f"SELECT {COLS_DEP} FROM depenses "
                        "WHERE date LIKE %s ORDER BY date DESC, id DESC", (like,)).fetchall()
        rev = c.execute(f"SELECT {COLS_REV} FROM revenus "
                        "WHERE date LIKE %s ORDER BY date DESC, id DESC", (like,)).fetchall()
    return {"depenses": dep, "revenus": rev}


# ------------------------------------------------------------------ Recherche
def analyser_recherche(q: str) -> tuple:
    """« #voyage restaurant 250 » → (tags, texte, montant). Les mots en # sont des tags, un
    nombre seul (250, 250,50) est un montant exact, le reste est cherché dans la description
    et la catégorie / source."""
    tags, mots, montant = [], [], None
    for mot in q.split():
        if mot.startswith("#") and len(mot) > 1:
            tags.append(mot[1:].lower())
        elif montant is None and re.fullmatch(r"\d+([.,]\d{1,2})?", mot):
            montant = float(mot.replace(",", "."))
        else:
            mots.append(mot)
    return tags, " ".join(mots), montant

@router.get("/recherche")
def rechercher(q: str = "", limite: int = 50, decalage: int = 0,
               du: Optional[date] = None, au: Optional[date] = None):
    """Dépenses et revenus, du plus récent au plus ancien, avec les totaux de toutes les lignes
    trouvées (pas seulement de la page) et leur répartition par catégorie / source. `du` et `au`
    (inclus) limitent à une période ; sans texte, une période seule liste toutes ses opérations."""
    if du and au and du > au:
        raise HTTPException(400, "La date de début doit précéder la date de fin")
    tags, texte, montant = analyser_recherche(q)
    if not (tags or texte or montant is not None or du or au):
        return {"resultats": [], "nb": 0, "total_depenses": 0, "total_revenus": 0, "par_rubrique": []}
    conditions, params = [], []
    if du:
        conditions.append("date >= %s")
        params.append(du.isoformat())
    if au:
        conditions.append("date <= %s")
        params.append(au.isoformat())
    if tags:
        conditions.append("tags @> %s::text[]")
        params.append(tags)
    if texte:
        conditions.append("(description ILIKE %s OR nom ILIKE %s)")
        params += [f"%{texte}%"] * 2
    if montant is not None:
        conditions.append("abs(montant - %s) < 0.005")
        params.append(montant)
    toutes = f"""SELECT * FROM (
        SELECT 'depenses' type, id, date, categorie nom, description, montant, tags FROM depenses
        UNION ALL
        SELECT 'revenus', id, date, COALESCE(source,''), COALESCE(description,''), montant, tags FROM revenus
    ) x WHERE {' AND '.join(conditions)}"""
    limite = max(1, min(limite, 200))
    with db() as c:
        lignes = c.execute(toutes + " ORDER BY date DESC, id DESC LIMIT %s OFFSET %s",
                           (*params, limite, max(decalage, 0))).fetchall()
        totaux = c.execute(f"""SELECT COUNT(*) nb,
                                      COALESCE(SUM(montant) FILTER (WHERE type='depenses'),0) dep,
                                      COALESCE(SUM(montant) FILTER (WHERE type='revenus'),0) rev
                               FROM ({toutes}) t""", params).fetchone()
        rubriques = c.execute(f"""SELECT type, nom, COUNT(*) nb, SUM(montant) montant FROM ({toutes}) t
                                  GROUP BY type, nom ORDER BY type, SUM(montant) DESC, nom""", params).fetchall()
    return {"resultats": lignes, "nb": totaux["nb"],
            "total_depenses": round(totaux["dep"], 2), "total_revenus": round(totaux["rev"], 2),
            "par_rubrique": [{**r, "montant": round(r["montant"], 2)} for r in rubriques]}


# ------------------------------------------------------------------ Suggestions et tags
@router.get("/suggestions")
def suggestions(type: str, nom: str):
    """Les 5 dernières descriptions distinctes d'une catégorie (dépenses) ou source (revenus),
    avec le dernier montant saisi pour chacune."""
    if type not in ("depenses", "revenus"):
        raise HTTPException(400, "type : depenses ou revenus")
    colonne = "categorie" if type == "depenses" else "source"
    with db() as c:
        return c.execute(f"""SELECT description, (array_agg(montant ORDER BY date DESC, id DESC))[1] montant
                             FROM {type} WHERE {colonne}=%s AND COALESCE(description,'') <> ''
                             GROUP BY description ORDER BY MAX(date) DESC, MAX(id) DESC LIMIT 5""",
                         (nom,)).fetchall()

@router.get("/tags")
def lister_tags():
    """Chaque tag avec son nombre d'opérations, ses totaux et sa période : « combien a coûté
    ce voyage ? »."""
    with db() as c:
        return c.execute("""SELECT tag, COUNT(*) nb, ROUND(SUM(dep)::numeric, 2)::float depenses,
                                   ROUND(SUM(rev)::numeric, 2)::float revenus, MIN(date) premier, MAX(date) dernier
                            FROM (SELECT unnest(tags) tag, montant dep, 0 rev, date FROM depenses
                                  UNION ALL
                                  SELECT unnest(tags), 0, montant, date FROM revenus) x
                            GROUP BY tag ORDER BY MAX(date) DESC, tag""").fetchall()


# ------------------------------------------------------------------ Export / import CSV
def _montant_fr(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")

@router.get("/export/csv")
def exporter_csv(debut: Optional[str] = None, fin: Optional[str] = None):
    """Dépenses et revenus entre deux dates incluses (toutes si absentes), au format CSV
    lisible par Excel en français : séparateur « ; », virgule décimale, BOM UTF-8."""
    for d in (debut, fin):
        if d:
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, "Format de date attendu : AAAA-MM-JJ")
    ou, params = "WHERE date >= %s AND date <= %s", (debut or "0000-00-00", fin or "9999-99-99")
    with db() as c:
        lignes = c.execute(f"""SELECT 'depense' type, date, categorie nom, description, montant, tags FROM depenses {ou}
                               UNION ALL
                               SELECT 'revenu', date, COALESCE(source,''), COALESCE(description,''), montant, tags FROM revenus {ou}
                               ORDER BY date, type""", params * 2).fetchall()
    sortie = io.StringIO()
    sortie.write("﻿")
    w = csv.writer(sortie, delimiter=";", lineterminator="\r\n")
    w.writerow(["type", "date", "categorie_ou_source", "description", "montant", "tags"])
    for l in lignes:
        w.writerow([l["type"], l["date"], l["nom"], l["description"], _montant_fr(l["montant"]), ", ".join(l["tags"])])
    nom = f"budget_{debut or 'debut'}_{fin or 'fin'}.csv"
    return Response(sortie.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})

@router.post("/import")
def importer(donnees: ImportIn):
    """Lignes déjà converties par le frontend (correspondance des colonnes faite à l'écran).
    Chaque ligne reçoit un statut : `ajoutee`, `doublon` (même type, date, montant et
    description qu'une opération existante : ignorée) ou `erreur`. Avec `simulation`, rien
    n'est enregistré : c'est l'aperçu."""
    statuts, a_inserer = [], []
    with db() as c:
        actives = {r["nom"] for r in c.execute("SELECT nom FROM categories WHERE actif=1").fetchall()}
        for l in donnees.lignes:
            table, colonne = ("depenses", "categorie") if l.type == "depense" else ("revenus", "source")
            nom, description = l.nom.strip(), l.description.strip()
            if l.type == "depense" and nom not in actives:
                statuts.append({"statut": "erreur", "message": f"Catégorie inconnue ou désactivée : « {nom} »"})
                continue
            if c.execute(f"""SELECT 1 FROM {table} WHERE date=%s AND abs(montant-%s) < 0.005
                             AND lower(trim(COALESCE(description,''))) = lower(%s) LIMIT 1""",
                         (l.date, l.montant, description)).fetchone():
                statuts.append({"statut": "doublon", "message": "Déjà enregistrée"})
                continue
            statuts.append({"statut": "ajoutee", "message": ""})
            a_inserer.append((table, colonne, (l.date, nom, description, l.montant, l.tags)))
        if not donnees.simulation:
            for table, colonne, valeurs in a_inserer:
                if table == "revenus":
                    valeurs = (valeurs[0], _source(c, valeurs[1]), *valeurs[2:])
                c.execute(f"INSERT INTO {table}(date,{colonne},description,montant,tags) VALUES(%s,%s,%s,%s,%s)", valeurs)
    return {"statuts": statuts,
            "nb_ajoutees": len(a_inserer), "nb_doublons": sum(s["statut"] == "doublon" for s in statuts),
            "nb_erreurs": sum(s["statut"] == "erreur" for s in statuts), "simulation": donnees.simulation}
