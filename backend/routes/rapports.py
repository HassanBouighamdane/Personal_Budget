# -*- coding: utf-8 -*-
"""Routes des rapports : résumés jour, semaine, mois et année."""
from datetime import date as dcls, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from database import db
from securite import utilisateur_courant

router = APIRouter(prefix="/api", tags=["rapports"],
                   dependencies=[Depends(utilisateur_courant)])

# ------------------------------------------------------------------ Helpers
def _valider_mois(mois: str):
    try:
        datetime.strptime(mois, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "Format de mois attendu : AAAA-MM")

def _valider_date(d: str) -> dcls:
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Format de date attendu : AAAA-MM-JJ")

def _somme(c, table: str, ou: str, params: tuple) -> float:
    return c.execute(f"SELECT COALESCE(SUM(montant),0) t FROM {table} WHERE {ou}",
                     params).fetchone()["t"]

def _objectif(c) -> float:
    return c.execute("SELECT valeur FROM params WHERE cle='objectif_epargne'").fetchone()["valeur"]

def _budget_total(c) -> float:
    return c.execute("SELECT COALESCE(SUM(budget),0) t FROM categories WHERE actif=1").fetchone()["t"]

# ------------------------------------------------------------------ Vue JOUR
@router.get("/resume_jour")
def resume_jour(date: str):
    d = _valider_date(date)
    veille = (d - timedelta(days=1)).isoformat()
    like_mois = d.strftime("%Y-%m") + "-%"

    with db() as c:
        total_dep = _somme(c, "depenses", "date=%s", (date,))
        total_rev = _somme(c, "revenus", "date=%s", (date,))
        dep_veille = _somme(c, "depenses", "date=%s", (veille,))

        donut = c.execute("SELECT categorie, SUM(montant) t FROM depenses WHERE date=%s "
                          "GROUP BY categorie ORDER BY t DESC", (date,)).fetchall()
        dep = c.execute("SELECT id,categorie,description,montant,paiement FROM depenses "
                        "WHERE date=%s ORDER BY id DESC", (date,)).fetchall()
        rev = c.execute("SELECT id,source,montant FROM revenus WHERE date=%s ORDER BY id DESC",
                        (date,)).fetchall()

        # Moyenne quotidienne du mois (jusqu'au jour demandé)
        dep_mois = _somme(c, "depenses", "date LIKE %s AND date <= %s", (like_mois, date))
        budget_total = _budget_total(c)

    moyenne_jour = round(dep_mois / d.day, 2) if d.day else 0
    budget_jour = round(budget_total / 30.44, 2)   # budget mensuel ramené au jour

    return {
        "date": date,
        "total_depenses": round(total_dep, 2),
        "total_revenus": round(total_rev, 2),
        "depenses_veille": round(dep_veille, 2),
        "nb_transactions": len(dep) + len(rev),
        "moyenne_jour_mois": moyenne_jour,
        "budget_jour": budget_jour,
        "donut": [{"cat": r["categorie"], "montant": round(r["t"], 2)} for r in donut],
        "depenses": dep,
        "revenus": rev,
    }

# ------------------------------------------------------------------ Vue SEMAINE
@router.get("/resume_semaine")
def resume_semaine(date: str):
    d = _valider_date(date)
    lundi = d - timedelta(days=d.weekday())
    jours = [(lundi + timedelta(days=i)).isoformat() for i in range(7)]
    j0, j6 = jours[0], jours[6]
    prec0 = (lundi - timedelta(days=7)).isoformat()
    prec6 = (lundi - timedelta(days=1)).isoformat()

    with db() as c:
        total_dep = _somme(c, "depenses", "date BETWEEN %s AND %s", (j0, j6))
        total_rev = _somme(c, "revenus", "date BETWEEN %s AND %s", (j0, j6))
        dep_prec = _somme(c, "depenses", "date BETWEEN %s AND %s", (prec0, prec6))
        rev_prec = _somme(c, "revenus", "date BETWEEN %s AND %s", (prec0, prec6))

        dep_rows = c.execute("SELECT date, SUM(montant) t FROM depenses "
                             "WHERE date BETWEEN %s AND %s GROUP BY date", (j0, j6)).fetchall()
        rev_rows = c.execute("SELECT date, SUM(montant) t FROM revenus "
                             "WHERE date BETWEEN %s AND %s GROUP BY date", (j0, j6)).fetchall()
        dep_j = {r["date"]: r["t"] for r in dep_rows}
        rev_j = {r["date"]: r["t"] for r in rev_rows}

        donut = c.execute("SELECT categorie, SUM(montant) t FROM depenses "
                          "WHERE date BETWEEN %s AND %s GROUP BY categorie ORDER BY t DESC",
                          (j0, j6)).fetchall()
        top = c.execute("SELECT date,categorie,description,montant FROM depenses "
                        "WHERE date BETWEEN %s AND %s ORDER BY montant DESC LIMIT 8",
                        (j0, j6)).fetchall()
        budget_total = _budget_total(c)

    epargne = total_rev - total_dep
    budget_hebdo = round(budget_total * 12 / 52, 2)   # budget mensuel ramené à la semaine

    return {
        "lundi": j0, "dimanche": j6,
        "total_depenses": round(total_dep, 2),
        "total_revenus": round(total_rev, 2),
        "epargne": round(epargne, 2),
        "depenses_semaine_precedente": round(dep_prec, 2),
        "revenus_semaine_precedente": round(rev_prec, 2),
        "budget_hebdo": budget_hebdo,
        "reste_budget_hebdo": round(budget_hebdo - total_dep, 2),
        "par_jour": [{"date": j, "dep": round(dep_j.get(j, 0), 2),
                      "rev": round(rev_j.get(j, 0), 2)} for j in jours],
        "donut": [{"cat": r["categorie"], "montant": round(r["t"], 2)} for r in donut],
        "top": top,
    }

# ------------------------------------------------------------------ Vue MOIS
@router.get("/resume")
def resume(mois: str):
    _valider_mois(mois)
    like = mois + "-%"
    annee, m = int(mois[:4]), int(mois[5:])
    nb_jours = (dcls(annee + (m == 12), (m % 12) + 1, 1) - dcls(annee, m, 1)).days

    with db() as c:
        total_dep = _somme(c, "depenses", "date LIKE %s", (like,))
        total_rev = _somme(c, "revenus", "date LIKE %s", (like,))
        obj = _objectif(c)

        cats = c.execute("SELECT nom,budget FROM categories WHERE actif=1").fetchall()
        reel_rows = c.execute("SELECT categorie, SUM(montant) t FROM depenses WHERE date LIKE %s "
                              "GROUP BY categorie", (like,)).fetchall()
        reel = {r["categorie"]: r["t"] for r in reel_rows}
        budget_vs = sorted(
            [{"cat": r["nom"], "budget": r["budget"], "reel": round(reel.get(r["nom"], 0), 2),
              "pct": round(reel.get(r["nom"], 0) / r["budget"] * 100, 1) if r["budget"] else 0}
             for r in cats],
            key=lambda x: x["pct"], reverse=True)
        noms_actifs = {r["nom"] for r in cats}
        for nom, v in reel.items():
            if nom not in noms_actifs:
                budget_vs.append({"cat": nom, "budget": 0, "reel": round(v, 2), "pct": 0})

        jours_rows = c.execute("SELECT CAST(substr(date,9,2) AS INT) j, SUM(montant) t FROM depenses "
                               "WHERE date LIKE %s GROUP BY 1", (like,)).fetchall()
        jours = {r["j"]: r["t"] for r in jours_rows}
        cumul, s = [], 0.0
        for j in range(1, nb_jours + 1):
            s += jours.get(j, 0)
            cumul.append(round(s, 2))

        donut = c.execute("SELECT categorie, SUM(montant) t FROM depenses WHERE date LIKE %s "
                          "GROUP BY categorie ORDER BY t DESC", (like,)).fetchall()

        evo = c.execute("""
            SELECT m, SUM(dep) dep, SUM(rev) rev FROM (
                SELECT substr(date,1,7) m, montant dep, 0 rev FROM depenses
                UNION ALL
                SELECT substr(date,1,7) m, 0 dep, montant rev FROM revenus
            ) x WHERE m <= %s GROUP BY m ORDER BY m DESC LIMIT 6
        """, (mois,)).fetchall()
        evo = sorted(evo, key=lambda r: r["m"])

        top = c.execute("SELECT date,categorie,description,montant FROM depenses WHERE date LIKE %s "
                        "ORDER BY montant DESC LIMIT 10", (like,)).fetchall()

        pa, pm = (annee - 1, 12) if m == 1 else (annee, m - 1)
        prec_like = f"{pa:04d}-{pm:02d}-%"
        dep_prec = _somme(c, "depenses", "date LIKE %s", (prec_like,))
        rev_prec = _somme(c, "revenus", "date LIKE %s", (prec_like,))

        budget_total = sum(r["budget"] for r in cats)

    epargne = total_rev - total_dep
    auj = dcls.today()
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
        "top": top,
    }

# ------------------------------------------------------------------ Vue ANNÉE
@router.get("/resume_annuel")
def resume_annuel(annee: int):
    like = f"{annee:04d}-%"
    with db() as c:
        dep_rows = c.execute("SELECT CAST(substr(date,6,2) AS INT) m, SUM(montant) t FROM depenses "
                             "WHERE date LIKE %s GROUP BY 1", (like,)).fetchall()
        rev_rows = c.execute("SELECT CAST(substr(date,6,2) AS INT) m, SUM(montant) t FROM revenus "
                             "WHERE date LIKE %s GROUP BY 1", (like,)).fetchall()
        dep_m = {r["m"]: r["t"] for r in dep_rows}
        rev_m = {r["m"]: r["t"] for r in rev_rows}
        obj = _objectif(c)
        cats = c.execute("SELECT nom,budget FROM categories WHERE actif=1").fetchall()
        cat_tot = c.execute("SELECT categorie, SUM(montant) t FROM depenses WHERE date LIKE %s "
                            "GROUP BY categorie ORDER BY t DESC", (like,)).fetchall()
        grille_rows = c.execute("SELECT categorie, CAST(substr(date,6,2) AS INT) m, SUM(montant) t "
                                "FROM depenses WHERE date LIKE %s GROUP BY 1,2", (like,)).fetchall()

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