# -*- coding: utf-8 -*-
"""
Objectifs d'épargne par projet : voyage, fonds d'urgence, voiture... Chacun a un montant cible et,
s'il le faut, une date limite. On y met de l'argent de côté par versements (ou on en reprend, avec
un montant négatif).

Un versement ne déplace pas d'argent : il reste dans les liquidités du patrimoine, il est seulement
réservé à l'objectif. Ce n'est donc ni une dépense du Budget ni un transfert (contrairement à un
apport Bourse). À ne pas confondre avec l'objectif d'épargne mensuel du Budget (params.objectif_epargne).
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

PROJET_COLONNES = "id, nom, cible, date_limite, note, archive"


def _d(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"))


def mois_jusqua(auj: date, limite: date) -> int:
    """Mois de versement d'ici la date limite, le mois en cours et celui de la date compris
    (le 11 novembre pour le 31 décembre : 2, novembre et décembre)."""
    return (limite.year - auj.year) * 12 + limite.month - auj.month + 1


def calculer(o: dict, versements: list, auj: date) -> dict:
    """Ajoute à un objectif son avancement et le rythme à tenir pour sa date limite."""
    verse = sum((v["montant"] for v in versements), Decimal(0))
    cible = o["cible"]
    reste = max(cible - verse, Decimal(0))
    atteint = verse >= cible
    limite = o["date_limite"]
    en_cours = not atteint and not o["archive"]
    mois = mois_jusqua(auj, limite) if limite and en_cours and limite >= auj else None
    return {**o, "versements": versements, "verse": verse, "reste": reste, "atteint": atteint,
            "progression": float(verse / cible) if cible else 0.0,
            "mois_restants": mois, "par_mois": round(reste / mois, 2) if mois else None,
            "en_retard": bool(limite and en_cours and limite < auj)}


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
    resultat = [calculer(o, par_projet.get(o["id"], []), auj) for o in projets]
    return sorted(resultat, key=lambda o: (o["archive"], o["date_limite"] or date.max, o["id"]))


def _objectif(c, projet_id: int) -> dict:
    trouves = lire_objectifs(c, aujourdhui(), projet_id)
    if not trouves:
        raise HTTPException(404, "Objectif introuvable")
    return trouves[0]


def _valeurs(p: ProjetIn) -> tuple:
    return (p.nom, _d(p.cible), p.date_limite, p.note, p.archive)


@router.get("", response_model=List[ProjetOut])
def lister_objectifs():
    with db() as c:
        return lire_objectifs(c, aujourdhui())


@router.post("", response_model=ProjetOut, status_code=201)
def ajouter_objectif(p: ProjetIn):
    with db() as c:
        row = c.execute("INSERT INTO objectifs (nom, cible, date_limite, note, archive) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                        _valeurs(p)).fetchone()
        return _objectif(c, row["id"])


@router.put("/{projet_id}", response_model=ProjetOut)
def modifier_objectif(projet_id: int, p: ProjetIn):
    with db() as c:
        if c.execute("UPDATE objectifs SET nom=%s, cible=%s, date_limite=%s, note=%s, archive=%s WHERE id=%s",
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
