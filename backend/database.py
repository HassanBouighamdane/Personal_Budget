# -*- coding: utf-8 -*-
"""Accès à la base PostgreSQL : connexion et initialisation du schéma."""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from config import (DATABASE_URL, CATEGORIES_DEFAUT, SOURCES_DEFAUT,
                    PAIEMENTS_DEFAUT, ADMIN_UTILISATEUR, ADMIN_MOT_DE_PASSE)

# Sociétés cotées à la Bourse de Casablanca (BVC) — (code, nom, secteur)
# Source : african-markets.com/fr/bourse/bvc/listed-companies, relevé juillet 2026.
# La cote évolue (introductions, radiations) : ajuste cette liste si besoin depuis
# l'onglet Paramètres > Titres, ou modifie directement la table bourse_titres.
TITRES_BVC_DEFAUT = [
    ("AFM", "AFMA", "Financials"),
    ("AFI", "Afric Industries", "Industrials"),
    ("GAZ", "Afriquia Gaz", "Oil & Gas"),
    ("AGM", "AGMA", "Financials"),
    ("ADI", "Alliances", "Financials"),
    ("ALM", "Aluminium Du Maroc", "Industrials"),
    ("ATL", "AtlantaSanad", "Financials"),
    ("ATW", "Attijariwafa Bank", "Financials"),
    ("ATH", "Auto Hall", "Consumer Services"),
    ("NEJ", "Auto Nejma", "Consumer Services"),
    ("BAL", "Balima", "Financials"),
    ("BCP", "BCP", "Financials"),
    ("BOA", "Bank of Africa (BMCE)", "Financials"),
    ("BCI", "BMCI", "Financials"),
    ("SBM", "Société des Boissons du Maroc", "Consumer Goods"),
    ("CRS", "Cartier Saada", "Consumer Goods"),
    ("CDM", "Credit du Maroc", "Financials"),
    ("CIH", "CIH Bank", "Financials"),
    ("CMA", "Ciments du Maroc", "Industrials"),
    ("COL", "Colorado", "Basic Materials"),
    ("CSR", "Cosumar", "Consumer Goods"),
    ("CTM", "CTM", "Consumer Services"),
    ("DARI", "Dari Couspate", "Consumer Goods"),
    ("DLM", "Delattre Levivier Maroc", "Industrials"),
    ("DHO", "Delta Holding", "Industrials"),
    ("DIS", "Diac Salaf", "Financials"),
    ("DWAY", "Disway", "Technology"),
    ("ADH", "Douja Prom Addoha", "Financials"),
    ("NAKL", "Ennakl", "Consumer Services"),
    ("EQD", "Eqdom", "Financials"),
    ("FBR", "Fenie Brossette", "Industrials"),
    ("HOL", "Holcim (Maroc)", "Industrials"),
    ("HPS", "HPS", "Technology"),
    ("IBMC", "IB Maroc.Com", "Technology"),
    ("INV", "Involys", "Technology"),
    ("IAM", "Maroc Telecom", "Telecom"),
    ("JET", "Jet Contractors", "Industrials"),
    ("LBV", "Label Vie", "Consumer Services"),
    ("LHM", "LafargeHolcim Maroc", "Industrials"),
    ("LES", "Lesieur Cristal", "Consumer Goods"),
    ("M2M", "M2M Group", "Technology"),
    ("MOX", "Maghreb Oxygene", "Basic Materials"),
    ("MAB", "Maghrebail", "Financials"),
    ("MNG", "Managem", "Basic Materials"),
    ("MLE", "Maroc Leasing", "Financials"),
    ("MDP", "Med Paper", "Basic Materials"),
    ("MIC", "Microdata", "Technology"),
    ("CMT", "Miniere Touissit", "Basic Materials"),
    ("OUL", "Oulmes", "Consumer Goods"),
    ("PRO", "Promopharm S.A.", "Health Care"),
    ("SRM", "Realis. Mecaniques (SRM)", "Industrials"),
    ("REB", "Rebab Company", "Basic Materials"),
    ("RDS", "Residences Dar Saada", "Financials"),
    ("RIS", "Risma", "Consumer Services"),
    ("S2M", "S.M Monetique", "Technology"),
    ("SAHM", "Sanlam Maroc", "Financials"),
    ("SLF", "Salafin", "Financials"),
    ("SAM", "Samir", "Oil & Gas"),
    ("SMI", "SMI", "Basic Materials"),
    ("SNP", "SNEP", "Basic Materials"),
    ("SID", "Sonasid", "Basic Materials"),
    ("SOT", "Sothema", "Health Care"),
    ("SNA", "Stokvis Nord Afrique", "Industrials"),
    ("STR", "Stroc Industrie", "Industrials"),
    ("TQM", "Taqa Morocco", "Utilities"),
    ("TMA", "TotalEnergies Marketing Maroc", "Oil & Gas"),
    ("UMR", "Unimer", "Consumer Goods"),
    ("WAA", "Wafa Assurance", "Financials"),
    ("ZDJ", "Zellidja S.A", "Basic Materials"),
    ("MSA", "Marsa Maroc", "Industrials"),
    ("IMO", "Immorente Invest", "Financials"),
    ("MUT", "Mutandis SCA", "Consumer Goods"),
    ("ARD", "Aradei Capital", "Financials"),
    ("TGC", "TGCC", "Industrials"),
    ("DYT", "Disty Technologies", "Technology"),
    ("AKT", "Akdital", "Health Care"),
    ("CFG", "CFG Bank", "Financials"),
    ("CMG", "CMGP Group", "Consumer Goods"),
    ("VCN", "Vicenne", "Technology"),
    ("CAP", "Cash Plus", "Technology"),
    ("T2S", "T2S", "Health Care"),
]

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

        -- ================================================================
        -- Bourse — schéma final (Action / Obligation / OPCVM / IPO)
        -- ================================================================
        CREATE TABLE IF NOT EXISTS bourse_parametres (
            id                            SERIAL PRIMARY KEY,
            -- Actions cotées
            taux_courtage_action          NUMERIC(6,4)  NOT NULL DEFAULT 0.0060,   -- 0.60 %
            taux_reglement_livraison      NUMERIC(6,4)  NOT NULL DEFAULT 0.0020,   -- 0.20 %
            taux_impot_bourse_action      NUMERIC(6,4)  NOT NULL DEFAULT 0.0010,   -- 0.10 %
            taux_tva                      NUMERIC(6,4)  NOT NULL DEFAULT 0.1000,   -- 10 %, sur le courtage uniquement
            -- Obligations cotées
            commission_fixe_obligation    NUMERIC(10,2) NOT NULL DEFAULT 110,
            taux_impot_bourse_obligation  NUMERIC(8,6)  NOT NULL DEFAULT 0.00005,  -- 0.005 %
            -- Droits de garde (frais trimestriels sur encours, hors transactions)
            taux_droit_garde_annuel       NUMERIC(6,4)  NOT NULL DEFAULT 0.0015,   -- 0.15 %
            droit_garde_min_trimestriel   NUMERIC(10,2) NOT NULL DEFAULT 13.77,
            -- IPO / souscriptions (introduction en bourse, augmentation de capital)
            taux_souscription_ipo         NUMERIC(6,4)  NOT NULL DEFAULT 0.0020,
            min_souscription_ipo          NUMERIC(10,2) NOT NULL DEFAULT 22,
            -- OPCVM (taux par défaut ; varient fortement par fonds)
            droits_entree_opcvm_defaut    NUMERIC(6,4)  NOT NULL DEFAULT 0,
            droits_sortie_opcvm_defaut    NUMERIC(6,4)  NOT NULL DEFAULT 0,
            -- Fiscalité
            taux_tpcvm                    NUMERIC(6,4)  NOT NULL DEFAULT 0.1500    -- 15 %
        );

        CREATE TABLE IF NOT EXISTS bourse_transactions (
            id                        SERIAL PRIMARY KEY,
            date_operation            DATE NOT NULL,
            titre                     VARCHAR(60) NOT NULL,
            isin                      VARCHAR(20),
            type_instrument           VARCHAR(15) NOT NULL DEFAULT 'Action'
                                          CHECK (type_instrument IN ('Action','Obligation','OPCVM','IPO')),
            type_operation            VARCHAR(10) NOT NULL CHECK (type_operation IN ('Achat', 'Vente')),
            quantite                  NUMERIC(14,4) NOT NULL CHECK (quantite > 0),
            cours_unitaire            NUMERIC(14,4) NOT NULL CHECK (cours_unitaire >= 0),
            -- Taux figés à la saisie (traçabilité) — NULL si non applicable au type d'instrument
            taux_courtage             NUMERIC(6,4),    -- Action
            taux_reglement_livraison  NUMERIC(6,4),    -- Action
            taux_impot_bourse         NUMERIC(8,6),    -- Action ou Obligation
            taux_tva                  NUMERIC(6,4),    -- Action
            commission_fixe           NUMERIC(10,2),   -- Obligation
            taux_droits_opcvm         NUMERIC(6,4),    -- OPCVM
            taux_souscription         NUMERIC(6,4),    -- IPO
            min_souscription          NUMERIC(10,2),   -- IPO
            autres_frais              NUMERIC(14,4) NOT NULL DEFAULT 0,
            cree_le                   TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_bourse_tx_titre ON bourse_transactions (titre);
        CREATE INDEX IF NOT EXISTS idx_bourse_tx_date  ON bourse_transactions (date_operation);

        CREATE TABLE IF NOT EXISTS bourse_prix (
            titre        VARCHAR(60) PRIMARY KEY,
            cours_actuel NUMERIC(14,4) NOT NULL DEFAULT 0,
            maj_le       TIMESTAMP NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS bourse_titres (
            id      SERIAL PRIMARY KEY,
            code    VARCHAR(15) UNIQUE NOT NULL,
            nom     VARCHAR(100) NOT NULL,
            secteur VARCHAR(50) DEFAULT '',
            actif   INTEGER NOT NULL DEFAULT 1
        );

        """)

        # Ajout additif (n'affecte aucune donnée existante) : permet de choisir, pour
        # chaque transaction IPO, entre la structure "Action" (courtage+R/L+impôt bourse)
        # et la structure "Souscription" forfaitaire.
        c.execute("""
        ALTER TABLE bourse_transactions ADD COLUMN IF NOT EXISTS structure_ipo VARCHAR(15);
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

        if c.execute("SELECT COUNT(*) n FROM bourse_parametres").fetchone()["n"] == 0:
            c.execute("INSERT INTO bourse_parametres DEFAULT VALUES")
        if c.execute("SELECT COUNT(*) n FROM bourse_titres").fetchone()["n"] == 0:
            with c.cursor() as cur:
                cur.executemany("INSERT INTO bourse_titres(code,nom,secteur) VALUES(%s,%s,%s)", TITRES_BVC_DEFAUT)