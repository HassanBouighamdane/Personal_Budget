# -*- coding: utf-8 -*-
"""Routes des rapports : résumés jour, semaine, mois et année."""
from datetime import date as dcls, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from config import aujourdhui
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

def _historique(c) -> dict:
    """{catégorie: {"actif", "lignes": [(mois_debut, budget, fixe)...] triées}} (budgets_historique)."""
    hist = {}
    for r in c.execute("""SELECT c.nom, c.actif, h.mois_debut, h.budget, h.fixe
                          FROM budgets_historique h JOIN categories c ON c.id = h.categorie_id
                          ORDER BY h.mois_debut""").fetchall():
        hist.setdefault(r["nom"], {"actif": r["actif"], "lignes": []})["lignes"].append(
            (r["mois_debut"], r["budget"], r["fixe"]))
    return hist

def categories_du_mois(hist: dict, mois: str) -> list:
    """Budget et « fixe » de chaque catégorie pour le mois AAAA-MM : la dernière ligne
    d'historique commencée au plus tard ce mois-là. Une catégorie créée après ce mois n'y
    figure pas ; une catégorie désactivée n'y figure que si elle avait encore un budget."""
    res = []
    for nom, h in hist.items():
        lignes = [l for l in h["lignes"] if l[0] <= mois]
        if not lignes:
            continue
        _, budget, fixe = lignes[-1]
        if h["actif"] or budget:
            res.append({"nom": nom, "budget": budget, "fixe": fixe})
    return res

def _categories(c, mois: str) -> list:
    return categories_du_mois(_historique(c), mois)

def _fixes(cats) -> list:
    """Noms des catégories de charges fixes (loyer, factures...)."""
    return [r["nom"] for r in cats if r["fixe"]]

def _budget_variable(cats) -> float:
    """Budget mensuel hors charges fixes : seul lui se répartit au jour ou à la semaine
    (un loyer payé une fois par mois ne « dépasse » pas le budget du jour où il tombe)."""
    return sum(r["budget"] for r in cats if not r["fixe"])

# Condition SQL « dépense variable » : à ajouter avec la liste des catégories fixes en paramètre
HORS_FIXES = " AND NOT (categorie = ANY(%s::text[]))"

def _nb_jours_mois(annee: int, m: int) -> int:
    return (dcls(annee + (m == 12), (m % 12) + 1, 1) - dcls(annee, m, 1)).days

def projection_fin_mois(reel: dict, cats, jour: int, nb_jours: int) -> float:
    """Dépenses attendues en fin de mois. Les charges fixes comptent pour leur budget (ou
    leur montant réel s'il le dépasse déjà), qu'elles soient payées ou non ; seules les
    dépenses variables sont extrapolées au rythme du mois. Sans cette séparation, un loyer
    payé le 1er multiplierait la projection par le nombre de jours du mois."""
    fixes = {r["nom"]: r["budget"] for r in cats if r["fixe"]}
    part_fixe = sum(max(reel.get(nom, 0), budget) for nom, budget in fixes.items())
    variables = sum(v for nom, v in reel.items() if nom not in fixes)
    return round(part_fixe + variables / jour * nb_jours, 2)

def stats_mois_termines(mois_data: list, termine, objectif: float) -> dict:
    """Moyennes, meilleur/pire mois et objectif atteint, calculés sur les seuls mois TERMINÉS
    ayant des mouvements : le mois en cours (incomplet, salaire parfois pas encore reçu) ne
    doit ni baisser la moyenne, ni passer pour le « pire mois », ni compter comme un échec."""
    actifs = [x for x in mois_data if (x["dep"] or x["rev"]) and termine(x["m"])]
    n = len(actifs)
    return {
        "nb_mois_actifs": n,
        "moyenne_dep_mois": round(sum(x["dep"] for x in actifs) / n, 2) if n else 0,
        "moyenne_rev_mois": round(sum(x["rev"] for x in actifs) / n, 2) if n else 0,
        "nb_mois_objectif": sum(1 for x in actifs if x["ep"] >= objectif),
        "meilleur_mois": max(actifs, key=lambda x: x["ep"]) if actifs else None,
        "pire_mois": min(actifs, key=lambda x: x["ep"]) if actifs else None,
    }

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
        dep = c.execute("SELECT id,categorie,description,montant FROM depenses "
                        "WHERE date=%s ORDER BY id DESC", (date,)).fetchall()
        rev = c.execute("SELECT id,source,COALESCE(description,'') description,montant FROM revenus WHERE date=%s ORDER BY id DESC",
                        (date,)).fetchall()

        cats = _categories(c, date[:7])
        fixes = _fixes(cats)
        dep_var = _somme(c, "depenses", "date=%s" + HORS_FIXES, (date, fixes))
        # Moyenne quotidienne des dépenses variables du mois (jusqu'au jour demandé)
        dep_mois = _somme(c, "depenses", "date LIKE %s AND date <= %s" + HORS_FIXES, (like_mois, date, fixes))

    moyenne_jour = round(dep_mois / d.day, 2) if d.day else 0
    budget_jour = round(_budget_variable(cats) / 30.44, 2)   # budget variable mensuel ramené au jour

    return {
        "date": date,
        "total_depenses": round(total_dep, 2),
        "total_revenus": round(total_rev, 2),
        "depenses_variables": round(dep_var, 2),   # à comparer au budget journalier
        "charges_fixes": bool(fixes),
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
    return calculer_resume_semaine(_valider_date(date), aujourdhui())

def calculer_resume_semaine(d: dcls, auj: dcls) -> dict:
    """`auj` est passé en paramètre pour que les tests fixent la date de référence."""
    lundi = d - timedelta(days=d.weekday())
    jours = [(lundi + timedelta(days=i)).isoformat() for i in range(7)]
    j0, j6 = jours[0], jours[6]
    prec0 = (lundi - timedelta(days=7)).isoformat()
    prec6 = (lundi - timedelta(days=1)).isoformat()
    # Semaine en cours : comparée à la semaine précédente jusqu'au même jour (lundi → même
    # jour), pas à la semaine entière, sinon la baisse affichée en milieu de semaine ne veut rien dire
    partielle = j0 <= auj.isoformat() < j6
    prec_fin = (lundi - timedelta(days=7 - auj.weekday())).isoformat() if partielle else prec6

    with db() as c:
        total_dep = _somme(c, "depenses", "date BETWEEN %s AND %s", (j0, j6))
        total_rev = _somme(c, "revenus", "date BETWEEN %s AND %s", (j0, j6))
        dep_prec = _somme(c, "depenses", "date BETWEEN %s AND %s", (prec0, prec_fin))
        rev_prec = _somme(c, "revenus", "date BETWEEN %s AND %s", (prec0, prec_fin))
        dep_prec_totale = _somme(c, "depenses", "date BETWEEN %s AND %s", (prec0, prec6))
        cats = _categories(c, j0[:7])
        fixes = _fixes(cats)
        dep_var = _somme(c, "depenses", "date BETWEEN %s AND %s" + HORS_FIXES, (j0, j6, fixes))

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

    epargne = total_rev - total_dep
    budget_hebdo = round(_budget_variable(cats) * 12 / 52, 2)   # budget variable mensuel ramené à la semaine

    return {
        "lundi": j0, "dimanche": j6,
        "total_depenses": round(total_dep, 2),
        "total_revenus": round(total_rev, 2),
        "epargne": round(epargne, 2),
        # Semaine précédente sur la même durée (jusqu'au même jour si la semaine est en cours)
        "depenses_semaine_precedente": round(dep_prec, 2),
        "revenus_semaine_precedente": round(rev_prec, 2),
        "depenses_semaine_precedente_totale": round(dep_prec_totale, 2),
        "comparaison_partielle": partielle,
        "depenses_variables": round(dep_var, 2),
        "charges_fixes": bool(fixes),
        "budget_hebdo": budget_hebdo,
        "reste_budget_hebdo": round(budget_hebdo - dep_var, 2),
        "par_jour": [{"date": j, "dep": round(dep_j.get(j, 0), 2),
                      "rev": round(rev_j.get(j, 0), 2)} for j in jours],
        "donut": [{"cat": r["categorie"], "montant": round(r["t"], 2)} for r in donut],
        "top": top,
    }

# ------------------------------------------------------------------ Vue MOIS
@router.get("/resume")
def resume(mois: str):
    _valider_mois(mois)
    return calculer_resume(mois, aujourdhui())

def calculer_resume(mois: str, auj: dcls) -> dict:
    """`auj` est passé en paramètre pour que les tests fixent la date de référence."""
    like = mois + "-%"
    annee, m = int(mois[:4]), int(mois[5:])
    nb_jours = _nb_jours_mois(annee, m)
    est_courant = mois == auj.strftime("%Y-%m")

    with db() as c:
        total_dep = _somme(c, "depenses", "date LIKE %s", (like,))
        total_rev = _somme(c, "revenus", "date LIKE %s", (like,))
        obj = _objectif(c)

        cats = _categories(c, mois)
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
        dep_prec_total = _somme(c, "depenses", "date LIKE %s", (prec_like,))
        rev_prec_total = _somme(c, "revenus", "date LIKE %s", (prec_like,))
        # Mois en cours : comparé au mois précédent arrêté au même jour (le 10 contre le 1er-10),
        # pas au mois entier. Si le mois précédent est plus court, il est pris en entier.
        jour_cmp = auj.day if est_courant and auj.day < _nb_jours_mois(pa, pm) else None
        if jour_cmp:
            fin = f"{pa:04d}-{pm:02d}-{jour_cmp:02d}"
            dep_prec = _somme(c, "depenses", "date LIKE %s AND date <= %s", (prec_like, fin))
            rev_prec = _somme(c, "revenus", "date LIKE %s AND date <= %s", (prec_like, fin))
        else:
            dep_prec, rev_prec = dep_prec_total, rev_prec_total

        # Même mois l'an dernier : plus parlant que le mois précédent pour les dépenses saisonnières
        # (été, rentrée, fêtes). Même règle de durée : le mois en cours est comparé jusqu'au même jour.
        an_like = f"{annee - 1:04d}-{m:02d}-%"
        dep_an_total = _somme(c, "depenses", "date LIKE %s", (an_like,))
        rev_an_total = _somme(c, "revenus", "date LIKE %s", (an_like,))
        jour_an = auj.day if est_courant and auj.day < _nb_jours_mois(annee - 1, m) else None
        fin_an = f"{annee - 1:04d}-{m:02d}-{jour_an:02d}" if jour_an else f"{annee - 1:04d}-{m:02d}-31"
        if jour_an:
            dep_an = _somme(c, "depenses", "date LIKE %s AND date <= %s", (an_like, fin_an))
            rev_an = _somme(c, "revenus", "date LIKE %s AND date <= %s", (an_like, fin_an))
        else:
            dep_an, rev_an = dep_an_total, rev_an_total
        # Par catégorie, sur la même durée (info-bulle de « Budget vs Réel »)
        reel_an = {r["categorie"]: r["t"] for r in c.execute(
            "SELECT categorie, SUM(montant) t FROM depenses WHERE date LIKE %s AND date <= %s GROUP BY categorie",
            (an_like, fin_an)).fetchall()}
        for b in budget_vs:
            b["an_dernier"] = round(reel_an.get(b["cat"], 0), 2)

        budget_total = sum(r["budget"] for r in cats)

    epargne = total_rev - total_dep
    fixes = set(_fixes(cats))
    dep_var = sum(v for nom, v in reel.items() if nom not in fixes)
    projection = projection_fin_mois(reel, cats, auj.day, nb_jours) if est_courant else None

    return {
        "mois": mois, "nb_jours": nb_jours,
        "total_depenses": round(total_dep, 2), "total_revenus": round(total_rev, 2),
        "epargne": round(epargne, 2),
        "taux_epargne": round(epargne / total_rev * 100, 1) if total_rev else 0,
        "objectif_epargne": obj, "budget_total": budget_total,
        "reste_budget": round(budget_total - total_dep, 2),
        # Mois précédent sur la même durée (jusqu'au jour `jour_comparaison` s'il est renseigné)
        "depenses_mois_precedent": round(dep_prec, 2),
        "revenus_mois_precedent": round(rev_prec, 2),
        "depenses_mois_precedent_total": round(dep_prec_total, 2),
        "revenus_mois_precedent_total": round(rev_prec_total, 2),
        "jour_comparaison": jour_cmp,
        # Même mois l'an dernier, sur la même durée (jusqu'au jour `jour_comparaison_annee` s'il est renseigné)
        "depenses_annee_precedente": round(dep_an, 2),
        "revenus_annee_precedente": round(rev_an, 2),
        "depenses_annee_precedente_total": round(dep_an_total, 2),
        "revenus_annee_precedente_total": round(rev_an_total, 2),
        "jour_comparaison_annee": jour_an,
        "depenses_variables": round(dep_var, 2),
        "charges_fixes": bool(fixes),
        "projection_fin_mois": projection,
        "budget_vs_reel": budget_vs, "cumul_quotidien": cumul,
        "donut": [{"cat": r["categorie"], "montant": round(r["t"], 2)} for r in donut],
        "evolution": evo,
        "top": top,
    }

# ------------------------------------------------------------------ Vue ANNÉE
@router.get("/resume_annuel")
def resume_annuel(annee: int):
    return calculer_resume_annuel(annee, aujourdhui())

def calculer_resume_annuel(annee: int, auj: dcls) -> dict:
    """`auj` est passé en paramètre pour que les tests fixent la date de référence."""
    like = f"{annee:04d}-%"
    with db() as c:
        dep_rows = c.execute("SELECT CAST(substr(date,6,2) AS INT) m, SUM(montant) t FROM depenses "
                             "WHERE date LIKE %s GROUP BY 1", (like,)).fetchall()
        rev_rows = c.execute("SELECT CAST(substr(date,6,2) AS INT) m, SUM(montant) t FROM revenus "
                             "WHERE date LIKE %s GROUP BY 1", (like,)).fetchall()
        dep_m = {r["m"]: r["t"] for r in dep_rows}
        rev_m = {r["m"]: r["t"] for r in rev_rows}
        obj = _objectif(c)
        hist = _historique(c)
        cat_tot = c.execute("SELECT categorie, SUM(montant) t FROM depenses WHERE date LIKE %s "
                            "GROUP BY categorie ORDER BY t DESC", (like,)).fetchall()
        grille_rows = c.execute("SELECT categorie, CAST(substr(date,6,2) AS INT) m, SUM(montant) t "
                                "FROM depenses WHERE date LIKE %s GROUP BY 1,2", (like,)).fetchall()

    mois_data = [{"m": i, "dep": round(dep_m.get(i, 0), 2), "rev": round(rev_m.get(i, 0), 2),
                  "ep": round(rev_m.get(i, 0) - dep_m.get(i, 0), 2)} for i in range(1, 13)]
    total_dep = round(sum(x["dep"] for x in mois_data), 2)
    total_rev = round(sum(x["rev"] for x in mois_data), 2)
    epargne = round(total_rev - total_dep, 2)

    stats = stats_mois_termines(mois_data, lambda i: (annee, i) < (auj.year, auj.month), obj)

    # Budget de chaque mois (il peut changer en cours d'année). L'année en cours est comparée au
    # budget à date (mois écoulés + part du mois en cours), pas au budget des 12 mois.
    if annee < auj.year:
        poids = [1.0] * 12
    elif annee > auj.year:
        poids = [0.0] * 12
    else:
        poids = [1.0 if m < auj.month else 0.0 for m in range(1, 13)]
        poids[auj.month - 1] = auj.day / _nb_jours_mois(auj.year, auj.month)
    budget_annuel, budget_a_date = {}, {}
    for m in range(1, 13):
        for r in categories_du_mois(hist, f"{annee:04d}-{m:02d}"):
            budget_annuel[r["nom"]] = budget_annuel.get(r["nom"], 0) + r["budget"]
            budget_a_date[r["nom"]] = budget_a_date.get(r["nom"], 0) + r["budget"] * poids[m - 1]
    categories = []
    for r in cat_tot:
        a_date = budget_a_date.get(r["categorie"], 0)
        categories.append({"cat": r["categorie"], "total": round(r["t"], 2),
                           "budget_annuel": round(budget_annuel.get(r["categorie"], 0), 2),
                           "budget_a_date": round(a_date, 2),
                           "pct": round(r["t"] / a_date * 100, 1) if a_date else 0})

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
        # Statistiques sur les mois terminés uniquement (cf. stats_mois_termines)
        "moyenne_dep_mois": stats["moyenne_dep_mois"],
        "nb_mois_actifs": stats["nb_mois_actifs"], "nb_mois_objectif": stats["nb_mois_objectif"],
        "mois_en_cours": auj.month if annee == auj.year else None,
        "objectif_epargne": obj,
        "meilleur_mois": stats["meilleur_mois"], "pire_mois": stats["pire_mois"],
        "par_mois": mois_data, "epargne_cumulee": cumul_ep,
        "categories": categories, "grille": grille,
    }
# ------------------------------------------------------------------ Vue GLOBALE
def _mois_continus(debut: str, fin: str) -> list:
    """Tous les mois AAAA-MM de `debut` à `fin` inclus (y compris les mois sans mouvement)."""
    a, m = int(debut[:4]), int(debut[5:7])
    fa, fm = int(fin[:4]), int(fin[5:7])
    res = []
    while (a, m) <= (fa, fm):
        res.append(f"{a:04d}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return res

@router.get("/resume_global")
def resume_global():
    return calculer_resume_global(aujourdhui())

def calculer_resume_global(auj: dcls) -> dict:
    """Tout l'historique : totaux, évolution mois par mois, bilan par année, catégories, top dépenses."""
    with db() as c:
        dep_rows = c.execute("SELECT substr(date,1,7) m, SUM(montant) t FROM depenses GROUP BY 1").fetchall()
        rev_rows = c.execute("SELECT substr(date,1,7) m, SUM(montant) t FROM revenus GROUP BY 1").fetchall()
        obj = _objectif(c)
        cat_tot = c.execute("SELECT categorie, SUM(montant) t FROM depenses "
                            "GROUP BY categorie ORDER BY t DESC").fetchall()
        top = c.execute("SELECT date,categorie,description,montant FROM depenses "
                        "ORDER BY montant DESC LIMIT 10").fetchall()

    dep_m = {r["m"]: r["t"] for r in dep_rows}
    rev_m = {r["m"]: r["t"] for r in rev_rows}
    tous = sorted(set(dep_m) | set(rev_m))
    mois = _mois_continus(tous[0], tous[-1]) if tous else []

    mois_data = [{"m": m, "dep": round(dep_m.get(m, 0), 2), "rev": round(rev_m.get(m, 0), 2),
                  "ep": round(rev_m.get(m, 0) - dep_m.get(m, 0), 2)} for m in mois]
    total_dep = round(sum(x["dep"] for x in mois_data), 2)
    total_rev = round(sum(x["rev"] for x in mois_data), 2)
    epargne = round(total_rev - total_dep, 2)

    stats = stats_mois_termines(mois_data, lambda m: m < auj.strftime("%Y-%m"), obj)

    cumul_ep, s = [], 0.0
    for x in mois_data:
        s += x["ep"]
        cumul_ep.append(round(s, 2))

    par_annee = {}
    for x in mois_data:
        a = par_annee.setdefault(x["m"][:4], {"annee": int(x["m"][:4]), "dep": 0.0, "rev": 0.0})
        a["dep"] += x["dep"]
        a["rev"] += x["rev"]
    annees = [{"annee": a["annee"], "dep": round(a["dep"], 2), "rev": round(a["rev"], 2),
               "ep": round(a["rev"] - a["dep"], 2),
               "taux_epargne": round((a["rev"] - a["dep"]) / a["rev"] * 100, 1) if a["rev"] else 0}
              for a in par_annee.values()]

    return {
        "premier_mois": mois[0] if mois else None, "dernier_mois": mois[-1] if mois else None,
        "total_depenses": total_dep, "total_revenus": total_rev, "epargne": epargne,
        "taux_epargne": round(epargne / total_rev * 100, 1) if total_rev else 0,
        # Statistiques sur les mois terminés uniquement (cf. stats_mois_termines)
        "nb_mois_actifs": stats["nb_mois_actifs"],
        "moyenne_dep_mois": stats["moyenne_dep_mois"],
        "moyenne_rev_mois": stats["moyenne_rev_mois"],
        "nb_mois_objectif": stats["nb_mois_objectif"],
        "objectif_epargne": obj,
        "meilleur_mois": stats["meilleur_mois"], "pire_mois": stats["pire_mois"],
        "par_mois": mois_data, "epargne_cumulee": cumul_ep, "par_annee": annees,
        "donut": [{"cat": r["categorie"], "montant": round(r["t"], 2)} for r in cat_tot],
        "top": top,
    }
