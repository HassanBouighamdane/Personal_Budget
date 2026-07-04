# -*- coding: utf-8 -*-
"""Accès à la base PostgreSQL : connexion et initialisation du schéma."""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from config import (DATABASE_URL, CATEGORIES_DEFAUT, SOURCES_DEFAUT,
                    PAIEMENTS_DEFAUT, ADMIN_UTILISATEUR, ADMIN_MOT_DE_PASSE)

@contextmanager
def db():
    """Connexion PostgreSQL avec commit automatique en sortie."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Crée les tables si besoin, insère les valeurs par défaut et le compte admin."""
    from securite import hacher_mdp   # import local pour éviter un import circulaire
    with db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            nom TEXT UNIQUE NOT NULL,
            budget DOUBLE PRECISION NOT NULL DEFAULT 0,
            actif INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS depenses (
            id SERIAL PRIMARY KEY,
            date TEXT NOT NULL,
            categorie TEXT NOT NULL,
            description TEXT DEFAULT '',
            montant DOUBLE PRECISION NOT NULL,
            paiement TEXT DEFAULT '',
            cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS revenus (
            id SERIAL PRIMARY KEY,
            date TEXT NOT NULL,
            source TEXT DEFAULT '',
            montant DOUBLE PRECISION NOT NULL,
            cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS params (
            cle TEXT PRIMARY KEY,
            valeur DOUBLE PRECISION NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources_revenus (
            id SERIAL PRIMARY KEY,
            nom TEXT UNIQUE NOT NULL,
            actif INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS paiements (
            id SERIAL PRIMARY KEY,
            nom TEXT UNIQUE NOT NULL,
            actif INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id SERIAL PRIMARY KEY,
            nom TEXT UNIQUE NOT NULL,
            mdp_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
            expire TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_depenses_date ON depenses(date);
        CREATE INDEX IF NOT EXISTS idx_revenus_date ON revenus(date);
        """)
        with c.cursor() as cur:
            if c.execute("SELECT COUNT(*) n FROM categories").fetchone()["n"] == 0:
                cur.executemany("INSERT INTO categories(nom,budget) VALUES(%s,%s)", CATEGORIES_DEFAUT)
            if c.execute("SELECT COUNT(*) n FROM sources_revenus").fetchone()["n"] == 0:
                cur.executemany("INSERT INTO sources_revenus(nom) VALUES(%s)", SOURCES_DEFAUT)
            if c.execute("SELECT COUNT(*) n FROM paiements").fetchone()["n"] == 0:
                cur.executemany("INSERT INTO paiements(nom) VALUES(%s)", PAIEMENTS_DEFAUT)
        c.execute("INSERT INTO params(cle,valeur) VALUES('objectif_epargne',5000) ON CONFLICT DO NOTHING")
        if c.execute("SELECT COUNT(*) n FROM utilisateurs").fetchone()["n"] == 0:
            c.execute("INSERT INTO utilisateurs(nom,mdp_hash) VALUES(%s,%s)",
                      (ADMIN_UTILISATEUR, hacher_mdp(ADMIN_MOT_DE_PASSE)))
            if ADMIN_MOT_DE_PASSE == "admin":
                print("⚠️  Compte créé avec le mot de passe par défaut 'admin'."
                      " Change-le immédiatement dans Paramètres !")