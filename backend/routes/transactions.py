# -*- coding: utf-8 -*-
"""Routes des transactions : dépenses et revenus (création, suppression, liste)."""
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
        row = c.execute("INSERT INTO revenus(date,source,montant) VALUES(%s,%s,%s) RETURNING id",
                        (r.date, r.source.strip(), r.montant)).fetchone()
    return {"id": row["id"]}

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
        rev = c.execute("SELECT id,date,source,montant FROM revenus "
                        "WHERE date LIKE %s ORDER BY date DESC, id DESC", (like,)).fetchall()
    return {"depenses": dep, "revenus": rev}