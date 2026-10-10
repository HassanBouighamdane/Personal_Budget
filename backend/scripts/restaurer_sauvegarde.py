# -*- coding: utf-8 -*-
"""
Restaure une sauvegarde complète (fichier .json ou .json.gz téléchargé depuis Paramètres, ou
reçu par e-mail / Telegram) dans la base configurée par DATABASE_URL (backend/.env).

⚠️  Le contenu actuel des tables sauvegardées est REMPLACÉ. Les comptes et les sessions ne
sont pas touchés. Tout se fait dans une seule transaction : en cas d'erreur, rien ne change.

    cd backend
    python scripts/restaurer_sauvegarde.py chemin/vers/mon-budget-2026-10-01.json.gz

Sur une base neuve, le schéma est créé d'abord (comme au démarrage de l'application).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sauvegarde
from config import DATABASE_URL
from database import db, init_db


def principal():
    if len(sys.argv) < 2:
        sys.exit("Usage : python scripts/restaurer_sauvegarde.py <fichier> [--oui]")
    try:
        donnees = sauvegarde.lire(Path(sys.argv[1]).read_bytes())
    except (OSError, ValueError) as e:
        sys.exit(f"Lecture impossible : {e}")
    nb = sum(len(lignes) for lignes in donnees["tables"].values())
    print(f"Sauvegarde du {donnees.get('cree_le', '?')} : {len(donnees['tables'])} tables, {nb} lignes")
    print(f"Base visée : {DATABASE_URL.split('@')[-1]}")
    if "--oui" not in sys.argv and input("Remplacer le contenu de cette base ? Tape « oui » : ").strip().lower() != "oui":
        sys.exit("Abandon : rien n'a été modifié.")
    init_db()
    with db() as c:
        bilan = sauvegarde.restaurer(c, donnees)
    for table, lignes in bilan.items():
        print(f"  {table:<28} {lignes:>6} lignes")
    ignorees = sorted(set(donnees["tables"]) - set(bilan))
    if ignorees:
        print("Tables absentes de cette base, ignorées :", ", ".join(ignorees))
    print("Restauration terminée.")


if __name__ == "__main__":
    principal()
