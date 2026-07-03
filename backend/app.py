# -*- coding: utf-8 -*-
"""
Mon Budget — Backend API (FastAPI + SQLite)
===========================================
API REST pure : aucun HTML dans ce fichier.
Le frontend (../frontend) est servi en fichiers statiques,
et peut aussi être hébergé ailleurs grâce au CORS activé.

Installation :  pip install fastapi uvicorn
Lancement    :  python app.py   (depuis le dossier backend/)
API          :  http://localhost:8500/api/...
Interface    :  http://localhost:8500/
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "budget.db"
FRONT_DIR = BASE_DIR.parent / "frontend"

CATEGORIES_DEFAUT = [
    ("Alimentation & Courses", 2500), ("Restaurants & Cafés", 800),
    ("Transport & Carburant", 1200), ("Loyer / Crédit logement", 4000),
    ("Factures & Abonnements", 900), ("Santé & Pharmacie", 500),
    ("Vêtements & Soins", 500), ("Loisirs & Sorties", 600),
    ("Famille & Cadeaux", 700), ("Éducation & Formation", 400),
    ("Imprévus & Divers", 500),
]
PAIEMENTS = ["Espèces", "Carte", "Virement", "Mobile"]

# ------------------------------------------------------------------ DB
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL,
            budget REAL NOT NULL DEFAULT 0,
            actif INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS depenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            categorie TEXT NOT NULL,
            description TEXT DEFAULT '',
            montant REAL NOT NULL,
            paiement TEXT DEFAULT 'Espèces',
            cree_le TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS revenus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            source TEXT DEFAULT '',
            montant REAL NOT NULL,
            cree_le TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS params (
            cle TEXT PRIMARY KEY,
            valeur REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources_revenus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL,
            actif INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS paiements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL,
            actif INTEGER NOT NULL DEFAULT 1
        );
        """)
        if c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            c.executemany("INSERT INTO categories(nom,budget) VALUES(?,?)", CATEGORIES_DEFAUT)
        if c.execute("SELECT COUNT(*) FROM sources_revenus").fetchone()[0] == 0:
            c.executemany("INSERT INTO sources_revenus(nom) VALUES(?)",
                          [("Salaire",), ("Prime",), ("Freelance",), ("Remboursement",)])
        if c.execute("SELECT COUNT(*) FROM paiements").fetchone()[0] == 0:
            c.executemany("INSERT INTO paiements(nom) VALUES(?)",
                          [("Espèces",), ("Carte",), ("Virement",), ("Mobile",)])
        c.execute("INSERT OR IGNORE INTO params(cle,valeur) VALUES('objectif_epargne',2000)")

init_db()
app = FastAPI(title="Mon Budget — API", version="1.0")

# CORS : permet à un frontend hébergé ailleurs (Next.js, autre port...) d'appeler l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # usage local ; restreindre si exposé sur un réseau partagé
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ Modèles
class DepenseIn(BaseModel):
    date: str
    categorie: str
    description: str = ""
    montant: float = Field(gt=0)
    paiement: str = "Espèces"

class RevenuIn(BaseModel):
    date: str
    source: str = ""
    montant: float = Field(gt=0)

class CategorieIn(BaseModel):
    nom: str
    budget: float = Field(ge=0)

class ObjectifIn(BaseModel):
    objectif: float = Field(ge=0)

# ------------------------------------------------------------------ Endpoints
@app.post("/api/depenses")
def ajouter_depense(d: DepenseIn):
    with db() as c:
        cur = c.execute("INSERT INTO depenses(date,categorie,description,montant,paiement) VALUES(?,?,?,?,?)",
                        (d.date, d.categorie, d.description.strip(), d.montant, d.paiement))
        return {"id": cur.lastrowid}

@app.delete("/api/depenses/{did}")
def supprimer_depense(did: int):
    with db() as c:
        c.execute("DELETE FROM depenses WHERE id=?", (did,))
    return {"ok": True}

@app.post("/api/revenus")
def ajouter_revenu(r: RevenuIn):
    with db() as c:
        cur = c.execute("INSERT INTO revenus(date,source,montant) VALUES(?,?,?)",
                        (r.date, r.source.strip(), r.montant))
        return {"id": cur.lastrowid}

@app.delete("/api/revenus/{rid}")
def supprimer_revenu(rid: int):
    with db() as c:
        c.execute("DELETE FROM revenus WHERE id=?", (rid,))
    return {"ok": True}

class NomIn(BaseModel):
    nom: str = Field(min_length=1)

@app.get("/api/categories")
def lister_config():
    """Configuration complète : catégories, sources de revenus, types de paiement, objectif."""
    with db() as c:
        rows = c.execute("SELECT id,nom,budget FROM categories WHERE actif=1 ORDER BY nom").fetchall()
        src = c.execute("SELECT id,nom FROM sources_revenus WHERE actif=1 ORDER BY nom").fetchall()
        pay = c.execute("SELECT id,nom FROM paiements WHERE actif=1 ORDER BY id").fetchall()
        obj = c.execute("SELECT valeur FROM params WHERE cle='objectif_epargne'").fetchone()
    return {"categories": [dict(r) for r in rows],
            "sources": [dict(r) for r in src],
            "paiements": [dict(r) for r in pay],
            "objectif_epargne": obj["valeur"]}

# ---- Sources de revenus (configurables) ----
@app.post("/api/sources")
def ajouter_source(s: NomIn):
    with db() as c:
        try:
            c.execute("INSERT INTO sources_revenus(nom) VALUES(?)", (s.nom.strip(),))
        except sqlite3.IntegrityError:
            c.execute("UPDATE sources_revenus SET actif=1 WHERE nom=?", (s.nom.strip(),))
    return {"ok": True}

@app.put("/api/sources/{sid}")
def modifier_source(sid: int, s: NomIn):
    with db() as c:
        c.execute("UPDATE sources_revenus SET nom=? WHERE id=?", (s.nom.strip(), sid))
    return {"ok": True}

@app.delete("/api/sources/{sid}")
def desactiver_source(sid: int):
    with db() as c:
        c.execute("UPDATE sources_revenus SET actif=0 WHERE id=?", (sid,))
    return {"ok": True}

# ---- Types de paiement (configurables) ----
@app.post("/api/paiements")
def ajouter_paiement(p: NomIn):
    with db() as c:
        try:
            c.execute("INSERT INTO paiements(nom) VALUES(?)", (p.nom.strip(),))
        except sqlite3.IntegrityError:
            c.execute("UPDATE paiements SET actif=1 WHERE nom=?", (p.nom.strip(),))
    return {"ok": True}

@app.put("/api/paiements/{pid}")
def modifier_paiement(pid: int, p: NomIn):
    with db() as c:
        c.execute("UPDATE paiements SET nom=? WHERE id=?", (p.nom.strip(), pid))
    return {"ok": True}

@app.delete("/api/paiements/{pid}")
def desactiver_paiement(pid: int):
    with db() as c:
        c.execute("UPDATE paiements SET actif=0 WHERE id=?", (pid,))
    return {"ok": True}

@app.post("/api/categories")
def ajouter_categorie(cat: CategorieIn):
    with db() as c:
        try:
            c.execute("INSERT INTO categories(nom,budget) VALUES(?,?)", (cat.nom.strip(), cat.budget))
        except sqlite3.IntegrityError:
            c.execute("UPDATE categories SET actif=1, budget=? WHERE nom=?", (cat.budget, cat.nom.strip()))
    return {"ok": True}

@app.put("/api/categories/{cid}")
def modifier_categorie(cid: int, cat: CategorieIn):
    with db() as c:
        c.execute("UPDATE categories SET nom=?, budget=? WHERE id=?", (cat.nom.strip(), cat.budget, cid))
    return {"ok": True}

@app.delete("/api/categories/{cid}")
def desactiver_categorie(cid: int):
    with db() as c:
        c.execute("UPDATE categories SET actif=0 WHERE id=?", (cid,))
    return {"ok": True}

@app.put("/api/objectif")
def modifier_objectif(o: ObjectifIn):
    with db() as c:
        c.execute("UPDATE params SET valeur=? WHERE cle='objectif_epargne'", (o.objectif,))
    return {"ok": True}

@app.get("/api/transactions")
def transactions(mois: str):
    _valider_mois(mois)
    like = mois + "-%"
    with db() as c:
        dep = c.execute("SELECT id,date,categorie,description,montant,paiement FROM depenses "
                        "WHERE date LIKE ? ORDER BY date DESC, id DESC", (like,)).fetchall()
        rev = c.execute("SELECT id,date,source,montant FROM revenus "
                        "WHERE date LIKE ? ORDER BY date DESC, id DESC", (like,)).fetchall()
    return {"depenses": [dict(r) for r in dep], "revenus": [dict(r) for r in rev]}

@app.get("/api/resume")
def resume(mois: str):
    _valider_mois(mois)
    like = mois + "-%"
    annee, m = int(mois[:4]), int(mois[5:])
    nb_jours = (date(annee + (m == 12), (m % 12) + 1, 1) - date(annee, m, 1)).days

    with db() as c:
        total_dep = c.execute("SELECT COALESCE(SUM(montant),0) t FROM depenses WHERE date LIKE ?", (like,)).fetchone()["t"]
        total_rev = c.execute("SELECT COALESCE(SUM(montant),0) t FROM revenus WHERE date LIKE ?", (like,)).fetchone()["t"]
        obj = c.execute("SELECT valeur FROM params WHERE cle='objectif_epargne'").fetchone()["valeur"]

        cats = c.execute("SELECT nom,budget FROM categories WHERE actif=1").fetchall()
        reel = dict(c.execute("SELECT categorie, SUM(montant) FROM depenses WHERE date LIKE ? GROUP BY categorie",
                              (like,)).fetchall())
        budget_vs = sorted(
            [{"cat": r["nom"], "budget": r["budget"], "reel": round(reel.get(r["nom"], 0), 2),
              "pct": round(reel.get(r["nom"], 0) / r["budget"] * 100, 1) if r["budget"] else 0}
             for r in cats],
            key=lambda x: x["pct"], reverse=True)
        noms_actifs = {r["nom"] for r in cats}
        for nom, v in reel.items():
            if nom not in noms_actifs:
                budget_vs.append({"cat": nom, "budget": 0, "reel": round(v, 2), "pct": 0})

        jours = dict(c.execute("SELECT CAST(substr(date,9,2) AS INT), SUM(montant) FROM depenses "
                               "WHERE date LIKE ? GROUP BY 1", (like,)).fetchall())
        cumul, s = [], 0.0
        for j in range(1, nb_jours + 1):
            s += jours.get(j, 0)
            cumul.append(round(s, 2))

        donut = c.execute("SELECT categorie, SUM(montant) t FROM depenses WHERE date LIKE ? "
                          "GROUP BY categorie ORDER BY t DESC", (like,)).fetchall()

        evo = c.execute("""
            SELECT m, SUM(dep) dep, SUM(rev) rev FROM (
                SELECT substr(date,1,7) m, montant dep, 0 rev FROM depenses
                UNION ALL
                SELECT substr(date,1,7) m, 0, montant FROM revenus
            ) WHERE m <= ? GROUP BY m ORDER BY m DESC LIMIT 6
        """, (mois,)).fetchall()
        evo = sorted([dict(r) for r in evo], key=lambda r: r["m"])

        top = c.execute("SELECT date,categorie,description,montant FROM depenses WHERE date LIKE ? "
                        "ORDER BY montant DESC LIMIT 10", (like,)).fetchall()

    epargne = total_rev - total_dep
    budget_total = sum(r["budget"] for r in cats)

    # Mois précédent (pour les badges de tendance)
    pa, pm = (annee - 1, 12) if m == 1 else (annee, m - 1)
    prec_like = f"{pa:04d}-{pm:02d}-%"
    with db() as c:
        dep_prec = c.execute("SELECT COALESCE(SUM(montant),0) t FROM depenses WHERE date LIKE ?", (prec_like,)).fetchone()["t"]
        rev_prec = c.execute("SELECT COALESCE(SUM(montant),0) t FROM revenus WHERE date LIKE ?", (prec_like,)).fetchone()["t"]

    # Projection de fin de mois (uniquement pour le mois en cours)
    auj = date.today()
    projection = None
    if mois == auj.strftime("%Y-%m") and auj.day > 0:
        projection = round(total_dep / auj.day * nb_jours, 2)

    return {
        "mois": mois, "nb_jours": nb_jours,
        "total_depenses": round(total_dep, 2), "total_revenus": round(total_rev, 2),
        "epargne": round(epargne, 2),
        "taux_epargne": round(epargne / total_rev * 100, 1) if total_rev else 0,
        "objectif_epargne": obj, "budget_total": budget_total,
        "reste_budget": round(budget_total - total_dep, 2),
        "depenses_mois_precedent": round(dep_prec, 2),
        "revenus_mois_precedent": round(rev_prec, 2),
        "projection_fin_mois": projection,
        "budget_vs_reel": budget_vs, "cumul_quotidien": cumul,
        "donut": [{"cat": r["categorie"], "montant": round(r["t"], 2)} for r in donut],
        "evolution": evo,
        "top": [dict(r) for r in top],
    }

@app.get("/api/resume_annuel")
def resume_annuel(annee: int):
    """Vue annuelle : totaux par mois, KPIs avancés, grille catégories × mois."""
    like = f"{annee:04d}-%"
    with db() as c:
        dep_m = dict(c.execute("SELECT CAST(substr(date,6,2) AS INT), SUM(montant) FROM depenses "
                               "WHERE date LIKE ? GROUP BY 1", (like,)).fetchall())
        rev_m = dict(c.execute("SELECT CAST(substr(date,6,2) AS INT), SUM(montant) FROM revenus "
                               "WHERE date LIKE ? GROUP BY 1", (like,)).fetchall())
        obj = c.execute("SELECT valeur FROM params WHERE cle='objectif_epargne'").fetchone()["valeur"]
        cats = c.execute("SELECT nom,budget FROM categories WHERE actif=1").fetchall()
        cat_tot = c.execute("SELECT categorie, SUM(montant) t FROM depenses WHERE date LIKE ? "
                            "GROUP BY categorie ORDER BY t DESC", (like,)).fetchall()
        grille_rows = c.execute("SELECT categorie, CAST(substr(date,6,2) AS INT) m, SUM(montant) t "
                                "FROM depenses WHERE date LIKE ? GROUP BY 1,2", (like,)).fetchall()

    mois_data = [{"m": i, "dep": round(dep_m.get(i, 0), 2), "rev": round(rev_m.get(i, 0), 2),
                  "ep": round(rev_m.get(i, 0) - dep_m.get(i, 0), 2)} for i in range(1, 13)]
    total_dep = round(sum(x["dep"] for x in mois_data), 2)
    total_rev = round(sum(x["rev"] for x in mois_data), 2)
    epargne = round(total_rev - total_dep, 2)

    actifs = [x for x in mois_data if x["dep"] or x["rev"]]
    meilleur = max(actifs, key=lambda x: x["ep"]) if actifs else None
    pire = min(actifs, key=lambda x: x["ep"]) if actifs else None
    nb_objectif = sum(1 for x in actifs if x["ep"] >= obj)

    budgets = {r["nom"]: r["budget"] for r in cats}
    categories = [{"cat": r["categorie"], "total": round(r["t"], 2),
                   "budget_annuel": budgets.get(r["categorie"], 0) * 12,
                   "pct": round(r["t"] / (budgets.get(r["categorie"], 0) * 12) * 100, 1)
                          if budgets.get(r["categorie"], 0) else 0}
                  for r in cat_tot]

    grille = {}
    for r in grille_rows:
        grille.setdefault(r["categorie"], [0.0] * 12)[r["m"] - 1] = round(r["t"], 2)

    cumul_ep, s = [], 0.0
    for x in mois_data:
        s += x["ep"]
        cumul_ep.append(round(s, 2))

    return {
        "annee": annee,
        "total_depenses": total_dep, "total_revenus": total_rev, "epargne": epargne,
        "taux_epargne": round(epargne / total_rev * 100, 1) if total_rev else 0,
        "moyenne_dep_mois": round(total_dep / len(actifs), 2) if actifs else 0,
        "nb_mois_actifs": len(actifs), "nb_mois_objectif": nb_objectif,
        "objectif_epargne": obj,
        "meilleur_mois": meilleur, "pire_mois": pire,
        "par_mois": mois_data, "epargne_cumulee": cumul_ep,
        "categories": categories, "grille": grille,
    }

def _valider_mois(mois: str):
    try:
        datetime.strptime(mois, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "Format de mois attendu : AAAA-MM")

# ------------------------------------------------------------------ Frontend statique
# Monté APRÈS les routes /api pour que celles-ci restent prioritaires.
# Supprimer ces 2 lignes si le frontend est hébergé ailleurs (ex : Next.js).
if FRONT_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONT_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    print("=" * 52)
    print("  💰 Mon Budget — API : http://localhost:8500/api")
    print("     Interface        : http://localhost:8500")
    print("     Docs Swagger     : http://localhost:8500/docs")
    print("=" * 52)
    uvicorn.run(app, host="0.0.0.0", port=8500)