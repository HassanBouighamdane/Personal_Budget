# -*- coding: utf-8 -*-
"""Routes de configuration : catégories, sources de revenus, objectif."""
from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from config import aujourdhui
from database import db
from securite import utilisateur_courant
from schemas import CategorieIn, ObjectifIn, NomIn

router = APIRouter(prefix="/api", tags=["configuration"],
                   dependencies=[Depends(utilisateur_courant)])

@router.get("/categories")
def lister_config():
    with db() as c:
        rows = c.execute("SELECT id,nom,budget,fixe FROM categories WHERE actif=1 ORDER BY nom").fetchall()
        src = c.execute("SELECT id,nom FROM sources_revenus WHERE actif=1 ORDER BY nom").fetchall()
        obj = c.execute("SELECT valeur FROM params WHERE cle='objectif_epargne'").fetchone()
    return {"categories": rows, "sources": src,
            "objectif_epargne": obj["valeur"]}

# ---- Catégories de dépense ----
def _mois_courant() -> str:
    return aujourdhui().strftime("%Y-%m")

def _fixer_budget(c, cid: int, mois: str, budget: float, fixe: bool):
    """Budget et « fixe » de la catégorie à partir de `mois` (les mois antérieurs gardent les
    leurs), puis recopie dans categories la valeur qui s'applique au mois en cours."""
    c.execute("""INSERT INTO budgets_historique(categorie_id, mois_debut, budget, fixe) VALUES(%s,%s,%s,%s)
                 ON CONFLICT (categorie_id, mois_debut) DO UPDATE SET budget=EXCLUDED.budget, fixe=EXCLUDED.fixe""",
              (cid, mois, budget, fixe))
    _synchroniser(c, cid)

def _synchroniser(c, cid: int):
    courant = c.execute("""SELECT budget, fixe FROM budgets_historique WHERE categorie_id=%s AND mois_debut <= %s
                           ORDER BY mois_debut DESC LIMIT 1""", (cid, _mois_courant())).fetchone()
    if courant:
        c.execute("UPDATE categories SET budget=%s, fixe=%s WHERE id=%s", (courant["budget"], courant["fixe"], cid))

@router.post("/categories")
def ajouter_categorie(cat: CategorieIn):
    """Nouvelle catégorie (ou réactivation) : son budget compte à partir du mois en cours,
    pas pour les mois passés."""
    with db() as c:
        row = c.execute("""INSERT INTO categories(nom,budget,fixe) VALUES(%s,%s,%s)
                           ON CONFLICT (nom) DO UPDATE SET actif=1 RETURNING id""",
                        (cat.nom.strip(), cat.budget, cat.fixe)).fetchone()
        _fixer_budget(c, row["id"], cat.a_partir_de or _mois_courant(), cat.budget, cat.fixe)
    return {"ok": True}

@router.put("/categories/{cid}")
def modifier_categorie(cid: int, cat: CategorieIn):
    nouveau_nom = cat.nom.strip()
    try:
        with db() as c:
            ancien = c.execute("SELECT nom FROM categories WHERE id=%s", (cid,)).fetchone()
            if not ancien:
                raise HTTPException(404, "Catégorie introuvable")
            c.execute("UPDATE categories SET nom=%s WHERE id=%s", (nouveau_nom, cid))
            _fixer_budget(c, cid, cat.a_partir_de or _mois_courant(), cat.budget, cat.fixe)
            if nouveau_nom != ancien["nom"]:
                # Sans cette mise à jour, les dépenses déjà saisies resteraient rattachées à
                # l'ancien nom et apparaîtraient comme une catégorie « fantôme » (budget 0).
                c.execute("UPDATE depenses SET categorie=%s WHERE categorie=%s", (nouveau_nom, ancien["nom"]))
    except UniqueViolation:
        # Le nom peut aussi être celui d'une catégorie désactivée (invisible dans la liste)
        raise HTTPException(409, f"La catégorie « {nouveau_nom} » existe déjà (éventuellement désactivée)")
    return {"ok": True}

@router.delete("/categories/{cid}")
def desactiver_categorie(cid: int):
    """La catégorie quitte les budgets à partir du mois en cours ; les mois passés la gardent."""
    with db() as c:
        row = c.execute("UPDATE categories SET actif=0 WHERE id=%s RETURNING fixe", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "Catégorie introuvable")
        _fixer_budget(c, cid, _mois_courant(), 0, row["fixe"])
    return {"ok": True}

@router.get("/categories/{cid}/historique")
def historique_budget(cid: int):
    """Budgets successifs de la catégorie, du plus récent au plus ancien."""
    with db() as c:
        return c.execute("""SELECT mois_debut, budget, fixe FROM budgets_historique WHERE categorie_id=%s
                            ORDER BY mois_debut DESC""", (cid,)).fetchall()

@router.delete("/categories/{cid}/historique/{mois}")
def supprimer_budget_mois(cid: int, mois: str):
    """Retire un changement de budget (saisi par erreur) : le budget précédent s'applique à nouveau."""
    with db() as c:
        if c.execute("SELECT COUNT(*) n FROM budgets_historique WHERE categorie_id=%s", (cid,)).fetchone()["n"] <= 1:
            raise HTTPException(400, "Impossible de retirer le seul budget de la catégorie")
        if c.execute("DELETE FROM budgets_historique WHERE categorie_id=%s AND mois_debut=%s",
                     (cid, mois)).rowcount == 0:
            raise HTTPException(404, "Aucun budget à ce mois")
        _synchroniser(c, cid)
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
    nouveau_nom = s.nom.strip()
    try:
        with db() as c:
            ancien = c.execute("SELECT nom FROM sources_revenus WHERE id=%s", (sid,)).fetchone()
            if not ancien:
                raise HTTPException(404, "Source introuvable")
            c.execute("UPDATE sources_revenus SET nom=%s WHERE id=%s", (nouveau_nom, sid))
            if nouveau_nom != ancien["nom"]:
                c.execute("UPDATE revenus SET source=%s WHERE source=%s", (nouveau_nom, ancien["nom"]))
    except UniqueViolation:
        raise HTTPException(409, f"La source « {nouveau_nom} » existe déjà (éventuellement retirée)")
    return {"ok": True}

@router.delete("/sources/{sid}")
def desactiver_source(sid: int):
    with db() as c:
        res = c.execute("UPDATE sources_revenus SET actif=0 WHERE id=%s", (sid,))
        if res.rowcount == 0:
            raise HTTPException(404, "Source introuvable")
    return {"ok": True}
