# -*- coding: utf-8 -*-
"""Routes de configuration : catégories, sources de revenus, types de paiement, objectif."""
from fastapi import APIRouter, Depends

from database import db
from securite import utilisateur_courant
from schemas import CategorieIn, ObjectifIn, NomIn

router = APIRouter(prefix="/api", tags=["configuration"],
                   dependencies=[Depends(utilisateur_courant)])

@router.get("/categories")
def lister_config():
    with db() as c:
        rows = c.execute("SELECT id,nom,budget FROM categories WHERE actif=1 ORDER BY nom").fetchall()
        src = c.execute("SELECT id,nom FROM sources_revenus WHERE actif=1 ORDER BY nom").fetchall()
        pay = c.execute("SELECT id,nom FROM paiements WHERE actif=1 ORDER BY id").fetchall()
        obj = c.execute("SELECT valeur FROM params WHERE cle='objectif_epargne'").fetchone()
    return {"categories": rows, "sources": src, "paiements": pay,
            "objectif_epargne": obj["valeur"]}

# ---- Catégories de dépense ----
@router.post("/categories")
def ajouter_categorie(cat: CategorieIn):
    with db() as c:
        c.execute("""INSERT INTO categories(nom,budget) VALUES(%s,%s)
                     ON CONFLICT (nom) DO UPDATE SET actif=1, budget=EXCLUDED.budget""",
                  (cat.nom.strip(), cat.budget))
    return {"ok": True}

@router.put("/categories/{cid}")
def modifier_categorie(cid: int, cat: CategorieIn):
    with db() as c:
        c.execute("UPDATE categories SET nom=%s, budget=%s WHERE id=%s",
                  (cat.nom.strip(), cat.budget, cid))
    return {"ok": True}

@router.delete("/categories/{cid}")
def desactiver_categorie(cid: int):
    with db() as c:
        c.execute("UPDATE categories SET actif=0 WHERE id=%s", (cid,))
    return {"ok": True}

# ---- Objectif d'épargne ----
@router.put("/objectif")
def modifier_objectif(o: ObjectifIn):
    with db() as c:
        c.execute("UPDATE params SET valeur=%s WHERE cle='objectif_epargne'", (o.objectif,))
    return {"ok": True}

# ---- Sources de revenus ----
@router.post("/sources")
def ajouter_source(s: NomIn):
    with db() as c:
        c.execute("""INSERT INTO sources_revenus(nom) VALUES(%s)
                     ON CONFLICT (nom) DO UPDATE SET actif=1""", (s.nom.strip(),))
    return {"ok": True}

@router.put("/sources/{sid}")
def modifier_source(sid: int, s: NomIn):
    with db() as c:
        c.execute("UPDATE sources_revenus SET nom=%s WHERE id=%s", (s.nom.strip(), sid))
    return {"ok": True}

@router.delete("/sources/{sid}")
def desactiver_source(sid: int):
    with db() as c:
        c.execute("UPDATE sources_revenus SET actif=0 WHERE id=%s", (sid,))
    return {"ok": True}

# ---- Types de paiement ----
@router.post("/paiements")
def ajouter_paiement(p: NomIn):
    with db() as c:
        c.execute("""INSERT INTO paiements(nom) VALUES(%s)
                     ON CONFLICT (nom) DO UPDATE SET actif=1""", (p.nom.strip(),))
    return {"ok": True}

@router.put("/paiements/{pid}")
def modifier_paiement(pid: int, p: NomIn):
    with db() as c:
        c.execute("UPDATE paiements SET nom=%s WHERE id=%s", (p.nom.strip(), pid))
    return {"ok": True}

@router.delete("/paiements/{pid}")
def desactiver_paiement(pid: int):
    with db() as c:
        c.execute("UPDATE paiements SET actif=0 WHERE id=%s", (pid,))
    return {"ok": True}