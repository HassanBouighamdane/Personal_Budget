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

        CREATE TABLE IF NOT EXISTS bourse_parametres (
            id              SERIAL PRIMARY KEY,
            taux_commission NUMERIC(6,4) NOT NULL DEFAULT 0.0060,   -- 0.60 %
            taux_tva        NUMERIC(6,4) NOT NULL DEFAULT 0.1000,   -- 10 %
            taux_tpcvm      NUMERIC(6,4) NOT NULL DEFAULT 0.1500    -- 15 %
        );
        
        CREATE TABLE IF NOT EXISTS bourse_transactions (
            id              SERIAL PRIMARY KEY,
            date_operation  DATE NOT NULL,
            titre           VARCHAR(60) NOT NULL,
            isin            VARCHAR(20),
            type_operation  VARCHAR(10) NOT NULL CHECK (type_operation IN ('Achat', 'Vente')),
            quantite        NUMERIC(14,4) NOT NULL CHECK (quantite > 0),
            cours_unitaire  NUMERIC(14,4) NOT NULL CHECK (cours_unitaire >= 0),
            taux_commission NUMERIC(6,4)  NOT NULL,   -- copié depuis les paramètres au moment de la saisie (traçabilité)
            taux_tva        NUMERIC(6,4)  NOT NULL,
            autres_frais    NUMERIC(14,4) NOT NULL DEFAULT 0,
            cree_le         TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_bourse_tx_titre ON bourse_transactions (titre);
        CREATE INDEX IF NOT EXISTS idx_bourse_tx_date  ON bourse_transactions (date_operation);
        
        CREATE TABLE IF NOT EXISTS bourse_prix (
            titre        VARCHAR(60) PRIMARY KEY,
            cours_actuel NUMERIC(14,4) NOT NULL DEFAULT 0,
            maj_le       TIMESTAMP NOT NULL DEFAULT now()
        );

        INSERT INTO bourse_parametres (taux_commission, taux_tva, taux_tpcvm)
        SELECT 0.0060, 0.1000, 0.1500
        WHERE NOT EXISTS (SELECT 1 FROM bourse_parametres);
        
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