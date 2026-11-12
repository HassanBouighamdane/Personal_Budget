# -*- coding: utf-8 -*-
"""
Objectifs d'épargne par projet : voyage, fonds d'urgence, voiture... Chacun a un montant cible et,
s'il le faut, une date limite. On y met de l'argent de côté par versements (ou on en reprend, avec
un montant négatif).

Un versement ne déplace pas d'argent : il reste dans les liquidités du patrimoine, il est seulement
réservé à l'objectif. Ce n'est donc ni une dépense du Budget ni un transfert (contrairement à un
apport Bourse). À ne pas confondre avec l'objectif d'épargne mensuel du Budget (params.objectif_epargne).

Un objectif peut être suivi par un tag (#turquie-2027) : les dépenses du Budget portant ce tag, datées
de `tag_depuis` ou après, sont prises sur l'argent mis de côté (moins les revenus portant le même tag,
un remboursement d'hôtel par exemple). Ce qui reste réservé (`reserve`) baisse d'autant, et
« Liquidités libres » ne compte plus deux fois le projet (une fois dépensé, une fois réservé).
L'avancement de l'épargne (`verse` sur `cible`) ne change pas : l'argent a bien été mis de côté.
"""
from datetime import date
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from config import aujourdhui
from database import db
from securite import utilisateur_courant
from schemas import ProjetIn, ProjetOut, VersementIn

router = APIRouter(prefix="/api/objectifs", tags=["objectifs"],
                   dependencies=[Depends(utilisateur_courant)])

PROJET_COLONNES = "id, nom, cible, date_limite, note, archive, tag, tag_depuis"
OPERATIONS_AFFICHEES = 50


def _d(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"))


def mois_jusqua(auj: date, limite: date) -> int:
    """Mois de versement d'ici la date limite, le mois en cours et celui de la date compris
    (le 11 novembre pour le 31 décembre : 2, novembre et décembre)."""
    return (limite.year - auj.year) * 12 + limite.month - auj.month + 1


def calculer(o: dict, versements: list, auj: date, depense: Decimal = Decimal(0), operations: list | None = None) -> dict:
    """Ajoute à un objectif son avancement, le rythme à tenir pour sa date limite et, s'il est suivi
    par un tag, ce que ses dépenses ont pris sur l'argent mis de côté (`depense`, net des remboursements)."""
    verse = sum((v["montant"] for v in versements), Decimal(0))
    depense = max(depense, Decimal(0)) if o.get("tag") else Decimal(0)
    cible = o["cible"]
    reste = max(cible - verse, Decimal(0))
    atteint = verse >= cible
    limite = o["date_limite"]
    en_cours = not atteint and not o["archive"]
    mois = mois_jusqua(auj, limite) if limite and en_cours and limite >= auj else None
    return {**o, "versements": versements, "verse": verse, "reste": reste, "atteint": atteint,
            "progression": float(verse / cible) if cible else 0.0,
            "mois_restants": mois, "par_mois": round(reste / mois, 2) if mois else None,
            "en_retard": bool(limite and en_cours and limite < auj),
            "depense": depense, "reserve": max(verse - depense, Decimal(0)),
            "depassement": max(depense - verse, Decimal(0)), "operations": operations or []}


def operations_taggees(c, tag: str, depuis: date) -> tuple:
    """(dépenses − revenus portant `tag` depuis `depuis`, les plus récentes opérations). Les dates
    du Budget sont du texte AAAA-MM-JJ : la comparaison de chaînes suit l'ordre des dates."""
    rows = c.execute("""SELECT 'depense' AS type, id, date, categorie AS nom, COALESCE(description,'') AS description, montant
                        FROM depenses WHERE tags @> ARRAY[%s]::text[] AND date >= %s
                        UNION ALL
                        SELECT 'revenu', id, date, COALESCE(source,''), COALESCE(description,''), montant
                        FROM revenus WHERE tags @> ARRAY[%s]::text[] AND date >= %s
                        ORDER BY date DESC, id DESC""", (tag, depuis.isoformat(), tag, depuis.isoformat())).fetchall()
    total = sum((Decimal(str(r["montant"])) * (1 if r["type"] == "depense" else -1) for r in rows), Decimal(0))
    return total.quantize(Decimal("0.01")), rows[:OPERATIONS_AFFICHEES]


def lire_objectifs(c, auj: date, projet_id: int | None = None) -> list:
    """Objectifs avec leurs versements (les plus récents d'abord). Les objectifs en cours d'abord,
    la date limite la plus proche en tête ; puis les archivés."""
    clause, params = (" WHERE id=%s", (projet_id,)) if projet_id is not None else ("", ())
    projets = c.execute(f"SELECT {PROJET_COLONNES} FROM objectifs{clause}", params).fetchall()
    clause = " WHERE objectif_id=%s" if projet_id is not None else ""
    par_projet = {}
    for v in c.execute("SELECT id, objectif_id, date_operation, montant, libelle FROM objectifs_versements"
                       f"{clause} ORDER BY date_operation DESC, id DESC", params).fetchall():
        par_projet.setdefault(v["objectif_id"], []).append(v)
    # Objectif qui provisionne une échéance (assurance, Aïd...) : cf. routes/carnet.py
    echeances = {r["objectif_id"]: r["id"] for r in c.execute(
        "SELECT id, objectif_id FROM echeances WHERE objectif_id IS NOT NULL").fetchall()}
    resultat = []
    for o in projets:
        o["echeance_id"] = echeances.get(o["id"])
        depense, operations = operations_taggees(c, o["tag"], o["tag_depuis"]) if o["tag"] else (Decimal(0), [])
        resultat.append(calculer(o, par_projet.get(o["id"], []), auj, depense, operations))
    return sorted(resultat, key=lambda o: (o["archive"], o["date_limite"] or date.max, o["id"]))


def _objectif(c, projet_id: int) -> dict:
    trouves = lire_objectifs(c, aujourdhui(), projet_id)
    if not trouves:
        raise HTTPException(404, "Objectif introuvable")
    return trouves[0]


def _valeurs(p: ProjetIn) -> tuple:
    # Tag sans date de départ : ses dépenses comptent à partir d'aujourd'hui (pas celles d'un
    # ancien voyage portant le même tag)
    depuis = (p.tag_depuis or aujourdhui()) if p.tag else None
    return (p.nom, _d(p.cible), p.date_limite, p.note, p.archive, p.tag, depuis)


@router.get("", response_model=List[ProjetOut])
def lister_objectifs():
    with db() as c:
        return lire_objectifs(c, aujourdhui())


@router.post("", response_model=ProjetOut, status_code=201)
def ajouter_objectif(p: ProjetIn):
    with db() as c:
        row = c.execute("""INSERT INTO objectifs (nom, cible, date_limite, note, archive, tag, tag_depuis)
                           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        _valeurs(p)).fetchone()
        return _objectif(c, row["id"])


@router.put("/{projet_id}", response_model=ProjetOut)
def modifier_objectif(projet_id: int, p: ProjetIn):
    with db() as c:
        if c.execute("""UPDATE objectifs SET nom=%s, cible=%s, date_limite=%s, note=%s, archive=%s, tag=%s, tag_depuis=%s
                        WHERE id=%s""",
                     (*_valeurs(p), projet_id)).rowcount == 0:
            raise HTTPException(404, "Objectif introuvable")
        return _objectif(c, projet_id)


@router.delete("/{projet_id}", status_code=204)
def supprimer_objectif(projet_id: int):
    with db() as c:
        if c.execute("DELETE FROM objectifs WHERE id=%s", (projet_id,)).rowcount == 0:
            raise HTTPException(404, "Objectif introuvable")


@router.post("/{projet_id}/versements", response_model=ProjetOut, status_code=201)
def ajouter_versement(projet_id: int, v: VersementIn):
    with db() as c:
        o = _objectif(c, projet_id)
        if o["verse"] + _d(v.montant) < 0:
            raise HTTPException(400, f"Tu ne peux pas reprendre plus que ce qui est mis de côté ({o['verse']} DH)")
        # Objectif suivi par un tag : ses dépenses sont déjà prises sur l'argent mis de côté
        if o["tag"] and v.montant < 0 and o["reserve"] + _d(v.montant) < 0:
            raise HTTPException(400, f"Il ne reste que {o['reserve']} DH dans l'enveloppe : "
                                     f"les dépenses #{o['tag']} sont déjà prises dessus")
        c.execute("INSERT INTO objectifs_versements (objectif_id, date_operation, montant, libelle) VALUES (%s,%s,%s,%s)",
                  (projet_id, v.date_operation, _d(v.montant), v.libelle))
        return _objectif(c, projet_id)


@router.delete("/versements/{versement_id}", status_code=204)
def supprimer_versement(versement_id: int):
    with db() as c:
        v = c.execute("SELECT objectif_id, montant FROM objectifs_versements WHERE id=%s", (versement_id,)).fetchone()
        if not v:
            raise HTTPException(404, "Versement introuvable")
        # Retirer un versement ne doit pas laisser un total négatif (argent repris entre-temps)
        if v["montant"] > 0 and _objectif(c, v["objectif_id"])["verse"] - v["montant"] < 0:
            raise HTTPException(400, "Supprime d'abord l'argent repris ensuite : le total deviendrait négatif")
        c.execute("DELETE FROM objectifs_versements WHERE id=%s", (versement_id,))
