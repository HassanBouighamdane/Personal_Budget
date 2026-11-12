# -*- coding: utf-8 -*-
"""
Indices de référence et comparaison : « aurais-je plus d'argent aujourd'hui si j'avais mis les mêmes
sommes, aux mêmes dates, dans l'indice ? »

Indices suivis : MASI, MASI 20 et MASI Mid and Small Cap (cours seuls), et les versions « Rentabilité
Net » du MASI et du MASI 20, qui réinvestissent les dividendes après la retenue à la source, comme
on les touche. Ce sont elles qui se comparent honnêtement à un compte qui touche des dividendes :
un indice de cours seul oublie les dividendes de ses sociétés (3 à 4 % par an) et flatte le compte.

Valeurs notées chaque soir de bourse par la tâche du soir (avec les cours de clôture), ou importées
d'un fichier pour les jours d'avant : sans elles, les apports antérieurs à l'historique ne peuvent
pas être comparés.

Portefeuille virtuel : chaque apport au compte Bourse achète des parts d'indice à sa valeur du jour
(la dernière connue si c'est un week-end ou un jour férié), chaque retrait en revend. Comparer les
APPORTS (et non chaque achat de titre) mesure toute la décision : choix des titres, espèces laissées
sans placement et frais.
"""
from bisect import bisect_right
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from config import aujourdhui
from cours_bvc import telecharger_indices
from database import db
from schemas import ImportIndiceIn
from securite import utilisateur_courant
from routes import bourse

router = APIRouter(prefix="/api/bourse/indices", tags=["indices"], dependencies=[Depends(utilisateur_courant)])

# Code de la Bourse de Casablanca → nom affiché et dividendes compris ou non (dans l'ordre d'affichage)
INDICES = {
    "MASRN": {"nom": "MASI Rentabilité Net", "dividendes": True},
    "MS20RN": {"nom": "MASI 20 Rentabilité Net", "dividendes": True},
    "MASI": {"nom": "MASI", "dividendes": False},
    "MSI20": {"nom": "MASI 20", "dividendes": False},
    "MASIMS": {"nom": "MASI Mid and Small Cap", "dividendes": False},
}
INDICE_DEFAUT = "MASRN"
ECART_IMPORT_MAX = 0.05     # une valeur importée à plus de 5 % de la valeur notée le même jour : autre indice
POINTS_COURBE_MAX = 260


def _indice(code: str) -> str:
    code = code.strip().upper()
    if code not in INDICES:
        raise HTTPException(404, f"Indice inconnu : {code}")
    return code


# ---------------------------------------------------------------- relevé du soir
def noter_indices(auj: date) -> dict:
    """Note la clôture des indices suivis (tâche du soir). Rien un week-end ou un jour férié ; une
    source injoignable ne fait pas échouer la tâche (le jour manque, simplement)."""
    with db() as c:
        ferme = bourse.raison_fermeture(auj, bourse._feries_variables(c))
    if ferme:
        return {"etat": "ferme", "raison": ferme}
    try:
        valeurs = telecharger_indices()
    except Exception as e:
        print(f"[indices] récupération échouée — {e}", flush=True)
        return {"etat": "erreur"}
    trouves = {code: valeurs[code] for code in INDICES if code in valeurs}
    with db() as c:
        for code, valeur in trouves.items():
            c.execute("""INSERT INTO indices_historique (indice, date, valeur, source) VALUES (%s, %s, %s, 'auto')
                         ON CONFLICT (indice, date) DO UPDATE SET valeur = EXCLUDED.valeur, source = 'auto'""",
                      (code, auj, valeur))
    return {"etat": "maj", "notes": len(trouves), "introuvables": [c for c in INDICES if c not in trouves]}


# ---------------------------------------------------------------- calcul (sans base)
def valeur_au(valeurs: list, jour: date) -> Optional[tuple]:
    """(date, valeur) la plus récente jusqu'à `jour` inclus dans `valeurs` [(date, valeur)] triée ; None sinon."""
    i = bisect_right(valeurs, (jour, float("inf")))
    return valeurs[i - 1] if i else None


def portefeuille_virtuel(flux: list, valeurs: list) -> dict:
    """Le même argent placé dans l'indice. `flux` : [(date, montant)] des mouvements du compte Bourse,
    apport positif, retrait négatif ; `valeurs` : [(date, valeur)] de l'indice, triée.

    `etat` : 'ok', 'vide' (aucune valeur d'indice) ou 'incomplet' (un mouvement précède la première
    valeur connue : `manque_avant` = date à couvrir par un import). `points` : valeur du portefeuille
    virtuel à chaque date connue de l'indice depuis le premier mouvement."""
    flux = sorted(f for f in flux if f[1])
    if not valeurs:
        return {"etat": "vide", "parts": 0.0, "valeur": None, "date_valeur": None, "points": [], "manque_avant": None}
    manquants = [d for d, _ in flux if valeur_au(valeurs, d) is None]
    if manquants:
        return {"etat": "incomplet", "parts": 0.0, "valeur": None, "date_valeur": valeurs[-1][0], "points": [],
                "manque_avant": min(manquants)}
    parts_au = []          # [(date, parts après ce mouvement)]
    parts = 0.0
    for d, montant in flux:
        parts += montant / valeur_au(valeurs, d)[1]
        parts_au.append((d, parts))
    points = []
    if flux:
        for d, v in valeurs:
            if d < flux[0][0]:
                continue
            i = bisect_right(parts_au, (d, float("inf")))
            points.append({"date": d, "valeur": round(parts_au[i - 1][1] * v, 2)})
    derniere = valeurs[-1]
    return {"etat": "ok", "parts": parts, "valeur": round(parts * derniere[1], 2), "date_valeur": derniere[0],
            "points": points, "manque_avant": None}


def echantillonner(points: list, maximum: int = POINTS_COURBE_MAX) -> list:
    """Au plus `maximum` points, régulièrement espacés, le dernier toujours gardé."""
    if len(points) <= maximum:
        return points
    pas = len(points) / (maximum - 1)
    garde = [points[int(i * pas)] for i in range(maximum - 1)]
    return garde + [points[-1]]


def ecart_import(importees: dict, notees: dict) -> Optional[tuple]:
    """Première date commune où une valeur importée s'écarte de plus de 5 % de la valeur notée
    automatiquement : (date, importée, notée). Sert à refuser le fichier d'un autre indice
    (MASI à la place de MASI Rentabilité Net, par exemple)."""
    return bourse.premier_ecart(importees, notees, ECART_IMPORT_MAX)


# ---------------------------------------------------------------- données
def _valeurs(c, code: str) -> list:
    return [(r["date"], float(r["valeur"])) for r in c.execute(
        "SELECT date, valeur FROM indices_historique WHERE indice = %s ORDER BY date", (code,)).fetchall()]


def _flux_compte() -> list:
    """Mouvements du compte Bourse : apport positif, retrait négatif."""
    return [(m["date_operation"], float(m["montant"]) * (1 if m["type_mouvement"] == "Apport" else -1))
            for m in bourse._mouvements()]


@router.get("")
def lister_indices():
    """Indices suivis, avec ce qui est connu de chacun, et la date du premier apport (à couvrir)."""
    with db() as c:
        stats = {r["indice"]: r for r in c.execute(
            """SELECT indice, COUNT(*) nb, COUNT(*) FILTER (WHERE source = 'import') nb_import, MIN(date) debut, MAX(date) fin,
                      (array_agg(valeur ORDER BY date DESC))[1] derniere
               FROM indices_historique GROUP BY indice""").fetchall()}
    flux = _flux_compte()
    return {"defaut": INDICE_DEFAUT, "premier_mouvement": min((d for d, _ in flux), default=None),
            "indices": [{"code": code, **info, "nb": stats.get(code, {}).get("nb", 0),
                         "nb_import": stats.get(code, {}).get("nb_import", 0),
                         "debut": stats.get(code, {}).get("debut"), "fin": stats.get(code, {}).get("fin"),
                         "derniere": float(stats[code]["derniere"]) if code in stats else None}
                        for code, info in INDICES.items()]}


@router.get("/comparaison")
def comparer(indice: str = Query(INDICE_DEFAUT)):
    """Le compte Bourse comparé au même argent placé dans l'indice : valeur, rendement annuel (même
    calcul que « Performance globale »), écart, et les deux courbes."""
    from routes import patrimoine          # import local : patrimoine importe déjà bourse
    code = _indice(indice)
    auj = aujourdhui()
    with db() as c:
        valeurs = _valeurs(c, code)
        debut_cours = c.execute("SELECT MIN(date) d FROM bourse_prix_historique").fetchone()["d"]
    flux = _flux_compte()
    virtuel = portefeuille_virtuel(flux, valeurs)
    compte = bourse.obtenir_dashboard()
    resultat = {"indice": code, **INDICES[code], "etat": virtuel["etat"] if flux else "sans_apport",
                "manque_avant": virtuel["manque_avant"], "date_valeur": virtuel["date_valeur"],
                "apports_nets": compte.apports_nets, "debut_cours": debut_cours,
                "toi": {"valeur": compte.patrimoine_total, "rendement": compte.rendement_annualise},
                "reference": None, "ecart": None, "points": []}
    if resultat["etat"] != "ok":
        return resultat

    # Même calcul que le rendement du compte : apports en sortie de poche, valeur finale en entrée
    poche = [(d, -m) for d, m in flux]
    rendement = bourse.taux_rendement_annualise(poche + [(auj, virtuel["valeur"])], auj)
    resultat["reference"] = {"valeur": virtuel["valeur"], "rendement": round(rendement, 4) if rendement is not None else None}
    resultat["ecart"] = round(compte.patrimoine_total - virtuel["valeur"], 2)

    # Courbes : le compte (titres + espèces) aux dates connues de l'indice, reconstitué comme la courbe du patrimoine
    points = echantillonner(virtuel["points"])
    if points:
        compte_aux = patrimoine.patrimoine_aux_dates([p["date"] for p in points], patrimoine.charger_operations())
        resultat["points"] = [{"date": p["date"], "indice": p["valeur"], "toi": c["bourse"]} for p, c in zip(points, compte_aux)]
    return resultat


@router.post("/{code}/import")
def importer(code: str, i: ImportIndiceIn):
    """Valeurs passées d'un indice (fichier). Une valeur déjà notée automatiquement est gardée ; si le
    fichier s'en écarte de plus de 5 % un même jour, c'est sans doute un autre indice : tout est refusé."""
    code = _indice(code)
    auj = aujourdhui()
    importees = {v.date: v.valeur for v in i.valeurs if v.date <= auj}
    if not importees:
        raise HTTPException(400, "Aucune valeur datée d'aujourd'hui ou avant")
    with db() as c:
        notees = {r["date"]: float(r["valeur"]) for r in c.execute(
            "SELECT date, valeur FROM indices_historique WHERE indice = %s AND source = 'auto'", (code,)).fetchall()}
        ecart = ecart_import(importees, notees)
        if ecart:
            d, importee, notee = ecart
            fr = lambda v: f"{v:,.2f}".replace(",", " ").replace(".", ",")
            raise HTTPException(400, f"Le {d.strftime('%d/%m/%Y')}, le fichier donne {fr(importee)} mais {INDICES[code]['nom']} "
                                     f"valait {fr(notee)} : ce fichier n'est sans doute pas celui de cet indice.")
        nouvelles = {d: v for d, v in importees.items() if d not in notees}
        with c.cursor() as cur:
            cur.executemany("""INSERT INTO indices_historique (indice, date, valeur, source) VALUES (%s, %s, %s, 'import')
                               ON CONFLICT (indice, date) DO UPDATE SET valeur = EXCLUDED.valeur
                               WHERE indices_historique.source = 'import'""",
                            [(code, d, v) for d, v in nouvelles.items()])
    return {"importees": len(nouvelles), "deja_notees": len(importees) - len(nouvelles),
            "debut": min(importees), "fin": max(importees)}


@router.delete("/{code}/import", status_code=204)
def supprimer_import(code: str):
    """Retire les valeurs importées d'un indice (mauvais fichier) ; celles notées le soir restent."""
    with db() as c:
        c.execute("DELETE FROM indices_historique WHERE indice = %s AND source = 'import'", (_indice(code),))
