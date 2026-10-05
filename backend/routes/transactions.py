# -*- coding: utf-8 -*-
"""Routes des transactions : dépenses et revenus (création, modification, suppression, liste)."""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from database import db
from securite import utilisateur_courant
from schemas import DepenseIn, RevenuIn

router = APIRouter(prefix="/api", tags=["transactions"],
                   dependencies=[Depends(utilisateur_courant)])

@router.post("/depenses")
def ajouter_depense(d: DepenseIn):
    with db() as c:
        row = c.execute("INSERT INTO depenses(date,categorie,description,montant) "
                        "VALUES(%s,%s,%s,%s) RETURNING id",
                        (d.date, d.categorie, d.description.strip(), d.montant)).fetchone()
    return {"id": row["id"]}

@router.put("/depenses/{did}")
def modifier_depense(did: int, d: DepenseIn):
    with db() as c:
        res = c.execute("UPDATE depenses SET date=%s, categorie=%s, description=%s, montant=%s WHERE id=%s",
                        (d.date, d.categorie, d.description.strip(), d.montant, did))
        if res.rowcount == 0:
            raise HTTPException(404, "Dépense introuvable")
    return {"ok": True}

@router.delete("/depenses/{did}")
def supprimer_depense(did: int):
    with db() as c:
        res = c.execute("DELETE FROM depenses WHERE id=%s", (did,))
        if res.rowcount == 0:
            raise HTTPException(404, "Dépense introuvable")
    return {"ok": True}

@router.post("/revenus")
def ajouter_revenu(r: RevenuIn):
    with db() as c:
        row = c.execute("INSERT INTO revenus(date,source,description,montant) VALUES(%s,%s,%s,%s) RETURNING id",
                        (r.date, r.source.strip(), r.description.strip(), r.montant)).fetchone()
    return {"id": row["id"]}

@router.put("/revenus/{rid}")
def modifier_revenu(rid: int, r: RevenuIn):
    with db() as c:
        res = c.execute("UPDATE revenus SET date=%s, source=%s, description=%s, montant=%s WHERE id=%s",
                        (r.date, r.source.strip(), r.description.strip(), r.montant, rid))
        if res.rowcount == 0:
            raise HTTPException(404, "Revenu introuvable")
    return {"ok": True}

@router.delete("/revenus/{rid}")
def supprimer_revenu(rid: int):
    with db() as c:
        res = c.execute("DELETE FROM revenus WHERE id=%s", (rid,))
        if res.rowcount == 0:
            raise HTTPException(404, "Revenu introuvable")
    return {"ok": True}

@router.get("/transactions")
def transactions(mois: str):
    try:
        datetime.strptime(mois, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "Format de mois attendu : AAAA-MM")
    like = mois + "-%"
    with db() as c:
        dep = c.execute("SELECT id,date,categorie,description,montant FROM depenses "
                        "WHERE date LIKE %s ORDER BY date DESC, id DESC", (like,)).fetchall()
        rev = c.execute("SELECT id,date,source,COALESCE(description,'') description,montant FROM revenus "
                        "WHERE date LIKE %s ORDER BY date DESC, id DESC", (like,)).fetchall()
    return {"depenses": dep, "revenus": rev}