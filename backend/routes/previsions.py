# -*- coding: utf-8 -*-
"""
Prévisions de trésorerie : les liquidités mois par mois, du mois en cours aux N prochains.

    solde(M) = solde(M−1) + revenus attendus − dépenses attendues − échéances − dettes à rembourser

  - départ : les liquidités d'aujourd'hui (sans les opérations datées de demain ou après) ;
  - revenus, par source : ses récurrences actives pas encore générées (ni passées) ce mois-là ;
    une source sans récurrence : la MÉDIANE de ses montants mensuels sur les 6 derniers mois
    terminés (une prime ou un remboursement isolé ne gonfle pas chaque mois à venir), moins ce qui
    est déjà saisi ce mois-là ;
  - dépenses, par catégorie : le plus grand de ses récurrences pas encore générées et de ce qui
    manque pour atteindre sa moyenne des 6 derniers mois terminés (ou son budget, pour une catégorie
    « Fixe » dont le budget est plus haut). Le plus grand, et non la somme : un loyer à la fois
    récurrent et dans la moyenne n'est compté qu'une fois ;
  - une opération datée d'après aujourd'hui (saisie d'avance) n'est pas encore dans les liquidités
    de départ : elle est ajoutée à son mois ;
  - échéances avec un montant (assurance, Aïd...) au mois où elles tombent, récurrentes comprises ;
  - emprunts à rembourser au mois de leur échéance (en retard : dans le mois en cours). L'argent
    qu'on me doit n'est pas compté : il arrive quand il arrive.

Les objectifs d'épargne ne sortent pas d'argent (il reste dans les liquidités, réservé) : ils
s'ajoutent à la réserve, de `par_mois` chaque mois jusqu'à leur date limite. Une échéance
provisionnée par un objectif vide sa réserve le mois où elle est payée. « Libre » = solde − réservé.

Fourchette : l'écart-type des dépenses mensuelles passées, multiplié par √(nombre de mois) — plus
on regarde loin, plus l'estimation est incertaine. Les opérations de pointage (tag `pointage`)
sont des corrections, pas des habitudes : elles restent hors des moyennes. Les apports en Bourse
et l'argent versé dans d'autres actifs sont des choix, pas des dépenses prévues : ils n'y sont pas.
"""
from datetime import date
from math import sqrt
from statistics import median, pstdev
from typing import Optional

from fastapi import APIRouter, Depends, Query

from config import aujourdhui
from database import db
from schemas import ReglagesPrevisionIn
from securite import utilisateur_courant
from resume_rendu import dh
from routes import patrimoine
from routes.carnet import ajouter_mois, lire_dettes
from routes.objectifs import lire_objectifs
from routes.recurrences import date_du_mois, mois_de, mois_precedent, mois_suivant, lire_recurrences

router = APIRouter(prefix="/api/previsions", tags=["previsions"],
                   dependencies=[Depends(utilisateur_courant)])

MOIS_HISTORIQUE = 6
HORIZON_DEFAUT, HORIZON_MAX = 6, 12
TAG_EXCLU = "pointage"


MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
           "décembre"]


def _r(v: float) -> float:
    return round(v + 0.0, 2)


def _mois_fr(mois: str) -> str:
    return f"{MOIS_FR[int(mois[5:7]) - 1]} {mois[:4]}"


# ---------------------------------------------------------------- calcul (sans base)
def _a_faire(r: dict, mois: str) -> bool:
    """La récurrence attend encore son opération de `mois` (ni générée ni passée)."""
    return r["debut"] <= mois and not (r.get("dernier_mois") and r["dernier_mois"] >= mois)


def reste_revenus(source: str, recurrences: list, historique: dict, fenetre: list, mois: str, deja: float = 0.0) -> tuple:
    """(montant encore attendu, base) d'une source pour le mois `mois`, `deja` étant ce qui est déjà
    saisi ce mois-là. Une source suivie par une récurrence n'attend que ses récurrences pas encore
    faites : un mois passé (salaire non versé) ne compte plus."""
    recs = [r for r in recurrences if r["type"] == "revenu" and (r["source"] or "") == source and r["debut"] <= mois]
    if recs:
        return sum(r["montant"] for r in recs if _a_faire(r, mois)), "recurrence"
    if not fenetre:
        return 0.0, "moyenne"
    return max(median(historique.get(source, {}).get(m, 0.0) for m in fenetre) - deja, 0.0), "moyenne"


def reste_depenses(categorie: str, info: Optional[dict], recurrences: list, historique: dict, fenetre: list,
                   mois: str, deja: float = 0.0) -> tuple:
    """(montant encore attendu, base) d'une catégorie pour le mois `mois` : le plus grand de ses
    récurrences pas encore faites et de ce qui manque pour atteindre sa moyenne (ou son budget fixe)."""
    recs = [r for r in recurrences if r["type"] == "depense" and r["categorie"] == categorie and r["debut"] <= mois]
    en_attente = sum(r["montant"] for r in recs if _a_faire(r, mois))
    if info is not None and not info["actif"] and not recs:
        return 0.0, "moyenne"       # catégorie désactivée : plus de dépenses attendues
    moyenne = sum(historique.get(categorie, {}).get(m, 0.0) for m in fenetre) / len(fenetre) if fenetre else 0.0
    budget = info["budget"] if info and info["fixe"] else 0.0
    habitude, base = (budget, "budget") if budget > moyenne else (moyenne, "moyenne")
    manque = max(habitude - deja, 0.0)
    return (en_attente, "recurrence") if en_attente > 0 and en_attente >= manque else (manque, base)


def dates_echeance(e: dict, debut: date, fin: date) -> list:
    """Dates d'une échéance (et de ses reports si elle est récurrente) entre `debut` et `fin` inclus."""
    dates, d, n = [], e["date_echeance"], 0
    while d <= fin and n < 400:
        if d >= debut:
            dates.append(d)
        if not e.get("recurrence_mois"):
            break
        n += 1
        d = ajouter_mois(e["date_echeance"], e["recurrence_mois"] * n)
    return dates


def projeter(d: dict, auj: date, horizon: int, plancher: float = 0.0) -> dict:
    """Prévision mois par mois à partir des données de charger() (ne lit pas la base)."""
    mois_liste = [mois_de(auj)]
    for _ in range(horizon):
        mois_liste.append(mois_suivant(mois_liste[-1]))
    fin = date_du_mois(mois_liste[-1], 31)
    fenetre, recs = d["fenetre"], d["recurrences"]

    sources = set(d["hist_revenus"]) | {r["source"] or "" for r in recs if r["type"] == "revenu"}
    categories = ({c for c, i in d["categories"].items() if i["actif"]} | set(d["hist_depenses"])
                  | {r["categorie"] for r in recs if r["type"] == "depense"})

    # Échéances et dettes, rangées par mois
    echeances_mois, provisions_mois = {}, {}
    for e in d["echeances"]:
        if not e.get("montant"):
            continue
        for jour in dates_echeance(e, auj, fin):
            echeances_mois.setdefault(mois_de(jour), []).append(
                {"titre": e["titre"], "date": jour, "montant": float(e["montant"])})
            if e.get("objectif_id"):
                provisions_mois.setdefault(mois_de(jour), []).append((e["objectif_id"], float(e["montant"])))
    dettes_mois = {}
    for x in d["dettes"]:
        if x["sens"] != "emprunt" or x["reste"] <= 0 or not x["echeance"] or x["echeance"] > fin:
            continue
        m = max(mois_de(x["echeance"]), mois_liste[0])
        dettes_mois.setdefault(m, []).append({"personne": x["personne"], "date": x["echeance"],
                                              "montant": float(x["reste"]), "en_retard": x["echeance"] < auj})

    # Réserve des objectifs, objectif par objectif
    reserve_objectif = {o["id"]: float(o["reserve"]) for o in d["objectifs"]}

    solde = d["depart"]
    totaux_hist = [sum(d["hist_depenses"].get(c, {}).get(m, 0.0) for c in d["hist_depenses"]) for m in fenetre]
    ecart_type = pstdev(totaux_hist) if len(totaux_hist) >= 2 else 0.0
    points = []
    for k, mois in enumerate(mois_liste):
        deja_dep, deja_rev = d["deja_depenses"].get(mois, {}), d["deja_revenus"].get(mois, {})
        futur_dep, futur_rev = d["futur_depenses"].get(mois, {}), d["futur_revenus"].get(mois, {})

        def ligne(nom: str, reste: float, base: str, futur: dict) -> Optional[dict]:
            """Ce qui reste attendu, plus ce qui est saisi d'avance (daté d'après aujourd'hui : pas
            encore dans les liquidités de départ)."""
            montant = reste + futur.get(nom, 0.0)
            return {"nom": nom, "montant": _r(montant), "base": base if reste > 0.005 else "saisi"} if montant > 0.005 else None

        lignes_rev = [l for s in sorted(sources)
                      if (l := ligne(s, *reste_revenus(s, recs, d["hist_revenus"], fenetre, mois, deja_rev.get(s, 0.0)), futur_rev))]
        lignes_dep = [l for c in sorted(categories)
                      if (l := ligne(c, *reste_depenses(c, d["categories"].get(c), recs, d["hist_depenses"], fenetre, mois,
                                                        deja_dep.get(c, 0.0)), futur_dep))]
        echeances = echeances_mois.get(mois, [])
        dettes = dettes_mois.get(mois, [])

        revenus = sum(l["montant"] for l in lignes_rev)
        depenses = sum(l["montant"] for l in lignes_dep)
        sorties = sum(e["montant"] for e in echeances) + sum(x["montant"] for x in dettes)
        solde += revenus - depenses - sorties

        # Objectifs : versement du mois jusqu'à la date limite, puis échéance provisionnée payée
        for o in d["objectifs"]:
            if o["par_mois"] and o["date_limite"] and mois <= mois_de(o["date_limite"]):
                reserve_objectif[o["id"]] = reserve_objectif.get(o["id"], 0.0) + float(o["par_mois"])
        for objectif_id, montant in provisions_mois.get(mois, []):
            if objectif_id in reserve_objectif:
                reserve_objectif[objectif_id] = max(reserve_objectif[objectif_id] - montant, 0.0)
        reserve = sum(reserve_objectif.values())

        incertitude = ecart_type * sqrt(k + 1)
        points.append({
            "mois": mois, "revenus": _r(revenus), "depenses": _r(depenses),
            "echeances": _r(sum(e["montant"] for e in echeances)), "dettes": _r(sum(x["montant"] for x in dettes)),
            "solde": _r(solde), "bas": _r(solde - incertitude), "haut": _r(solde + incertitude),
            "reserve": _r(reserve), "libre": _r(solde - reserve),
            "detail": {"revenus": lignes_rev, "depenses": sorted(lignes_dep, key=lambda l: -l["montant"]),
                       "echeances": echeances, "dettes": dettes},
        })

    point_bas = min(points, key=lambda p: p["solde"])
    libre_bas = min(points, key=lambda p: p["libre"])
    # Mois « type » : le premier mois entier (le mois en cours n'en est qu'un reste)
    type_ = points[1] if len(points) > 1 else points[0]
    epargne_prevue = _r(type_["revenus"] - type_["depenses"])
    rythme_objectifs = _r(sum(float(o["par_mois"]) for o in d["objectifs"] if o["par_mois"]))

    alertes = []
    if point_bas["solde"] < plancher:
        alertes.append({"type": "plancher", "mois": point_bas["mois"],
                        "titre": "Liquidités sous ton plancher" if plancher > 0 else "Liquidités dans le rouge",
                        "detail": f"{dh(point_bas['solde'])} prévus fin {_mois_fr(point_bas['mois'])}"
                                  + (f" (plancher : {dh(plancher)})" if plancher > 0 else "")})
    if libre_bas["libre"] < 0 and libre_bas["solde"] >= plancher:
        alertes.append({"type": "objectifs", "mois": libre_bas["mois"],
                        "titre": "Tes objectifs réservent plus que tes liquidités",
                        "detail": f"{dh(-libre_bas['libre'])} manquants fin {_mois_fr(libre_bas['mois'])}"})
    if rythme_objectifs > 0 and rythme_objectifs > epargne_prevue:
        alertes.append({"type": "rythme", "mois": type_["mois"],
                        "titre": "Tes objectifs demandent plus que ton épargne",
                        "detail": f"{dh(rythme_objectifs)} à mettre de côté par mois, {dh(epargne_prevue)} d'épargne prévue"})

    return {"date": auj, "depart": _r(d["depart"]), "plancher": plancher, "nb_mois_historique": len(fenetre),
            "mois": points, "point_bas": {"mois": point_bas["mois"], "solde": point_bas["solde"]},
            "epargne_prevue": epargne_prevue, "rythme_objectifs": rythme_objectifs, "alertes": alertes}


# ---------------------------------------------------------------- données
def fenetre_historique(auj: date, premier_mois: Optional[str]) -> list:
    """Les MOIS_HISTORIQUE derniers mois terminés, sans ceux d'avant la première opération."""
    mois, m = [], mois_de(auj)
    for _ in range(MOIS_HISTORIQUE):
        m = mois_precedent(m)
        if premier_mois and m >= premier_mois:
            mois.insert(0, m)
    return mois


def charger(auj: date) -> dict:
    depart = patrimoine.liquidites_du_jour(auj)
    mois_courant = mois_de(auj)
    with db() as c:
        premier = c.execute("""SELECT min(m) m FROM (SELECT min(substr(date,1,7)) m FROM depenses
                               UNION ALL SELECT min(substr(date,1,7)) FROM revenus) x""").fetchone()["m"]
        fenetre = fenetre_historique(auj, premier)
        debut = (fenetre[0] if fenetre else mois_courant) + "-01"

        def par_nom_et_mois(table: str, colonne: str, depuis: str, jusqua: Optional[str] = None) -> list:
            borne = " AND date < %s" if jusqua else ""
            return c.execute(f"""SELECT COALESCE({colonne},'') nom, substr(date,1,7) mois, SUM(montant) t
                                 FROM {table} WHERE date >= %s{borne} AND NOT tags @> ARRAY[%s]::text[]
                                 GROUP BY 1, 2""",
                             (depuis, *([jusqua] if jusqua else []), TAG_EXCLU)).fetchall()

        hist_dep, hist_rev = {}, {}
        for r in par_nom_et_mois("depenses", "categorie", debut, mois_courant + "-01"):
            hist_dep.setdefault(r["nom"], {})[r["mois"]] = float(r["t"])
        for r in par_nom_et_mois("revenus", "source", debut, mois_courant + "-01"):
            hist_rev.setdefault(r["nom"], {})[r["mois"]] = float(r["t"])

        # Déjà saisi : tout le mois en cours et au-delà (pour le déduire de l'attendu) ; daté d'après
        # aujourd'hui (pas encore dans les liquidités de départ, à ajouter)
        deja_dep, deja_rev, futur_dep, futur_rev = {}, {}, {}, {}
        for table, colonne, deja, futur in (("depenses", "categorie", deja_dep, futur_dep),
                                             ("revenus", "source", deja_rev, futur_rev)):
            for r in c.execute(f"""SELECT COALESCE({colonne},'') nom, substr(date,1,7) mois, date > %s apres, SUM(montant) t
                                   FROM {table} WHERE date >= %s GROUP BY 1, 2, 3""",
                               (auj.isoformat(), mois_courant + "-01")).fetchall():
                deja.setdefault(r["mois"], {}).setdefault(r["nom"], 0.0)
                deja[r["mois"]][r["nom"]] += float(r["t"])
                if r["apres"]:
                    futur.setdefault(r["mois"], {})[r["nom"]] = float(r["t"])

        categories = {r["nom"]: {"budget": float(r["budget"]), "fixe": r["fixe"], "actif": r["actif"] == 1}
                      for r in c.execute("SELECT nom, budget, fixe, actif FROM categories").fetchall()}
        recurrences = [r for r in lire_recurrences(c) if r["actif"]]
        echeances = c.execute("SELECT titre, date_echeance, recurrence_mois, montant, objectif_id FROM echeances "
                              "WHERE montant IS NOT NULL").fetchall()
        dettes = [{"sens": x["sens"], "personne": x["personne"], "reste": float(x["reste"]), "echeance": x["echeance"]}
                  for x in lire_dettes(c)]
        objectifs = [{"id": o["id"], "nom": o["nom"], "reserve": float(o["reserve"]), "date_limite": o["date_limite"],
                      "par_mois": float(o["par_mois"]) if o["par_mois"] is not None else None}
                     for o in lire_objectifs(c, auj) if not o["archive"]]
        plancher = c.execute("SELECT valeur FROM params WHERE cle='prevision_plancher'").fetchone()
    return {"depart": depart, "fenetre": fenetre, "hist_depenses": hist_dep, "hist_revenus": hist_rev,
            "deja_depenses": deja_dep, "deja_revenus": deja_rev, "futur_depenses": futur_dep, "futur_revenus": futur_rev,
            "categories": categories, "recurrences": recurrences, "echeances": echeances, "dettes": dettes,
            "objectifs": objectifs, "plancher": float(plancher["valeur"]) if plancher else 0.0}


def calculer_previsions(auj: date, horizon: int = HORIZON_DEFAUT) -> dict:
    d = charger(auj)
    return projeter(d, auj, horizon, d["plancher"])


@router.get("")
def previsions(mois: int = Query(HORIZON_DEFAUT, ge=1, le=HORIZON_MAX)):
    return calculer_previsions(aujourdhui(), mois)


@router.put("/reglages")
def regler(r: ReglagesPrevisionIn):
    with db() as c:
        c.execute("""INSERT INTO params(cle,valeur) VALUES('prevision_plancher',%s)
                     ON CONFLICT (cle) DO UPDATE SET valeur=EXCLUDED.valeur""", (r.plancher,))
    return {"ok": True}
