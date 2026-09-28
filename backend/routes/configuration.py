# -*- coding: utf-8 -*-
"""Routes de configuration : catégories, sources de revenus, objectif."""
from fastapi import APIRouter, Depends, HTTPException

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
        obj = c.execute("SELECT valeur FROM params WHERE cle='objectif_epargne'").fetchone()
    return {"categories": rows, "sources": src,
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
        ancien = c.execute("SELECT nom FROM categories WHERE id=%s", (cid,)).fetchone()
        if not ancien:
            raise HTTPException(404, "Catégorie introuvable")
        nouveau_nom = cat.nom.strip()
        c.execute("UPDATE categories SET nom=%s, budget=%s WHERE id=%s", (nouveau_nom, cat.budget, cid))
        if nouveau_nom != ancien["nom"]:
            # Sans cette mise à jour, les dépenses déjà saisies resteraient rattachées à
            # l'ancien nom et apparaîtraient comme une catégorie « fantôme » (budget 0).
            c.execute("UPDATE depenses SET categorie=%s WHERE categorie=%s", (nouveau_nom, ancien["nom"]))
    return {"ok": True}

@router.delete("/categories/{cid}")
def desactiver_categorie(cid: int):
    with db() as c:
        res = c.execute("UPDATE categories SET actif=0 WHERE id=%s", (cid,))
        if res.rowcount == 0:
            raise HTTPException(404, "Catégorie introuvable")
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
        ancien = c.execute("SELECT nom FROM sources_revenus WHERE id=%s", (sid,)).fetchone()
        if not ancien:
            raise HTTPException(404, "Source introuvable")
        nouveau_nom = s.nom.strip()
        c.execute("UPDATE sources_revenus SET nom=%s WHERE id=%s", (nouveau_nom, sid))
        if nouveau_nom != ancien["nom"]:
            c.execute("UPDATE revenus SET source=%s WHERE source=%s", (nouveau_nom, ancien["nom"]))
    return {"ok": True}

@router.delete("/sources/{sid}")
def desactiver_source(sid: int):
    with db() as c:
        res = c.execute("UPDATE sources_revenus SET actif=0 WHERE id=%s", (sid,))
        if res.rowcount == 0:
            raise HTTPException(404, "Source introuvable")
    return {"ok": True}

