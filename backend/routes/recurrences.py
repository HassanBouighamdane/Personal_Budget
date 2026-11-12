# -*- coding: utf-8 -*-
"""
Opérations récurrentes : loyer, abonnements, factures, salaire. Chaque récurrence donne une dépense
(ou un revenu) par mois, au jour choisi. Un jour 29, 30 ou 31 tombe au dernier jour des mois plus courts.

Deux façons de les ajouter au Budget :
  - avec le bouton de Saisie (« À ajouter ce mois-ci »), qui laisse corriger le montant d'une facture
    qui varie (électricité) ou passer un mois ;
  - toute seule, le jour dit, par la tâche du matin, pour les récurrences marquées `auto`.

`dernier_mois` garde le dernier mois généré (ou passé) : un second passage ne fait rien, et des mois
manqués (tâche du matin arrêtée) sont rattrapés dans l'ordre. Une opération générée est une
opération ordinaire : elle se modifie ou se supprime dans Saisie comme les autres.

Suggestions : une même dépense (même catégorie, même description) présente une seule fois dans
chacun des 3 derniers mois terminés, avec des montants à 10 % près, est proposée comme récurrence.
"""
import calendar
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from config import aujourdhui
from database import db, references_valides
from schemas import GenerationIn, PasserIn, RecurrenceIn
from securite import utilisateur_courant
from routes.transactions import _source, _verifier_categorie

router = APIRouter(prefix="/api/recurrences", tags=["recurrences"],
                   dependencies=[Depends(utilisateur_courant)])

COLONNES = "id, type, categorie, source, description, montant, jour, tags, auto, actif, debut, dernier_mois"
MOIS_SUGGESTION = 3
ECART_SUGGESTION = 0.10
# Descriptions jamais proposées : écritures techniques de l'application
DESCRIPTIONS_EXCLUES = {"écart de pointage du solde"}


# ---------------------------------------------------------------- calendrier (sans base)
def mois_de(d: date) -> str:
    return d.strftime("%Y-%m")


def mois_suivant(mois: str) -> str:
    a, m = int(mois[:4]), int(mois[5:7])
    return f"{a + m // 12}-{m % 12 + 1:02d}"


def mois_precedent(mois: str) -> str:
    a, m = int(mois[:4]), int(mois[5:7])
    return f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"


def date_du_mois(mois: str, jour: int) -> date:
    """Jour `jour` du mois AAAA-MM, ramené au dernier jour d'un mois plus court (31 → 30 avril, 28 février)."""
    a, m = int(mois[:4]), int(mois[5:7])
    return date(a, m, min(jour, calendar.monthrange(a, m)[1]))


def premier_mois_attendu(r: dict) -> str:
    """Prochain mois à générer : le mois après `dernier_mois`, jamais avant `debut`."""
    if r["dernier_mois"] and r["dernier_mois"] >= r["debut"]:
        return mois_suivant(r["dernier_mois"])
    return r["debut"]


def mois_a_generer(r: dict, jusqua: str) -> list:
    """Mois encore à générer pour la récurrence `r`, du plus ancien à `jusqua` inclus."""
    mois, resultat = premier_mois_attendu(r), []
    while mois <= jusqua:
        resultat.append(mois)
        mois = mois_suivant(mois)
    return resultat


def echeances_en_attente(recurrences: list, auj: date, seulement_echues: bool = False) -> list:
    """[{recurrence, mois, date}] des récurrences actives pas encore générées, jusqu'au mois en cours.
    `seulement_echues` : sans celles dont la date est encore à venir (tâche du matin)."""
    resultat = []
    for r in recurrences:
        if not r["actif"]:
            continue
        for mois in mois_a_generer(r, mois_de(auj)):
            jour = date_du_mois(mois, r["jour"])
            if seulement_echues and jour > auj:
                break
            resultat.append({"recurrence": r, "mois": mois, "date": jour})
    return sorted(resultat, key=lambda e: (e["date"], e["recurrence"]["id"]))


# ---------------------------------------------------------------- lecture
def _ligne(r: dict) -> dict:
    return {**r, "montant": float(r["montant"]), "nom": (r["categorie"] if r["type"] == "depense" else r["source"]) or ""}


def lire_recurrences(c, recurrence_id: Optional[int] = None) -> list:
    clause, params = (" WHERE id=%s", (recurrence_id,)) if recurrence_id is not None else ("", ())
    rows = c.execute(f"SELECT {COLONNES} FROM recurrences{clause} ORDER BY type, jour, id", params).fetchall()
    return [_ligne(r) for r in rows]


def _recurrence(c, recurrence_id: int, verrou: bool = False) -> dict:
    row = c.execute(f"SELECT {COLONNES} FROM recurrences WHERE id=%s{' FOR UPDATE' if verrou else ''}",
                    (recurrence_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Récurrence introuvable")
    return _ligne(row)


def _avec_prochaine(r: dict, auj: date) -> dict:
    """Ajoute la prochaine date prévue et le nombre de mois en retard (non générés jusqu'au mois en cours)."""
    mois = premier_mois_attendu(r)
    en_attente = len(mois_a_generer(r, mois_de(auj))) if r["actif"] else 0
    return {**r, "prochain_mois": mois, "prochaine_date": date_du_mois(mois, r["jour"]), "en_attente": en_attente}


@router.get("")
def lister():
    auj = aujourdhui()
    with db() as c:
        return [_avec_prochaine(r, auj) for r in lire_recurrences(c)]


@router.get("/a-generer")
def a_generer():
    """Ce qui reste à ajouter jusqu'au mois en cours, y compris les dates à venir de ce mois-ci."""
    auj = aujourdhui()
    with db() as c:
        recurrences = lire_recurrences(c)
    return [{"id": e["recurrence"]["id"], "type": e["recurrence"]["type"], "nom": e["recurrence"]["nom"],
             "description": e["recurrence"]["description"], "montant": e["recurrence"]["montant"],
             "auto": e["recurrence"]["auto"], "mois": e["mois"], "date": e["date"], "a_venir": e["date"] > auj}
            for e in echeances_en_attente(recurrences, auj)]


# ---------------------------------------------------------------- écriture
def _valeurs(c, r: RecurrenceIn, actuelle: Optional[dict] = None) -> tuple:
    """Colonnes catégorie et source selon le type ; une dépense exige une catégorie active (sauf si elle
    garde sa catégorie actuelle, désactivée depuis)."""
    if r.type == "depense":
        if not r.nom:
            raise HTTPException(400, "Choisis la catégorie de la dépense")
        _verifier_categorie(c, r.nom, actuelle["categorie"] if actuelle else None)
        categorie, source = r.nom, None
    else:
        categorie, source = None, _source(c, r.nom)
    return (r.type, categorie, source, r.description, Decimal(str(r.montant)), r.jour, r.tags, r.auto, r.actif, r.debut)


@router.post("", status_code=201)
def ajouter(r: RecurrenceIn):
    with references_valides(), db() as c:
        row = c.execute("""INSERT INTO recurrences (type, categorie, source, description, montant, jour, tags, auto, actif, debut)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", _valeurs(c, r)).fetchone()
        return _avec_prochaine(_recurrence(c, row["id"]), aujourdhui())


@router.put("/{recurrence_id}")
def modifier(recurrence_id: int, r: RecurrenceIn):
    """Changer le montant ou le jour ne touche pas les opérations déjà générées. Avancer `debut`
    au-delà du dernier mois généré ne fait rien de plus ; le reculer ne regénère pas les mois déjà faits."""
    with references_valides(), db() as c:
        actuelle = _recurrence(c, recurrence_id)
        c.execute("""UPDATE recurrences SET type=%s, categorie=%s, source=%s, description=%s, montant=%s, jour=%s,
                     tags=%s, auto=%s, actif=%s, debut=%s WHERE id=%s""", (*_valeurs(c, r, actuelle), recurrence_id))
        return _avec_prochaine(_recurrence(c, recurrence_id), aujourdhui())


@router.delete("/{recurrence_id}", status_code=204)
def supprimer(recurrence_id: int):
    """Les opérations déjà générées restent dans le Budget."""
    with db() as c:
        if c.execute("DELETE FROM recurrences WHERE id=%s", (recurrence_id,)).rowcount == 0:
            raise HTTPException(404, "Récurrence introuvable")


def _generer_une(c, recurrence_id: int, mois: str, montant: Optional[float] = None, inserer: bool = True) -> Optional[dict]:
    """Ajoute l'opération du mois `mois` (ou le passe seulement, `inserer=False`). Ne fait rien et renvoie
    None si ce mois n'est pas le prochain attendu (déjà généré par un autre passage, ou un mois sauté).
    La ligne de la récurrence est verrouillée : deux passages simultanés ne génèrent pas deux fois."""
    r = _recurrence(c, recurrence_id, verrou=True)
    if not r["actif"] or premier_mois_attendu(r) != mois:
        return None
    jour = date_du_mois(mois, r["jour"])
    valeur = Decimal(str(montant)) if montant is not None else Decimal(str(r["montant"]))
    if inserer:
        if r["type"] == "depense":
            c.execute("INSERT INTO depenses(date,categorie,description,montant,tags) VALUES(%s,%s,%s,%s,%s)",
                      (jour.isoformat(), r["categorie"], r["description"], valeur, r["tags"]))
        else:
            c.execute("INSERT INTO revenus(date,source,description,montant,tags) VALUES(%s,%s,%s,%s,%s)",
                      (jour.isoformat(), r["source"], r["description"], valeur, r["tags"]))
    c.execute("UPDATE recurrences SET dernier_mois=%s WHERE id=%s", (mois, recurrence_id))
    return {"id": r["id"], "type": r["type"], "nom": r["nom"], "description": r["description"],
            "montant": float(valeur), "date": jour, "mois": mois}


@router.post("/generer")
def generer(g: GenerationIn):
    """Ajoute les opérations choisies (une par récurrence et par mois, dans l'ordre des mois).
    `montant` remplace celui de la récurrence pour ce mois seulement."""
    generees, ignorees = [], 0
    with references_valides(), db() as c:
        for e in sorted(g.elements, key=lambda e: (e.mois, e.id)):
            fait = _generer_une(c, e.id, e.mois, e.montant)
            if fait:
                generees.append(fait)
            else:
                ignorees += 1
    return {"generees": generees, "ignorees": ignorees}


@router.post("/{recurrence_id}/passer")
def passer(recurrence_id: int, p: PasserIn):
    """Ce mois-ci, rien à ajouter (abonnement suspendu, loyer payé autrement) : le mois est marqué fait."""
    with db() as c:
        if not _generer_une(c, recurrence_id, p.mois, inserer=False):
            raise HTTPException(409, "Ce mois n'est pas le prochain à ajouter pour cette récurrence")
    return {"ok": True}


def generer_automatiques(auj: date) -> list:
    """Tâche du matin : ajoute les opérations des récurrences `auto` dont la date est arrivée (mois
    manqués compris). Une récurrence dont la catégorie a été désactivée est laissée de côté."""
    with db() as c:
        inactives = {r["nom"] for r in c.execute("SELECT nom FROM categories WHERE actif=0").fetchall()}
        recurrences = [r for r in lire_recurrences(c) if r["auto"] and r["categorie"] not in inactives]
    generees = []
    with db() as c:
        for e in echeances_en_attente(recurrences, auj, seulement_echues=True):
            fait = _generer_une(c, e["recurrence"]["id"], e["mois"])
            if fait:
                generees.append(fait)
    return generees


def a_ajouter_aujourdhui(auj: date) -> list:
    """Récurrences manuelles (sans `auto`) dont la date tombe aujourd'hui : rappelées le matin."""
    with db() as c:
        recurrences = [r for r in lire_recurrences(c) if not r["auto"]]
    return [e["recurrence"] for e in echeances_en_attente(recurrences, auj) if e["date"] == auj]


# ---------------------------------------------------------------- suggestions
def _cle(description: str) -> str:
    return " ".join((description or "").lower().split())


def suggerer(lignes: list, mois_attendus: list, existantes: set) -> list:
    """Opérations présentes une seule fois dans CHACUN des `mois_attendus`, avec la même catégorie
    (ou source) et la même description, à des montants proches (±10 % de leur moyenne).
    `lignes` : [{type, nom, description, date (AAAA-MM-JJ), montant, tags}] ; `existantes` :
    {(type, nom, description normalisée)} déjà couvertes par une récurrence."""
    groupes = {}
    for l in lignes:
        cle = (l["type"], l["nom"] or "", _cle(l["description"]))
        if cle in existantes or cle[2] in DESCRIPTIONS_EXCLUES:
            continue
        groupes.setdefault(cle, []).append(l)
    attendus = sorted(mois_attendus)
    suggestions = []
    for (type_, nom, _), ops in groupes.items():
        if sorted(o["date"][:7] for o in ops) != attendus:
            continue          # absente d'un mois, ou plusieurs fois le même mois
        montants = [float(o["montant"]) for o in ops]
        moyenne = sum(montants) / len(montants)
        if any(abs(m - moyenne) > ECART_SUGGESTION * moyenne for m in montants):
            continue
        derniere = max(ops, key=lambda o: o["date"])
        suggestions.append({"type": type_, "nom": nom, "description": derniere["description"] or "",
                            "montant": float(derniere["montant"]), "jour": int(median(int(o["date"][8:10]) for o in ops)),
                            "tags": list(derniere["tags"] or []), "moyenne": round(moyenne, 2)})
    return sorted(suggestions, key=lambda s: (s["type"], -s["montant"]))


@router.get("/suggestions")
def suggestions():
    auj = aujourdhui()
    fin = mois_de(auj)
    mois = [fin]
    for _ in range(MOIS_SUGGESTION):
        mois.insert(0, mois_precedent(mois[0]))
    attendus, debut = mois[:-1], mois[0]
    with db() as c:
        lignes = c.execute("""SELECT 'depense' AS type, categorie AS nom, COALESCE(description,'') description, date, montant, tags
                              FROM depenses WHERE date >= %s AND date < %s
                              UNION ALL
                              SELECT 'revenu', COALESCE(source,''), COALESCE(description,''), date, montant, tags
                              FROM revenus WHERE date >= %s AND date < %s""",
                           (debut + "-01", fin + "-01", debut + "-01", fin + "-01")).fetchall()
        existantes = {(r["type"], r["nom"], _cle(r["description"])) for r in lire_recurrences(c)}
    return suggerer(lignes, attendus, existantes)
