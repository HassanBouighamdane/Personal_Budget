# -*- coding: utf-8 -*-
"""Sauvegarde complète : toutes les tables de l'application dans un seul fichier JSON, et
restauration de ce fichier (script scripts/restaurer_sauvegarde.py).

Les tables sont découvertes dans la base : une table ajoutée plus tard est sauvegardée sans
rien changer ici. Les comptes et les sessions n'en font pas partie (aucun mot de passe, même
haché, ne sort de la base)."""
import gzip
import json
from datetime import date, datetime
from decimal import Decimal

from psycopg import sql

from config import aujourdhui
from database import CLES_ETRANGERES, db

TABLES_EXCLUES = {"utilisateurs", "sessions", "cron_journal", "telegram_messages"}
FORMAT = 1
APPLICATION = "Carnet"
# Nom de l'application avant son renommage : ses sauvegardes restent lisibles
ANCIENS_NOMS = {"Mon Budget"}


def _tables(c) -> list:
    rows = c.execute("""SELECT table_name FROM information_schema.tables
                        WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
                        ORDER BY table_name""").fetchall()
    return [r["table_name"] for r in rows if r["table_name"] not in TABLES_EXCLUES]


def _json(valeur):
    """Types que json ne connaît pas : dates en ISO, montants NUMERIC en texte (valeur exacte)."""
    if isinstance(valeur, (date, datetime)):
        return valeur.isoformat()
    if isinstance(valeur, Decimal):
        return str(valeur)
    raise TypeError(f"Type non sérialisable : {type(valeur).__name__}")


def exporter() -> dict:
    """{"application", "format", "cree_le", "tables": {nom: [lignes]}} — une seule transaction,
    donc un état cohérent de toutes les tables."""
    with db() as c:
        tables = {t: c.execute(sql.SQL("SELECT * FROM {} ORDER BY 1").format(sql.Identifier(t))).fetchall()
                  for t in _tables(c)}
    return {"application": APPLICATION, "format": FORMAT, "cree_le": datetime.now().isoformat(timespec="seconds"),
            "tables": tables}


def en_json(donnees: dict) -> bytes:
    return json.dumps(donnees, default=_json, ensure_ascii=False, indent=1).encode()


def fichier_compresse() -> tuple:
    """(nom, contenu) de la sauvegarde du jour, compressée : pour l'envoi automatique."""
    return f"carnet-{aujourdhui().isoformat()}.json.gz", gzip.compress(en_json(exporter()))


def lire(contenu: bytes) -> dict:
    """Fichier de sauvegarde (.json ou .json.gz) → données ; ValueError s'il n'en est pas un."""
    if contenu[:2] == b"\x1f\x8b":
        contenu = gzip.decompress(contenu)
    donnees = json.loads(contenu)
    if not isinstance(donnees, dict) or donnees.get("application") not in {APPLICATION} | ANCIENS_NOMS or not isinstance(donnees.get("tables"), dict):
        raise ValueError("Ce fichier n'est pas une sauvegarde de Carnet")
    if donnees.get("format", 0) > FORMAT:
        raise ValueError("Sauvegarde faite par une version plus récente de l'application")
    return donnees


def _ordre_d_insertion(c, tables: list) -> list:
    """Tables parentes avant celles qui les référencent (clés étrangères)."""
    liens = c.execute("""SELECT enfant.relname enfant, parent.relname parent
                         FROM pg_constraint k
                         JOIN pg_class enfant ON enfant.oid = k.conrelid
                         JOIN pg_class parent ON parent.oid = k.confrelid
                         WHERE k.contype = 'f' AND k.connamespace = current_schema()::regnamespace""").fetchall()
    parents = {t: {l["parent"] for l in liens if l["enfant"] == t and l["parent"] in tables and l["parent"] != t} for t in tables}
    ordre = []
    while parents:
        prets = sorted(t for t, p in parents.items() if not p - set(ordre))
        if not prets:
            raise RuntimeError("Références circulaires entre les tables")
        ordre += prets
        for t in prets:
            del parents[t]
    return ordre


def restaurer(c, donnees: dict) -> dict:
    """Remplace le contenu des tables présentes dans la sauvegarde ET dans la base, sur la
    connexion `c` (donc dans sa transaction : en cas d'erreur, rien n'est modifié). Une colonne
    ou une table absente de la base est ignorée ; une colonne absente du fichier prend sa valeur
    par défaut. Renvoie {table: nombre de lignes restaurées}."""
    tables = [t for t in _tables(c) if t in donnees["tables"]]
    if not tables:
        raise ValueError("Aucune table de la sauvegarde n'existe dans cette base")
    c.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY").format(sql.SQL(", ").join(map(sql.Identifier, tables))))
    bilan = {}
    for t in _ordre_d_insertion(c, tables):
        colonnes_base = {r["column_name"]: r["data_type"] for r in c.execute(
            """SELECT column_name, data_type FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = %s""", (t,)).fetchall()}
        lignes = donnees["tables"][t]
        if lignes:
            colonnes = [k for k in lignes[0] if k in colonnes_base]
            requete = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(t), sql.SQL(", ").join(map(sql.Identifier, colonnes)),
                sql.SQL(", ").join(sql.Placeholder() * len(colonnes)))
            # Sauvegarde d'avant les clés étrangères : un nom vide (revenu sans source, livre sans
            # genre) devient NULL, comme dans la base actuelle
            vides = {col for table, col, *_ in CLES_ETRANGERES if table == t}
            valeur = lambda l, k: None if k in vides and isinstance(l.get(k), str) and not l[k].strip() else l.get(k)
            c.cursor().executemany(requete, [[valeur(l, k) for k in colonnes] for l in lignes])
        bilan[t] = len(lignes)
        # Les identifiants automatiques repartent après le plus grand restauré
        for r in c.execute("""SELECT column_name, pg_get_serial_sequence(%s, column_name) seq FROM information_schema.columns
                              WHERE table_schema = current_schema() AND table_name = %s""", (t, t)).fetchall():
            if r["seq"]:
                c.execute(sql.SQL("SELECT setval(%s, COALESCE((SELECT MAX({}) FROM {}), 1))").format(
                    sql.Identifier(r["column_name"]), sql.Identifier(t)), (r["seq"],))
    return bilan
