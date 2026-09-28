# -*- coding: utf-8 -*-
"""Accès à la base PostgreSQL : connexion et initialisation du schéma."""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import (DATABASE_URL, CATEGORIES_DEFAUT, SOURCES_DEFAUT,
                    ADMIN_UTILISATEUR, ADMIN_MOT_DE_PASSE)

# Un seul pool pour toute l'application (au lieu d'ouvrir une connexion TCP par
# requête) : chaque endpoint ouvre plusieurs `with db()` (jusqu'à 3-4 pour le
# dashboard Bourse), ce qui multipliait inutilement les connexions.
_pool = ConnectionPool(
    conninfo=DATABASE_URL, min_size=1, max_size=10,
    kwargs={"row_factory": dict_row}, open=True,
    # L'hébergeur de la base coupe les connexions restées inactives : sans vérification,
    # le pool prêterait une connexion morte et la requête échouerait en 500. `check`
    # teste chaque connexion avant de la prêter et la remplace si elle est cassée.
    check=ConnectionPool.check_connection,
    # Ferme d'elle-même une connexion inactive depuis 5 min, avant que le serveur ne la coupe.
    max_idle=300,
)

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
    """Connexion PostgreSQL (tirée du pool) avec commit automatique en sortie.
    En cas d'exception, `pool.connection()` fait un rollback avant de remettre
    la connexion dans le pool — indispensable ici puisque la connexion est
    réutilisée par une future requête plutôt que fermée."""
    with _pool.connection() as conn:
        yield conn
        conn.commit()

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
        -- Types de paiement : fonctionnalité retirée (29/09/2026). Table et colonne
        -- depenses.paiement conservées pour l'historique déjà saisi, plus lues ni écrites.
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
        -- Aucun frais n'est calculé automatiquement (prix net saisi directement) :
        -- seule la TPCVM reste un calcul indépendant des frais de transaction
        -- (cf. module routes/bourse.py). Les droits de garde se saisissent
        -- manuellement dans le journal des frais de compte (bourse_frais).
        -- ================================================================
        CREATE TABLE IF NOT EXISTS bourse_parametres (
            id                            SERIAL PRIMARY KEY,
            -- Fiscalité
            taux_tpcvm                    NUMERIC(6,4)  NOT NULL DEFAULT 0.1500    -- 15 %, sur les plus-values de cession
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

        -- Dividendes : montant NET déjà reçu, saisi directement (aucun calcul de
        -- retenue à la source — l'utilisateur fait ce calcul lui-même en amont).
        CREATE TABLE IF NOT EXISTS bourse_dividendes (
            id             SERIAL PRIMARY KEY,
            date_operation DATE NOT NULL,
            titre          VARCHAR(60) NOT NULL,
            montant        NUMERIC(14,4) NOT NULL CHECK (montant >= 0),
            cree_le        TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_bourse_div_titre ON bourse_dividendes (titre);
        CREATE INDEX IF NOT EXISTS idx_bourse_div_date  ON bourse_dividendes (date_operation);

        -- Frais de compte / courtage récurrents ou ponctuels, indépendants d'une
        -- transaction précise (ex : abonnement mensuel Wafabourse, frais de tenue de compte).
        CREATE TABLE IF NOT EXISTS bourse_frais (
            id             SERIAL PRIMARY KEY,
            date_operation DATE NOT NULL,
            libelle        VARCHAR(200) NOT NULL DEFAULT '',
            montant        NUMERIC(14,4) NOT NULL CHECK (montant >= 0),
            cree_le        TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_bourse_frais_date ON bourse_frais (date_operation);

        -- Mouvements d'argent entre la banque (Budget) et le compte Bourse :
        -- un apport ou un retrait est un TRANSFERT, ni une dépense ni un revenu.
        CREATE TABLE IF NOT EXISTS bourse_mouvements (
            id                SERIAL PRIMARY KEY,
            date_operation    DATE NOT NULL,
            type_mouvement    VARCHAR(10) NOT NULL CHECK (type_mouvement IN ('Apport', 'Retrait')),
            montant           NUMERIC(14,4) NOT NULL CHECK (montant > 0),
            libelle           VARCHAR(200) NOT NULL DEFAULT '',
            cree_le           TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_bourse_mvt_date ON bourse_mouvements (date_operation);

        """)

        # ------------------------------------------------------------------
        # Migration additive : simplification du module Bourse — les frais
        # (courtage, TVA, impôt de bourse...) et la retenue sur dividendes ne
        # sont plus calculés automatiquement ; l'utilisateur saisit directement
        # le prix net (achat/vente) et le montant net des dividendes. Les
        # anciennes colonnes de taux figés restent en base (non détruites) mais
        # ne sont plus lues par l'application.
        # ------------------------------------------------------------------
        # Colonne requise par la migration ci-dessous, quelle que soit l'ancienneté
        # de l'installation (peut être absente si bourse_parametres existait déjà
        # avant l'ajout du module Dividendes).
        c.execute("""
        ALTER TABLE bourse_parametres ADD COLUMN IF NOT EXISTS taux_retenue_source_dividendes NUMERIC(6,4) NOT NULL DEFAULT 0.15;
        """)

        ancienne_colonne = c.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'bourse_dividendes' AND column_name = 'montant_brut'
        """).fetchone()
        if ancienne_colonne:
            c.execute("ALTER TABLE bourse_dividendes ADD COLUMN IF NOT EXISTS montant NUMERIC(14,4)")
            c.execute("""
                UPDATE bourse_dividendes d SET montant = d.montant_brut * (1 - COALESCE(d.taux_retenue_source, p.taux_retenue_source_dividendes))
                FROM bourse_parametres p WHERE d.montant IS NULL
            """)
            c.execute("ALTER TABLE bourse_dividendes ALTER COLUMN montant SET NOT NULL")
            c.execute("ALTER TABLE bourse_dividendes DROP COLUMN montant_brut")
            c.execute("ALTER TABLE bourse_dividendes DROP COLUMN IF EXISTS taux_retenue_source")

        # Nettoyage : anciennes colonnes de taux figés, plus jamais lues depuis la
        # simplification du module Bourse (aucun frais n'est calculé automatiquement).
        # Idem pour les droits de garde : ne sont plus estimés automatiquement, à
        # saisir manuellement dans le journal des frais de compte (bourse_frais).
        # DROP COLUMN IF EXISTS est idempotent — sans effet dès le premier passage
        # sur une base déjà nettoyée, et sans effet non plus sur une base neuve
        # (le schéma ci-dessus ne crée plus ces colonnes).
        c.execute("""
            ALTER TABLE bourse_parametres
                DROP COLUMN IF EXISTS taux_courtage_action,
                DROP COLUMN IF EXISTS taux_reglement_livraison,
                DROP COLUMN IF EXISTS taux_impot_bourse_action,
                DROP COLUMN IF EXISTS taux_tva,
                DROP COLUMN IF EXISTS commission_fixe_obligation,
                DROP COLUMN IF EXISTS taux_impot_bourse_obligation,
                DROP COLUMN IF EXISTS taux_souscription_ipo,
                DROP COLUMN IF EXISTS min_souscription_ipo,
                DROP COLUMN IF EXISTS droits_entree_opcvm_defaut,
                DROP COLUMN IF EXISTS droits_sortie_opcvm_defaut,
                DROP COLUMN IF EXISTS taux_retenue_source_dividendes,
                DROP COLUMN IF EXISTS taux_droit_garde_annuel,
                DROP COLUMN IF EXISTS droit_garde_min_trimestriel
        """)
        c.execute("""
            ALTER TABLE bourse_transactions
                DROP COLUMN IF EXISTS taux_courtage,
                DROP COLUMN IF EXISTS taux_reglement_livraison,
                DROP COLUMN IF EXISTS taux_impot_bourse,
                DROP COLUMN IF EXISTS taux_tva,
                DROP COLUMN IF EXISTS commission_fixe,
                DROP COLUMN IF EXISTS taux_droits_opcvm,
                DROP COLUMN IF EXISTS taux_souscription,
                DROP COLUMN IF EXISTS min_souscription,
                DROP COLUMN IF EXISTS structure_ipo
        """)

        with c.cursor() as cur:
            if c.execute("SELECT COUNT(*) n FROM categories").fetchone()["n"] == 0:
                cur.executemany("INSERT INTO categories(nom,budget) VALUES(%s,%s)", CATEGORIES_DEFAUT)
            if c.execute("SELECT COUNT(*) n FROM sources_revenus").fetchone()["n"] == 0:
                cur.executemany("INSERT INTO sources_revenus(nom) VALUES(%s)", SOURCES_DEFAUT)
        c.execute("INSERT INTO params(cle,valeur) VALUES('objectif_epargne',5000) ON CONFLICT DO NOTHING")
        if c.execute("SELECT COUNT(*) n FROM utilisateurs").fetchone()["n"] == 0:
            if not ADMIN_UTILISATEUR or not ADMIN_MOT_DE_PASSE:
                raise RuntimeError(
                    "Aucun compte utilisateur en base et ADMIN_UTILISATEUR / ADMIN_MOT_DE_PASSE "
                    "manquant(s) dans backend/.env : impossible de créer le compte administrateur "
                    "au premier démarrage. Renseigne ces deux variables et relance."
                )
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