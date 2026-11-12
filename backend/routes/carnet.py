# -*- coding: utf-8 -*-
"""
Module Carnet — dettes et prêts, échéances.

Dettes et prêts : de l'argent prêté (on me doit) ou emprunté (je dois), remboursé en une ou
plusieurs fois. Ce sont des transferts : ils ne se saisissent pas dans le Budget, sinon un prêt
passerait pour une dépense et son remboursement pour un revenu.

Échéances : tout ce qui a une date limite (CIN, passeport, assurance, visite technique,
vignette, garanties). Une échéance récurrente se reporte d'une période une fois traitée.

Provision : une échéance qui coûte (assurance, Aïd al-Adha, rentrée scolaire) peut avoir un montant
et un objectif d'épargne du même montant, pour la même date (`objectif_id`). L'objectif donne ce qu'il
faut mettre de côté chaque mois : la dépense ne tombe plus d'un coup sur un seul mois. Quand
l'échéance récurrente est reportée, l'objectif est archivé (avec ce qui a été mis de côté) et un
nouveau prend la période suivante.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from config import aujourdhui
from database import db
from securite import utilisateur_courant
from schemas import DetteIn, DetteOut, EcheanceIn, EcheanceOut, RemboursementIn

router = APIRouter(prefix="/api/carnet", tags=["carnet"],
                   dependencies=[Depends(utilisateur_courant)])


def _d(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"))


# ---------------------------------------------------------------- dettes et prêts
DETTE_COLONNES = "id, sens, personne, montant, date_operation, echeance, libelle"


def lire_dettes(c, dette_id: int | None = None) -> list:
    """Dettes avec leurs remboursements : celles en cours d'abord (échéance la plus proche en
    tête), puis les soldées (dernier remboursement le plus récent en tête)."""
    clause, params = (" WHERE id=%s", (dette_id,)) if dette_id is not None else ("", ())
    dettes = c.execute(f"SELECT {DETTE_COLONNES} FROM dettes{clause}", params).fetchall()
    clause = " WHERE dette_id=%s" if dette_id is not None else ""
    par_dette = {}
    for r in c.execute("SELECT id, dette_id, date_operation, montant, libelle FROM dettes_remboursements"
                       f"{clause} ORDER BY date_operation DESC, id DESC", params).fetchall():
        par_dette.setdefault(r["dette_id"], []).append(r)
    for d in dettes:
        d["remboursements"] = par_dette.get(d["id"], [])
        d["rembourse"] = sum((r["montant"] for r in d["remboursements"]), Decimal(0))
        d["reste"] = d["montant"] - d["rembourse"]

    def ordre(d):
        if d["reste"] > 0:
            return (0, d["echeance"] or date.max, -d["date_operation"].toordinal(), -d["id"])
        dernier = d["remboursements"][0]["date_operation"] if d["remboursements"] else d["date_operation"]
        return (1, date.min, -dernier.toordinal(), -d["id"])
    return sorted(dettes, key=ordre)


def _dette(c, dette_id: int) -> dict:
    dettes = lire_dettes(c, dette_id)
    if not dettes:
        raise HTTPException(404, "Dette introuvable")
    return dettes[0]


def _valeurs_dette(d: DetteIn) -> tuple:
    return (d.sens, d.personne, _d(d.montant), d.date_operation, d.echeance, d.libelle.strip())


@router.get("/dettes", response_model=List[DetteOut])
def lister_dettes():
    with db() as c:
        return lire_dettes(c)


@router.post("/dettes", response_model=DetteOut, status_code=201)
def ajouter_dette(d: DetteIn):
    with db() as c:
        row = c.execute("""INSERT INTO dettes (sens, personne, montant, date_operation, echeance, libelle)
                           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""", _valeurs_dette(d)).fetchone()
        return _dette(c, row["id"])


@router.put("/dettes/{dette_id}", response_model=DetteOut)
def modifier_dette(dette_id: int, d: DetteIn):
    with db() as c:
        actuelle = _dette(c, dette_id)
        if _d(d.montant) < actuelle["rembourse"]:
            raise HTTPException(400, f"Le montant ne peut pas être inférieur à ce qui est déjà remboursé "
                                     f"({actuelle['rembourse']} DH)")
        c.execute("""UPDATE dettes SET sens=%s, personne=%s, montant=%s, date_operation=%s, echeance=%s, libelle=%s
                     WHERE id=%s""", (*_valeurs_dette(d), dette_id))
        return _dette(c, dette_id)


@router.delete("/dettes/{dette_id}", status_code=204)
def supprimer_dette(dette_id: int):
    with db() as c:
        if c.execute("DELETE FROM dettes WHERE id=%s", (dette_id,)).rowcount == 0:
            raise HTTPException(404, "Dette introuvable")


@router.post("/dettes/{dette_id}/remboursements", response_model=DetteOut, status_code=201)
def ajouter_remboursement(dette_id: int, r: RemboursementIn):
    with db() as c:
        dette = _dette(c, dette_id)
        if _d(r.montant) > dette["reste"]:
            raise HTTPException(400, f"Le remboursement dépasse le reste dû ({dette['reste']} DH)")
        if r.date_operation < dette["date_operation"]:
            raise HTTPException(400, "Un remboursement ne peut pas précéder la date du prêt")
        c.execute("""INSERT INTO dettes_remboursements (dette_id, date_operation, montant, libelle)
                     VALUES (%s,%s,%s,%s)""", (dette_id, r.date_operation, _d(r.montant), r.libelle.strip()))
        return _dette(c, dette_id)


@router.delete("/remboursements/{remboursement_id}", status_code=204)
def supprimer_remboursement(remboursement_id: int):
    with db() as c:
        if c.execute("DELETE FROM dettes_remboursements WHERE id=%s", (remboursement_id,)).rowcount == 0:
            raise HTTPException(404, "Remboursement introuvable")


# ---------------------------------------------------------------- échéances
ECHEANCE_COLONNES = "id, titre, categorie, date_echeance, rappel_jours, recurrence_mois, note, montant, objectif_id"


def ajouter_mois(d: date, n: int) -> date:
    """`d` décalée de `n` mois ; le 31 d'un mois plus court devient son dernier jour."""
    total = d.month - 1 + n
    annee, mois = d.year + total // 12, total % 12 + 1
    return date(annee, mois, min(d.day, calendar.monthrange(annee, mois)[1]))


def _avec_delai(e: dict, auj: date) -> dict:
    jours = (e["date_echeance"] - auj).days
    return {**e, "jours_restants": jours, "a_rappeler": jours <= e["rappel_jours"]}


def lire_echeances(c, auj: date) -> list:
    """Échéances de la plus proche (ou la plus en retard) à la plus lointaine."""
    rows = c.execute(f"SELECT {ECHEANCE_COLONNES} FROM echeances ORDER BY date_echeance, id").fetchall()
    return [_avec_delai(e, auj) for e in rows]


def _avec_provisions(c, echeances: list, auj: date) -> list:
    """Ajoute à chaque échéance provisionnée l'état de son objectif (mis de côté, reste, par mois)."""
    from routes.objectifs import lire_objectifs   # import local : objectifs n'a pas à charger le Carnet
    if not any(e["objectif_id"] for e in echeances):
        return [{**e, "provision": None} for e in echeances]
    objectifs = {o["id"]: o for o in lire_objectifs(c, auj)}
    resultat = []
    for e in echeances:
        o = objectifs.get(e["objectif_id"])
        resultat.append({**e, "provision": o and {"objectif_id": o["id"], "verse": o["verse"], "cible": o["cible"],
                                                  "reste": o["reste"], "par_mois": o["par_mois"], "archive": o["archive"]}})
    return resultat


def _echeance(c, echeance_id: int) -> dict:
    row = c.execute(f"SELECT {ECHEANCE_COLONNES} FROM echeances WHERE id=%s", (echeance_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Échéance introuvable")
    auj = aujourdhui()
    return _avec_provisions(c, [_avec_delai(row, auj)], auj)[0]


def _valeurs_echeance(e: EcheanceIn) -> tuple:
    return (e.titre, e.categorie.strip(), e.date_echeance, e.rappel_jours, e.recurrence_mois, e.note.strip(),
            _d(e.montant) if e.montant else None)


def _nouvel_objectif(c, e: dict, tag: str | None = None, tag_depuis: date | None = None) -> int:
    return c.execute("""INSERT INTO objectifs (nom, cible, date_limite, note, tag, tag_depuis)
                        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                     (e["titre"][:100], e["montant"], e["date_echeance"],
                      f"Provision pour l'échéance « {e['titre']} »", tag, tag_depuis)).fetchone()["id"]


def _detacher_objectif(c, objectif_id: int):
    """L'échéance ne provisionne plus : son objectif est supprimé s'il est vide, gardé sinon (l'argent
    mis de côté reste visible dans Objectifs, à reprendre ou à archiver)."""
    c.execute("""DELETE FROM objectifs WHERE id=%s
                 AND NOT EXISTS (SELECT 1 FROM objectifs_versements WHERE objectif_id=%s)""", (objectif_id, objectif_id))


def _synchroniser_provision(c, e: dict, provisionner: bool):
    """Crée, met à jour ou retire l'objectif qui provisionne l'échéance `e` (ligne de la base)."""
    if provisionner and e["montant"]:
        if e["objectif_id"]:
            c.execute("UPDATE objectifs SET nom=%s, cible=%s, date_limite=%s WHERE id=%s",
                      (e["titre"][:100], e["montant"], e["date_echeance"], e["objectif_id"]))
        else:
            c.execute("UPDATE echeances SET objectif_id=%s WHERE id=%s", (_nouvel_objectif(c, e), e["id"]))
    elif e["objectif_id"]:
        c.execute("UPDATE echeances SET objectif_id=NULL WHERE id=%s", (e["id"],))
        _detacher_objectif(c, e["objectif_id"])


@router.get("/echeances", response_model=List[EcheanceOut])
def lister_echeances():
    auj = aujourdhui()
    with db() as c:
        return _avec_provisions(c, lire_echeances(c, auj), auj)


@router.post("/echeances", response_model=EcheanceOut, status_code=201)
def ajouter_echeance(e: EcheanceIn):
    with db() as c:
        row = c.execute(f"""INSERT INTO echeances (titre, categorie, date_echeance, rappel_jours, recurrence_mois, note, montant)
                            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING {ECHEANCE_COLONNES}""", _valeurs_echeance(e)).fetchone()
        _synchroniser_provision(c, row, e.provisionner)
        return _echeance(c, row["id"])


@router.put("/echeances/{echeance_id}", response_model=EcheanceOut)
def modifier_echeance(echeance_id: int, e: EcheanceIn):
    with db() as c:
        row = c.execute(f"""UPDATE echeances SET titre=%s, categorie=%s, date_echeance=%s, rappel_jours=%s,
                                   recurrence_mois=%s, note=%s, montant=%s
                            WHERE id=%s RETURNING {ECHEANCE_COLONNES}""", (*_valeurs_echeance(e), echeance_id)).fetchone()
        if not row:
            raise HTTPException(404, "Échéance introuvable")
        _synchroniser_provision(c, row, e.provisionner)
        return _echeance(c, echeance_id)


@router.delete("/echeances/{echeance_id}", status_code=204)
def supprimer_echeance(echeance_id: int):
    with db() as c:
        row = c.execute("DELETE FROM echeances WHERE id=%s RETURNING objectif_id", (echeance_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Échéance introuvable")
        if row["objectif_id"]:
            _detacher_objectif(c, row["objectif_id"])


@router.post("/echeances/{echeance_id}/reporter", response_model=EcheanceOut)
def reporter_echeance(echeance_id: int):
    """Échéance récurrente traitée : sa date avance d'une période (de sa date prévue, pas d'aujourd'hui).
    Son objectif de provision passe à la période suivante : archivé avec ce qui a été mis de côté
    (l'argent a servi), puis remplacé par un nouveau ; un objectif encore vide est simplement décalé."""
    with db() as c:
        e = c.execute(f"SELECT {ECHEANCE_COLONNES} FROM echeances WHERE id=%s", (echeance_id,)).fetchone()
        if not e:
            raise HTTPException(404, "Échéance introuvable")
        if not e["recurrence_mois"]:
            raise HTTPException(400, "Cette échéance n'est pas récurrente : modifie sa date ou supprime-la")
        row = c.execute(f"UPDATE echeances SET date_echeance=%s WHERE id=%s RETURNING {ECHEANCE_COLONNES}",
                        (ajouter_mois(e["date_echeance"], e["recurrence_mois"]), echeance_id)).fetchone()
        if row["objectif_id"]:
            o = c.execute("""SELECT archive, tag, EXISTS (SELECT 1 FROM objectifs_versements WHERE objectif_id=o.id) verse
                             FROM objectifs o WHERE id=%s""", (row["objectif_id"],)).fetchone()
            if o and o["verse"]:
                c.execute("UPDATE objectifs SET archive=true WHERE id=%s", (row["objectif_id"],))
                # Le tag suit : les dépenses de la nouvelle période comptent à partir de demain
                nouveau = _nouvel_objectif(c, row, o["tag"], aujourdhui() + timedelta(days=1) if o["tag"] else None)
                c.execute("UPDATE echeances SET objectif_id=%s WHERE id=%s", (nouveau, echeance_id))
            else:
                _synchroniser_provision(c, row, True)
        return _echeance(c, echeance_id)
