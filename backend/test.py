# -*- coding: utf-8 -*-
"""
Supprime toutes les tables du module Bourse (bourse_transactions, bourse_prix,
bourse_parametres) — utile pour repartir sur un schéma propre après plusieurs
migrations successives.

⚠️  Supprime aussi toutes les données Bourse déjà saisies (transactions, cours,
paramètres). N'affecte PAS le reste de l'application (dépenses, revenus,
catégories, utilisateurs...).

Usage :
    cd backend
    python supprimer_bourse.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import db

TABLES_BOURSE = ["bourse_transactions", "bourse_prix", "bourse_parametres"]


def supprimer_tables_bourse():
    with db() as conn:
        for table in TABLES_BOURSE:
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            print(f"  ✓ Table {table} supprimée (si elle existait)")


if __name__ == "__main__":
    reponse = input(
        "Ceci va supprimer DÉFINITIVEMENT toutes les tables et données du module "
        "Bourse. Continuer ? (tapez 'oui' pour confirmer) : "
    )
    if reponse.strip().lower() == "oui":
        supprimer_tables_bourse()
        print("\nTerminé. Relance `python app.py` : les tables seront recréées "
              "automatiquement avec le schéma final au démarrage.")
    else:
        print("Annulé — aucune table supprimée.")