# -*- coding: utf-8 -*-
"""Accès à la base PostgreSQL : connexion et initialisation du schéma."""
from contextlib import contextmanager

from fastapi import HTTPException
from psycopg import sql
from psycopg.errors import ForeignKeyViolation
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import (DATABASE_URL, VERSION_DEPLOYEE, CATEGORIES_DEFAUT, SOURCES_DEFAUT,
                    ADMIN_UTILISATEUR, ADMIN_MOT_DE_PASSE, GENRES_DEFAUT,
                    OBJECTIF_LECTURE_ANNUEL_DEFAUT, OBJECTIF_LECTURE_MENSUEL_DEFAUT)

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
# Source des titres : african-markets.com/fr/bourse/bvc/listed-companies, relevé juillet 2026.
# Secteurs : classification sectorielle de la Bourse de Casablanca (relevé Le Matin, 28/09/2026).
# La cote évolue (introductions, radiations) : ajuste cette liste si besoin depuis
# l'onglet Paramètres > Titres, ou modifie directement la table bourse_titres.
TITRES_BVC_DEFAUT = [
    ("AFM", "AFMA", "Assurances"),
    ("AFI", "Afric Industries", "Bâtiment et Matériaux de Construction"),
    ("GAZ", "Afriquia Gaz", "Pétrole et Gaz"),
    ("AGM", "AGMA", "Assurances"),
    ("ADI", "Alliances", "Participation et promotion immobilières"),
    ("ALM", "Aluminium Du Maroc", "Bâtiment et Matériaux de Construction"),
    ("ATL", "AtlantaSanad", "Assurances"),
    ("ATW", "Attijariwafa Bank", "Banques"),
    ("ATH", "Auto Hall", "Distributeurs"),
    ("NEJ", "Auto Nejma", "Distributeurs"),
    ("BAL", "Balima", "Sociétés de placement immobilier"),
    ("BCP", "BCP", "Banques"),
    ("BOA", "Bank of Africa (BMCE)", "Banques"),
    ("BCI", "BMCI", "Banques"),
    ("SBM", "Société des Boissons du Maroc", "Boissons"),
    ("CRS", "Cartier Saada", "Agroalimentaire et Production"),
    ("CDM", "Credit du Maroc", "Banques"),
    ("CIH", "CIH Bank", "Banques"),
    ("CMA", "Ciments du Maroc", "Bâtiment et Matériaux de Construction"),
    ("COL", "Colorado", "Bâtiment et Matériaux de Construction"),
    ("CSR", "Cosumar", "Agroalimentaire et Production"),
    ("CTM", "CTM", "Services de transport"),
    ("DARI", "Dari Couspate", "Agroalimentaire et Production"),
    ("DLM", "Delattre Levivier Maroc", "Ingénieries et Biens d'Equipement Industriels"),
    ("DHO", "Delta Holding", "Sociétés de Portefeuilles - Holdings"),
    ("DIS", "Diac Salaf", "Sociétés de financement et Autres Activités Financières"),
    ("DWAY", "Disway", "Matériels, Logiciels et Services Informatiques"),
    ("ADH", "Douja Prom Addoha", "Participation et promotion immobilières"),
    ("NAKL", "Ennakl", "Distributeurs"),
    ("EQD", "Eqdom", "Sociétés de financement et Autres Activités Financières"),
    ("FBR", "Fenie Brossette", "Distributeurs"),
    ("HOL", "Holcim (Maroc)", "Bâtiment et Matériaux de Construction"),
    ("HPS", "HPS", "Matériels, Logiciels et Services Informatiques"),
    ("IBMC", "IB Maroc.Com", "Matériels, Logiciels et Services Informatiques"),
    ("INV", "Involys", "Matériels, Logiciels et Services Informatiques"),
    ("IAM", "Maroc Telecom", "Télécommunications"),
    ("JET", "Jet Contractors", "Bâtiment et Matériaux de Construction"),
    ("LBV", "Label Vie", "Distributeurs"),
    ("LHM", "LafargeHolcim Maroc", "Bâtiment et Matériaux de Construction"),
    ("LES", "Lesieur Cristal", "Agroalimentaire et Production"),
    ("M2M", "M2M Group", "Matériels, Logiciels et Services Informatiques"),
    ("MOX", "Maghreb Oxygene", "Chimie"),
    ("MAB", "Maghrebail", "Sociétés de financement et Autres Activités Financières"),
    ("MNG", "Managem", "Mines"),
    ("MLE", "Maroc Leasing", "Sociétés de financement et Autres Activités Financières"),
    ("MDP", "Med Paper", "Sylviculture et Papier"),
    ("MIC", "Microdata", "Matériels, Logiciels et Services Informatiques"),
    ("CMT", "Miniere Touissit", "Mines"),
    ("OUL", "Oulmes", "Boissons"),
    ("PRO", "Promopharm S.A.", "Industrie Pharmaceutique"),
    ("SRM", "Realis. Mecaniques (SRM)", "Distributeurs"),
    ("REB", "Rebab Company", "Mines"),
    ("RDS", "Residences Dar Saada", "Participation et promotion immobilières"),
    ("RIS", "Risma", "Loisirs et Hôtels"),
    ("S2M", "S.M Monetique", "Matériels, Logiciels et Services Informatiques"),
    ("SAHM", "Sanlam Maroc", "Assurances"),
    ("SLF", "Salafin", "Sociétés de financement et Autres Activités Financières"),
    ("SAM", "Samir", "Pétrole et Gaz"),
    ("SMI", "SMI", "Mines"),
    ("SNP", "SNEP", "Chimie"),
    ("SID", "Sonasid", "Bâtiment et Matériaux de Construction"),
    ("SOT", "Sothema", "Industrie Pharmaceutique"),
    ("SNA", "Stokvis Nord Afrique", "Distributeurs"),
    ("STR", "Stroc Industrie", "Ingénieries et Biens d'Equipement Industriels"),
    ("TQM", "Taqa Morocco", "Electricité"),
    ("TMA", "TotalEnergies Marketing Maroc", "Pétrole et Gaz"),
    ("UMR", "Unimer", "Agroalimentaire et Production"),
    ("WAA", "Wafa Assurance", "Assurances"),
    ("ZDJ", "Zellidja S.A", "Sociétés de Portefeuilles - Holdings"),
    ("MSA", "Marsa Maroc", "Services de transport"),
    ("IMO", "Immorente Invest", "Sociétés de placement immobilier"),
    ("MUT", "Mutandis SCA", "Agroalimentaire et Production"),
    ("ARD", "Aradei Capital", "Sociétés de placement immobilier"),
    ("TGC", "TGCC", "Bâtiment et Matériaux de Construction"),
    ("DYT", "Disty Technologies", "Matériels, Logiciels et Services Informatiques"),
    ("AKT", "Akdital", "Santé"),
    ("CFG", "CFG Bank", "Banques"),
    ("CMG", "CMGP Group", "Industrie Agricole"),
    ("VCN", "Vicenne", "Santé"),
    ("CAP", "Cash Plus", "Sociétés de financement et Autres Activités Financières"),
    ("T2S", "T2S", "Santé"),
    ("GTM", "SGTM (Société Générale des Travaux du Maroc)", "Bâtiment et Matériaux de Construction"),
]

# ISIN des titres ci-dessus, pour les rapprocher de la source de cours de secours (cf. cours_bvc.py).
# Établi en rapprochant les noms du flux Médias24 (relevé 09/10/2026) des codes BVC : à
# corriger depuis Bourse > Paramètres si un cours ne correspond pas. Les titres absents du
# flux (DIS, HOL, MDP, SAM, SOT, SNA) n'ont pas d'ISIN et restent en saisie manuelle.
ISIN_BVC_DEFAUT = {
    "AFM": "MA0000012296", "AFI": "MA0000012114", "GAZ": "MA0000010951", "AGM": "MA0000010944",
    "ADI": "MA0000011819", "ALM": "MA0000010936", "ATL": "MA0000011710", "ATW": "MA0000012445",
    "ATH": "MA0000010969", "NEJ": "MA0000011009", "BAL": "MA0000011991", "BCP": "MA0000011884",
    "BOA": "MA0000012437", "BCI": "MA0000010811", "SBM": "MA0000010365", "CRS": "MA0000011868",
    "CDM": "MA0000010381", "CIH": "MA0000011454", "CMA": "MA0000010506", "COL": "MA0000011934",
    "CSR": "MA0000012247", "CTM": "MA0000010340", "DARI": "MA0000011421", "DLM": "MA0000011777",
    "DHO": "MA0000011850", "DWAY": "MA0000011637", "ADH": "MA0000011512", "NAKL": "MA0000011942",
    "EQD": "MA0000010357", "FBR": "MA0000011587", "HPS": "MA0000012619", "IBMC": "MA0000011132",
    "INV": "MA0000011579", "IAM": "MA0000011488", "JET": "MA0000012080", "LBV": "MA0000011801",
    "LHM": "MA0000012320", "LES": "MA0000012031", "M2M": "MA0000011678", "MOX": "MA0000010985",
    "MAB": "MA0000011215", "MNG": "MA0000012866", "MLE": "MA0000010035", "MIC": "MA0000012163",
    "CMT": "MA0000011793", "OUL": "MA0000010415", "PRO": "MA0000011660", "SRM": "MA0000011595",
    "REB": "MA0000010993", "RDS": "MA0000012239", "RIS": "MA0000011462", "S2M": "MA0000012106",
    "SAHM": "MA0000012007", "SLF": "MA0000011744", "SMI": "MA0000010068", "SNP": "MA0000011728",
    "SID": "MA0000010019", "STR": "MA0000012056", "TQM": "MA0000012205", "TMA": "MA0000012262",
    "UMR": "MA0000012023", "WAA": "MA0000010928", "ZDJ": "MA0000010571", "MSA": "MA0000012312",
    "IMO": "MA0000012387", "MUT": "MA0000012395", "ARD": "MA0000012460", "TGC": "MA0000012528",
    "DYT": "MA0000012536", "AKT": "MA0000012585", "CFG": "MA0000012627", "CMG": "MA0000012718",
    "VCN": "MA0000012759", "CAP": "MA0000012767", "T2S": "MA0000012858", "GTM": "MA0000012783",
}

# Anciens libellés (classification anglaise) remplacés par la migration dans init_db.
ANCIENS_SECTEURS_EN = [
    "Basic Materials", "Consumer Goods", "Consumer Services", "Financials", "Health Care",
    "Industrials", "Oil & Gas", "Technology", "Telecom", "Utilities",
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

# Message renvoyé quand une écriture vise un nom absent de la table parente (CLES_ETRANGERES)
MESSAGES_CLES = {
    "fk_depenses_categorie": "Catégorie inconnue : choisis-la dans la liste (Paramètres → Catégories).",
    "fk_revenus_source": "Source de revenu inconnue.",
    "fk_bourse_transactions_titre": "Titre inconnu. Ajoute-le d'abord dans Bourse > Paramètres > Titres.",
    "fk_bourse_dividendes_titre": "Titre inconnu. Ajoute-le d'abord dans Bourse > Paramètres > Titres.",
    "fk_bourse_prix_titre": "Titre inconnu. Ajoute-le d'abord dans Bourse > Paramètres > Titres.",
    "fk_bourse_cours_historique_titre": "Titre inconnu. Ajoute-le d'abord dans Bourse > Paramètres > Titres.",
    "fk_lectures_livres_genre": "Genre inconnu : ajoute-le d'abord dans Lectures > Paramètres.",
    "fk_lectures_a_lire_genre": "Genre inconnu : ajoute-le d'abord dans Lectures > Paramètres.",
    "fk_recurrences_categorie": "Catégorie inconnue : choisis-la dans la liste (Paramètres → Catégories).",
    "fk_recurrences_source": "Source de revenu inconnue.",
    "fk_bourse_cibles_titre": "Titre inconnu. Ajoute-le d'abord dans Bourse > Paramètres > Titres.",
}


def message_cle_etrangere(e: ForeignKeyViolation) -> str:
    nom = getattr(e.diag, "constraint_name", None) or ""
    return MESSAGES_CLES.get(nom, "Référence inconnue ou encore utilisée ailleurs.")


@contextmanager
def references_valides():
    """Traduit une clé étrangère violée en erreur 400 lisible. À placer AUTOUR de `db()` :
    la connexion est d'abord remise en état (rollback), puis l'erreur est traduite."""
    try:
        yield
    except ForeignKeyViolation as e:
        raise HTTPException(400, message_cle_etrangere(e)) from None


# Clé arbitraire du verrou PostgreSQL (pg_advisory_xact_lock) qui sérialise les migrations
VERROU_MIGRATIONS = 4_815_162_342


@contextmanager
def migrations_a_faire():
    """Indique (True/False) s'il faut lancer init_db et les migrations pour la version déployée.

    Sur Vercel, chaque démarrage à froid lançait init_db, parfois dans plusieurs instances à la
    fois (le dashboard envoie ses requêtes en parallèle) : les mêmes CREATE/ALTER concurrents
    échouaient en 500. Désormais, elles ne tournent qu'une fois par version (VERSION_DEPLOYEE),
    notée dans la table migrations_appliquees, et sous un verrou : les autres instances attendent
    la fin de la première puis constatent que c'est fait. La version n'est notée que si le corps
    du `with` réussit ; sinon la suivante réessaie. Sans version connue (en local) : toujours True."""
    with db() as c:
        def deja_faite():
            if not VERSION_DEPLOYEE:
                return False
            # Table absente : base neuve, ou première version qui note ses migrations
            if not c.execute("SELECT to_regclass('migrations_appliquees') IS NOT NULL ok").fetchone()["ok"]:
                return False
            return c.execute("SELECT 1 FROM migrations_appliquees WHERE version = %s",
                             (VERSION_DEPLOYEE,)).fetchone() is not None

        if deja_faite():           # cas courant : une seule petite requête par démarrage à froid
            yield False
            return
        # Verrou tenu jusqu'à la fin de la transaction de `c`, donc après init_db (autre connexion)
        c.execute("SELECT pg_advisory_xact_lock(%s)", (VERROU_MIGRATIONS,))
        if deja_faite():           # une autre instance vient de les faire pendant l'attente
            yield False
            return
        yield True
        if VERSION_DEPLOYEE:
            c.execute("INSERT INTO migrations_appliquees(version) VALUES(%s) ON CONFLICT DO NOTHING",
                      (VERSION_DEPLOYEE,))

# Tables de données : chacune reçoit `modifie_le`, la date de la dernière modification d'une ligne.
# Un déclencheur PostgreSQL la tient à jour, y compris pour un UPDATE fait hors de l'application.
TABLES_MODIFIE_LE = (
    "categories", "depenses", "revenus", "sources_revenus", "budgets_historique", "params", "utilisateurs",
    "bourse_parametres", "bourse_transactions", "bourse_titres", "bourse_dividendes", "bourse_frais",
    "bourse_mouvements", "bourse_cibles_secteur", "bourse_cibles_titre",
    "lectures_livres", "lectures_genres", "lectures_a_lire", "lectures_notes", "lectures_prets",
    "dettes", "dettes_remboursements", "echeances", "actifs", "actifs_mouvements", "objectifs", "objectifs_versements",
    "bourse_cours_historique", "rapprochements", "recurrences",
)


def _colonnes_modifie_le(c):
    """Ajoute `modifie_le` aux tables qui ne l'ont pas encore (une seule fois : ajouter et
    supprimer une colonne à chaque démarrage consommerait des numéros de colonne, cf.
    test_deploiement) et (re)crée le déclencheur qui la met à jour à chaque UPDATE."""
    c.execute("""CREATE OR REPLACE FUNCTION maj_modifie_le() RETURNS trigger AS $$
                 BEGIN NEW.modifie_le = now(); RETURN NEW; END $$ LANGUAGE plpgsql""")
    colonnes = c.execute("""SELECT table_name, column_name FROM information_schema.columns
                            WHERE table_schema = current_schema() AND column_name IN ('modifie_le', 'cree_le')""").fetchall()
    ont = lambda colonne: {r["table_name"] for r in colonnes if r["column_name"] == colonne}
    deja, avec_cree_le = ont("modifie_le"), ont("cree_le")
    for t in TABLES_MODIFIE_LE:
        table = sql.Identifier(t)
        if t not in deja:
            c.execute(sql.SQL("ALTER TABLE {} ADD COLUMN modifie_le TIMESTAMPTZ").format(table))
            # Lignes existantes : leur date de création si la table la garde, sinon celle de la migration
            if t in avec_cree_le:
                c.execute(sql.SQL("UPDATE {} SET modifie_le = cree_le").format(table))
            c.execute(sql.SQL("UPDATE {} SET modifie_le = now() WHERE modifie_le IS NULL").format(table))
            c.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN modifie_le SET DEFAULT now(), "
                              "ALTER COLUMN modifie_le SET NOT NULL").format(table))
        # DROP + CREATE plutôt que CREATE OR REPLACE TRIGGER (PostgreSQL 14+ seulement)
        c.execute(sql.SQL("DROP TRIGGER IF EXISTS trg_modifie_le ON {}").format(table))
        c.execute(sql.SQL("CREATE TRIGGER trg_modifie_le BEFORE UPDATE ON {} "
                          "FOR EACH ROW EXECUTE FUNCTION maj_modifie_le()").format(table))


# Noms utilisés comme référence (texte) dans d'autres tables : (table, colonne, table parente,
# colonne parente, contrainte). ON UPDATE CASCADE : renommer une catégorie, une source ou un
# code de titre renomme toutes les lignes qui y font référence, sans code dans les routes.
CLES_ETRANGERES = (
    ("depenses", "categorie", "categories", "nom", "fk_depenses_categorie"),
    ("revenus", "source", "sources_revenus", "nom", "fk_revenus_source"),
    ("bourse_transactions", "titre", "bourse_titres", "code", "fk_bourse_transactions_titre"),
    ("bourse_dividendes", "titre", "bourse_titres", "code", "fk_bourse_dividendes_titre"),
    ("bourse_prix", "titre", "bourse_titres", "code", "fk_bourse_prix_titre"),
    ("bourse_cours_historique", "titre", "bourse_titres", "code", "fk_bourse_cours_historique_titre"),
    ("lectures_livres", "genre", "lectures_genres", "nom", "fk_lectures_livres_genre"),
    ("lectures_a_lire", "genre", "lectures_genres", "nom", "fk_lectures_a_lire_genre"),
)


def _cles_etrangeres(c):
    """Pose les clés étrangères de CLES_ETRANGERES (une seule fois). Avant, chaque nom orphelin
    (saisi avant ces contraintes : faute de frappe, source libre « Autre… », titre seulement présent
    dans le journal) devient une ligne parente RETIRÉE (inactive), pour ne rien perdre."""
    deja = {r["conname"] for r in c.execute("SELECT conname FROM pg_constraint WHERE contype = 'f'").fetchall()}
    if all(fk[4] in deja for fk in CLES_ETRANGERES):
        return
    # Un code de titre doit pouvoir porter n'importe quel titre déjà saisi (VARCHAR(60) dans le journal)
    c.execute("ALTER TABLE bourse_titres ALTER COLUMN code TYPE VARCHAR(60)")
    # Revenu sans source : NULL (une clé étrangère n'accepte pas '' sans source '' en face)
    c.execute("UPDATE revenus SET source = NULL WHERE trim(source) = ''")
    c.execute("ALTER TABLE revenus ALTER COLUMN source DROP DEFAULT")
    c.execute("""INSERT INTO categories(nom, budget, actif)
                 SELECT DISTINCT categorie, 0, 0 FROM depenses ON CONFLICT (nom) DO NOTHING""")
    # travail = false : une source libre ne comptait pas dans le taux horaire, elle n'y compte toujours pas
    c.execute("""INSERT INTO sources_revenus(nom, actif, travail)
                 SELECT DISTINCT source, 0, false FROM revenus WHERE source IS NOT NULL ON CONFLICT (nom) DO NOTHING""")
    # Livre sans genre : NULL (comme un revenu sans source) ; un genre inconnu devient un genre retiré
    for table in ("lectures_livres", "lectures_a_lire"):
        c.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN genre DROP NOT NULL, ALTER COLUMN genre DROP DEFAULT").format(
            sql.Identifier(table)))
        c.execute(sql.SQL("UPDATE {} SET genre = NULL WHERE trim(genre) = ''").format(sql.Identifier(table)))
    c.execute("""INSERT INTO lectures_genres(nom, actif)
                 SELECT DISTINCT genre, 0 FROM (SELECT genre FROM lectures_livres UNION SELECT genre FROM lectures_a_lire) g
                 WHERE genre IS NOT NULL ON CONFLICT (nom) DO NOTHING""")
    c.execute("""INSERT INTO bourse_titres(code, nom, actif)
                 SELECT titre, titre, 0 FROM (SELECT titre FROM bourse_transactions UNION SELECT titre FROM bourse_dividendes
                                              UNION SELECT titre FROM bourse_prix UNION SELECT titre FROM bourse_cours_historique) t
                 ON CONFLICT (code) DO NOTHING""")
    for table, colonne, parente, cle, nom in CLES_ETRANGERES:
        if nom not in deja:
            c.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {} ({}) ON UPDATE CASCADE").format(
                sql.Identifier(table), sql.Identifier(nom), sql.Identifier(colonne), sql.Identifier(parente), sql.Identifier(cle)))
    # Index côté enfant : une cascade de renommage ne parcourt pas toute la table
    c.execute("CREATE INDEX IF NOT EXISTS idx_depenses_categorie ON depenses (categorie)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_revenus_source ON revenus (source)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bourse_tx_titre ON bourse_transactions (titre)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_lectures_livres_genre ON lectures_livres (genre)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_lectures_a_lire_genre ON lectures_a_lire (genre)")


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
            description TEXT DEFAULT '',
            montant DOUBLE PRECISION NOT NULL,
            cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        -- Charge fixe (loyer, factures) : exclue du budget journalier/hebdo, traitée à part dans la projection
        ALTER TABLE categories ADD COLUMN IF NOT EXISTS fixe BOOLEAN NOT NULL DEFAULT false;
        -- Description libre d'un revenu (ajoutée après coup : les bases existantes la reçoivent ici)
        ALTER TABLE revenus ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
        -- Versions déployées dont les migrations ont tourné (cf. migrations_a_faire)
        CREATE TABLE IF NOT EXISTS migrations_appliquees (
            version TEXT PRIMARY KEY,
            le      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS params (
            cle TEXT PRIMARY KEY,
            valeur DOUBLE PRECISION NOT NULL
        );
        -- Journal de la tâche planifiée /api/cron/quotidien (derniers appels), affiché dans les Paramètres
        CREATE TABLE IF NOT EXISTS cron_journal (
            id     SERIAL PRIMARY KEY,
            le     TIMESTAMPTZ NOT NULL DEFAULT now(),
            etat   VARCHAR(20) NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
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
        -- Durée de la session (1 jour, ou 30 avec « Rester connecté ») : sert à la prolonger pendant l'utilisation
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS duree_jours INTEGER NOT NULL DEFAULT 1;
        CREATE INDEX IF NOT EXISTS idx_depenses_date ON depenses(date);
        CREATE INDEX IF NOT EXISTS idx_revenus_date ON revenus(date);

        -- Tags libres, transverses aux catégories (« voyage été 2026 », « mariage »), en minuscules
        ALTER TABLE depenses ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
        ALTER TABLE revenus ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
        CREATE INDEX IF NOT EXISTS idx_depenses_tags ON depenses USING GIN (tags);
        CREATE INDEX IF NOT EXISTS idx_revenus_tags ON revenus USING GIN (tags);

        -- Budget de chaque catégorie mois par mois : un mois utilise la dernière ligne dont
        -- mois_debut (AAAA-MM) est antérieur ou égal. Changer un budget ajoute une ligne au lieu
        -- de réécrire le « prévu » des mois passés. categories.budget/fixe gardent la valeur du
        -- mois en cours (lecture rapide pour les formulaires). '1900-01' = depuis toujours.
        CREATE TABLE IF NOT EXISTS budgets_historique (
            categorie_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            mois_debut   TEXT NOT NULL,
            budget       DOUBLE PRECISION NOT NULL,
            fixe         BOOLEAN NOT NULL DEFAULT false,
            PRIMARY KEY (categorie_id, mois_debut)
        );

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
            code    VARCHAR(60) UNIQUE NOT NULL,
            nom     VARCHAR(100) NOT NULL,
            secteur VARCHAR(100) DEFAULT '',
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

        -- TPCVM saisie manuellement sur chaque vente (montant du relevé de courtage).
        -- NULL = vente antérieure à cette colonne : remplie une seule fois au démarrage
        -- avec l'ancienne valeur calculée (cf. routes/bourse.py, remplir_tpcvm_manquantes).
        ALTER TABLE bourse_transactions ADD COLUMN IF NOT EXISTS tpcvm NUMERIC(14,4);

        -- Cours automatiques (cf. cours_bvc.py) : l'ISIN rapproche un titre du flux de cours ;
        -- `manuel` verrouille un cours saisi à la main jusqu'à sa remise en automatique ;
        -- `cours_auto_le` date la dernière récupération réussie (au plus une toutes les 15 min).
        ALTER TABLE bourse_titres ADD COLUMN IF NOT EXISTS isin VARCHAR(20);
        ALTER TABLE bourse_prix ADD COLUMN IF NOT EXISTS manuel BOOLEAN NOT NULL DEFAULT false;
        ALTER TABLE bourse_parametres ADD COLUMN IF NOT EXISTS cours_auto_le TIMESTAMPTZ;

        -- ================================================================
        -- Lectures — livres terminés. Une relecture est une nouvelle ligne :
        -- elle compte comme un livre lu de plus.
        -- ================================================================
        CREATE TABLE IF NOT EXISTS lectures_livres (
            id           SERIAL PRIMARY KEY,
            titre        VARCHAR(200) NOT NULL,
            auteur       VARCHAR(150) NOT NULL DEFAULT '',
            genre        VARCHAR(100) NOT NULL DEFAULT '',     -- genre stocké par son nom (comme les catégories)
            date_debut   DATE,                                 -- optionnelle
            date_fin     DATE NOT NULL,                        -- détermine le mois et l'année du livre
            pages        INTEGER CHECK (pages > 0),
            note         SMALLINT CHECK (note BETWEEN 1 AND 5),   -- appréciation en étoiles
            commentaire  TEXT NOT NULL DEFAULT '',
            cree_le      TIMESTAMP NOT NULL DEFAULT now(),
            CHECK (date_debut IS NULL OR date_debut <= date_fin)
        );
        CREATE INDEX IF NOT EXISTS idx_lectures_date_fin ON lectures_livres (date_fin);

        CREATE TABLE IF NOT EXISTS lectures_genres (
            id    SERIAL PRIMARY KEY,
            nom   TEXT UNIQUE NOT NULL,
            actif INTEGER NOT NULL DEFAULT 1
        );

        -- ISBN et couverture (Open Library), facultatifs
        ALTER TABLE lectures_livres ADD COLUMN IF NOT EXISTS isbn VARCHAR(20) NOT NULL DEFAULT '';
        ALTER TABLE lectures_livres ADD COLUMN IF NOT EXISTS couverture TEXT NOT NULL DEFAULT '';

        -- Livres à lire, ou en cours (date_debut renseignée). « Terminé » le déplace dans
        -- lectures_livres : ces tables restent séparées pour que le bilan ne compte que les livres finis.
        CREATE TABLE IF NOT EXISTS lectures_a_lire (
            id          SERIAL PRIMARY KEY,
            titre       VARCHAR(200) NOT NULL,
            auteur      VARCHAR(150) NOT NULL DEFAULT '',
            genre       VARCHAR(100) NOT NULL DEFAULT '',
            pages       INTEGER CHECK (pages > 0),
            isbn        VARCHAR(20) NOT NULL DEFAULT '',
            couverture  TEXT NOT NULL DEFAULT '',
            commentaire TEXT NOT NULL DEFAULT '',
            date_debut  DATE,
            cree_le     TIMESTAMP NOT NULL DEFAULT now()
        );

        -- Notes et citations, rattachées à un livre terminé OU à un livre à lire / en cours
        -- (elles suivent le livre quand il est terminé)
        CREATE TABLE IF NOT EXISTS lectures_notes (
            id        SERIAL PRIMARY KEY,
            livre_id  INTEGER REFERENCES lectures_livres(id) ON DELETE CASCADE,
            a_lire_id INTEGER REFERENCES lectures_a_lire(id) ON DELETE CASCADE,
            type      VARCHAR(10) NOT NULL DEFAULT 'note' CHECK (type IN ('note', 'citation')),
            texte     TEXT NOT NULL,
            page      INTEGER CHECK (page > 0),
            cree_le   TIMESTAMP NOT NULL DEFAULT now(),
            CHECK ((livre_id IS NULL) <> (a_lire_id IS NULL))
        );
        CREATE INDEX IF NOT EXISTS idx_lectures_notes_livre ON lectures_notes (livre_id);
        CREATE INDEX IF NOT EXISTS idx_lectures_notes_a_lire ON lectures_notes (a_lire_id);

        -- Bourse : poids cible de chaque secteur dans le portefeuille (0 à 1)
        CREATE TABLE IF NOT EXISTS bourse_cibles_secteur (
            secteur VARCHAR(100) PRIMARY KEY,
            cible   NUMERIC(6,4) NOT NULL CHECK (cible >= 0 AND cible <= 1)
        );

        -- Bourse : poids cible de chaque titre dans le portefeuille (0 à 1) ; suit le renommage d'un code
        CREATE TABLE IF NOT EXISTS bourse_cibles_titre (
            titre VARCHAR(60) PRIMARY KEY CONSTRAINT fk_bourse_cibles_titre REFERENCES bourse_titres(code)
                  ON UPDATE CASCADE ON DELETE CASCADE,
            cible NUMERIC(6,4) NOT NULL CHECK (cible >= 0 AND cible <= 1)
        );

        -- ================================================================
        -- Carnet — dettes et prêts. Un prêt accordé ou un emprunt est un TRANSFERT (comme un
        -- apport Bourse) : ni une dépense ni un revenu du Budget. Le reste dû = montant − remboursements.
        -- ================================================================
        CREATE TABLE IF NOT EXISTS dettes (
            id             SERIAL PRIMARY KEY,
            sens           VARCHAR(10) NOT NULL CHECK (sens IN ('pret', 'emprunt')),   -- pret : on me doit ; emprunt : je dois
            personne       VARCHAR(100) NOT NULL,
            montant        NUMERIC(14,2) NOT NULL CHECK (montant > 0),
            date_operation DATE NOT NULL,
            echeance       DATE,                                  -- date de remboursement convenue, optionnelle
            libelle        VARCHAR(200) NOT NULL DEFAULT '',
            cree_le        TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS dettes_remboursements (
            id             SERIAL PRIMARY KEY,
            dette_id       INTEGER NOT NULL REFERENCES dettes(id) ON DELETE CASCADE,
            date_operation DATE NOT NULL,
            montant        NUMERIC(14,2) NOT NULL CHECK (montant > 0),
            libelle        VARCHAR(200) NOT NULL DEFAULT '',
            cree_le        TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_dettes_remb_dette ON dettes_remboursements (dette_id);

        -- Carnet — échéances (papiers, assurance, visite technique, garanties...). `rappel_jours` :
        -- prévenir à partir de J−n ; `recurrence_mois` : NULL = ponctuelle, 12 = revient tous les ans.
        CREATE TABLE IF NOT EXISTS echeances (
            id              SERIAL PRIMARY KEY,
            titre           VARCHAR(150) NOT NULL,
            categorie       VARCHAR(50) NOT NULL DEFAULT '',
            date_echeance   DATE NOT NULL,
            rappel_jours    INTEGER NOT NULL DEFAULT 30 CHECK (rappel_jours >= 0),
            recurrence_mois INTEGER CHECK (recurrence_mois > 0),
            note            TEXT NOT NULL DEFAULT '',
            cree_le         TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_echeances_date ON echeances (date_echeance);

        -- Lectures : page atteinte dans un livre en cours, au plus une ligne par jour et par livre
        CREATE TABLE IF NOT EXISTS lectures_progression (
            a_lire_id INTEGER NOT NULL REFERENCES lectures_a_lire(id) ON DELETE CASCADE,
            date      DATE NOT NULL,
            page      INTEGER NOT NULL CHECK (page >= 0),
            PRIMARY KEY (a_lire_id, date)
        );
        -- Jours où l'on a lu (série de jours consécutifs) : gardés à part, car la progression
        -- d'un livre disparaît avec lui quand il est terminé
        CREATE TABLE IF NOT EXISTS lectures_jours (
            date DATE PRIMARY KEY
        );
        -- Livres prêtés : `date_retour` renseignée = rendu
        CREATE TABLE IF NOT EXISTS lectures_prets (
            id          SERIAL PRIMARY KEY,
            titre       VARCHAR(200) NOT NULL,
            personne    VARCHAR(100) NOT NULL,
            date_pret   DATE NOT NULL,
            date_retour DATE,
            note        TEXT NOT NULL DEFAULT '',
            cree_le     TIMESTAMP NOT NULL DEFAULT now(),
            CHECK (date_retour IS NULL OR date_retour >= date_pret)
        );

        -- Bourse : pourquoi j'ai acheté ou vendu (journal des décisions)
        ALTER TABLE bourse_transactions ADD COLUMN IF NOT EXISTS note TEXT NOT NULL DEFAULT '';

        -- Patrimoine — actifs hors Bourse, à valeur saisie à la main (or, compte épargne, immobilier...).
        -- `verse` : argent sorti de l'épargne du Budget pour cet actif sans être saisi en dépense
        -- (un transfert, comme un apport Bourse) ; il est retiré des liquidités pour ne pas compter deux fois.
        CREATE TABLE IF NOT EXISTS actifs (
            id      SERIAL PRIMARY KEY,
            nom     VARCHAR(100) NOT NULL,
            type    VARCHAR(30) NOT NULL DEFAULT 'Autre',
            valeur  NUMERIC(14,2) NOT NULL CHECK (valeur >= 0),
            verse   NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (verse >= 0),
            zakat   BOOLEAN NOT NULL DEFAULT false,          -- compte dans l'assiette de la zakat
            maj_le  DATE NOT NULL,                           -- date de la dernière valeur saisie
            note    TEXT NOT NULL DEFAULT '',
            cree_le TIMESTAMP NOT NULL DEFAULT now()
        );
        -- Versements et retraits d'un actif (bouton « Verser / Retirer ») : chacun ajoute son montant
        -- (négatif = retrait) à `valeur` ET à `verse` de l'actif, qui restent les totaux lus partout.
        -- `verse` peut donc devenir négatif : retirer plus qu'on n'a mis (intérêts, plus-value)
        -- fait revenir cet argent dans les liquidités.
        ALTER TABLE actifs DROP CONSTRAINT IF EXISTS actifs_verse_check;
        CREATE TABLE IF NOT EXISTS actifs_mouvements (
            id             SERIAL PRIMARY KEY,
            actif_id       INTEGER NOT NULL REFERENCES actifs(id) ON DELETE CASCADE,
            date_operation DATE NOT NULL,
            montant        NUMERIC(14,2) NOT NULL CHECK (montant <> 0),
            libelle        VARCHAR(200) NOT NULL DEFAULT '',
            cree_le        TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_actifs_mouvements ON actifs_mouvements (actif_id);

        -- Objectifs d'épargne par projet (voyage, fonds d'urgence, voiture). Un versement met de
        -- l'argent de côté pour l'objectif : il reste dans les liquidités (ce n'est ni une dépense
        -- ni un transfert), il est seulement réservé. Négatif = argent repris à l'objectif.
        CREATE TABLE IF NOT EXISTS objectifs (
            id          SERIAL PRIMARY KEY,
            nom         VARCHAR(100) NOT NULL,
            cible       NUMERIC(14,2) NOT NULL CHECK (cible > 0),
            date_limite DATE,
            note        TEXT NOT NULL DEFAULT '',
            archive     BOOLEAN NOT NULL DEFAULT false,      -- atteint ou abandonné : sorti de la liste en cours
            cree_le     TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS objectifs_versements (
            id             SERIAL PRIMARY KEY,
            objectif_id    INTEGER NOT NULL REFERENCES objectifs(id) ON DELETE CASCADE,
            date_operation DATE NOT NULL,
            montant        NUMERIC(14,2) NOT NULL CHECK (montant <> 0),
            libelle        VARCHAR(200) NOT NULL DEFAULT '',
            cree_le        TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_objectifs_versements ON objectifs_versements (objectif_id);
        -- Objectif suivi par un tag (#turquie-2027) : les dépenses portant ce tag, datées de
        -- tag_depuis ou après, sont prises sur l'argent mis de côté (cf. routes/objectifs.py)
        ALTER TABLE objectifs ADD COLUMN IF NOT EXISTS tag VARCHAR(40);
        ALTER TABLE objectifs ADD COLUMN IF NOT EXISTS tag_depuis DATE;

        -- Patrimoine net noté une fois par jour (tâche du matin, et à chaque ouverture de l'écran
        -- Patrimoine) : la courbe se construit jour après jour. Les cours passés n'étant pas
        -- conservés, les jours d'avant ne peuvent pas être recalculés.
        CREATE TABLE IF NOT EXISTS patrimoine_historique (
            date          DATE PRIMARY KEY,
            total         NUMERIC(14,2) NOT NULL,
            liquidites    NUMERIC(14,2) NOT NULL,
            bourse        NUMERIC(14,2) NOT NULL,
            autres_actifs NUMERIC(14,2) NOT NULL,
            creances      NUMERIC(14,2) NOT NULL,
            dettes        NUMERIC(14,2) NOT NULL,
            maj_le        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        -- estime : point de fin de mois recalculé après coup (reconstitution), et non noté le jour même.
        -- Un vrai point du jour le remplace toujours.
        ALTER TABLE patrimoine_historique ADD COLUMN IF NOT EXISTS estime BOOLEAN NOT NULL DEFAULT false;

        -- Échecs de mot de passe récents (anti force brute, cf. securite.LimiteurEchecs) : en base,
        -- pour être partagés par toutes les instances Vercel et survivre aux redémarrages
        CREATE TABLE IF NOT EXISTS echecs_login (
            id   SERIAL PRIMARY KEY,
            cle  VARCHAR(200) NOT NULL,
            le   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_echecs_login_cle ON echecs_login (cle, le);

        -- Cours passés saisis à la main (relevés de fin de mois du courtier) : servent à la
        -- reconstitution de la courbe du patrimoine, à la place du dernier cours d'achat ou de vente.
        CREATE TABLE IF NOT EXISTS bourse_cours_historique (
            titre    VARCHAR(60) NOT NULL,
            date     DATE NOT NULL,
            cours    NUMERIC(14,4) NOT NULL CHECK (cours > 0),
            cree_le  TIMESTAMP NOT NULL DEFAULT now(),
            PRIMARY KEY (titre, date)
        );

        -- Pointages du solde : le solde réel (banque, espèces) comparé aux liquidités calculées.
        -- `comptes` : détail saisi [{nom, montant}] ; `regle` : l'écart a été enregistré en dépense ou en revenu.
        CREATE TABLE IF NOT EXISTS rapprochements (
            id            SERIAL PRIMARY KEY,
            date          DATE NOT NULL,
            solde_reel    NUMERIC(14,2) NOT NULL,
            solde_calcule NUMERIC(14,2) NOT NULL,
            comptes       JSONB NOT NULL DEFAULT '[]',
            regle         VARCHAR(10) CHECK (regle IN ('depense', 'revenu')),
            note          TEXT NOT NULL DEFAULT '',
            cree_le       TIMESTAMP NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_rapprochements_date ON rapprochements (date);

        -- Échéance avec un montant (assurance, Aïd, rentrée...) : `objectif_id` = l'objectif qui la
        -- provisionne mois après mois (cf. routes/carnet.py)
        ALTER TABLE echeances ADD COLUMN IF NOT EXISTS montant NUMERIC(14,2) CHECK (montant > 0);
        ALTER TABLE echeances ADD COLUMN IF NOT EXISTS objectif_id INTEGER REFERENCES objectifs(id) ON DELETE SET NULL;

        -- Messages reçus du bot Telegram (saisie rapide) : un message déjà traité est ignoré (Telegram
        -- renvoie un message tant qu'il n'a pas reçu de réponse). `attente` : opération qui attend
        -- le choix de sa catégorie (boutons).
        CREATE TABLE IF NOT EXISTS telegram_messages (
            update_id BIGINT PRIMARY KEY,
            le        TIMESTAMPTZ NOT NULL DEFAULT now(),
            attente   JSONB
        );

        -- Alertes de dépenses écartées à la main (« ce n'est pas un doublon ») : clé de l'alerte
        CREATE TABLE IF NOT EXISTS alertes_ignorees (
            cle VARCHAR(300) PRIMARY KEY,
            le  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        -- Cours de clôture de chaque titre détenu, un par jour de bourse : noté une fois, le soir, par
        -- la tâche /api/cron/cours-du-soir (cf. bourse.noter_cours_du_jour). Ni week-end ni jour férié.
        -- Les sources ne donnent que le cours du jour : cet historique commence le jour de sa mise en place.
        CREATE TABLE IF NOT EXISTS bourse_prix_historique (
            titre   VARCHAR(60) NOT NULL REFERENCES bourse_titres(code) ON UPDATE CASCADE,
            date    DATE NOT NULL,
            cours   NUMERIC(14,4) NOT NULL CHECK (cours > 0),
            manuel  BOOLEAN NOT NULL DEFAULT false,
            PRIMARY KEY (titre, date)
        );
        -- 'import' : cours passé importé d'un fichier (historique de la Bourse de Casablanca) ; une
        -- clôture notée le soir ('auto') n'est jamais remplacée par une valeur importée
        ALTER TABLE bourse_prix_historique ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'auto'
            CHECK (source IN ('auto', 'import'));
        -- Jours fériés à date variable (fêtes religieuses, fixées à l'observation de la lune) : la
        -- Bourse est fermée, aucun cours n'est noté. Les fêtes à date fixe sont dans bourse.FERIES_FIXES.
        CREATE TABLE IF NOT EXISTS bourse_jours_feries (
            date    DATE PRIMARY KEY,
            libelle VARCHAR(100) NOT NULL DEFAULT ''
        );
        -- Valeur de clôture des indices de référence (MASI, MASI Rentabilité Net...), une par jour de
        -- bourse : notée le soir (`source` = 'auto') ou importée d'un fichier pour les jours d'avant
        -- ('import' ; une valeur notée automatiquement n'est jamais remplacée par une importée).
        CREATE TABLE IF NOT EXISTS indices_historique (
            indice  VARCHAR(20) NOT NULL,
            date    DATE NOT NULL,
            valeur  NUMERIC(16,6) NOT NULL CHECK (valeur > 0),
            source  VARCHAR(10) NOT NULL DEFAULT 'auto' CHECK (source IN ('auto', 'import')),
            PRIMARY KEY (indice, date)
        );

        -- Opérations récurrentes (loyer, abonnements, salaire) : générées chaque mois au jour dit,
        -- par un bouton dans Saisie ou toutes seules par la tâche du matin (`auto`). `dernier_mois` :
        -- dernier mois généré (ou passé), AAAA-MM : un second passage le même mois ne fait rien.
        CREATE TABLE IF NOT EXISTS recurrences (
            id            SERIAL PRIMARY KEY,
            type          VARCHAR(10) NOT NULL CHECK (type IN ('depense', 'revenu')),
            categorie     TEXT,
            source        TEXT,
            description   VARCHAR(500) NOT NULL DEFAULT '',
            montant       NUMERIC(14,2) NOT NULL CHECK (montant > 0),
            jour          INTEGER NOT NULL CHECK (jour BETWEEN 1 AND 31),
            tags          TEXT[] NOT NULL DEFAULT '{}',
            auto          BOOLEAN NOT NULL DEFAULT false,
            actif         BOOLEAN NOT NULL DEFAULT true,
            debut         VARCHAR(7) NOT NULL,
            dernier_mois  VARCHAR(7),
            cree_le       TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT fk_recurrences_categorie FOREIGN KEY (categorie) REFERENCES categories(nom) ON UPDATE CASCADE,
            CONSTRAINT fk_recurrences_source FOREIGN KEY (source) REFERENCES sources_revenus(nom) ON UPDATE CASCADE,
            CONSTRAINT recurrences_categorie_requise CHECK (type = 'revenu' OR categorie IS NOT NULL)
        );

        """)

        # ------------------------------------------------------------------
        # Migration additive : simplification du module Bourse — les frais
        # (courtage, TVA, impôt de bourse...) et la retenue sur dividendes ne
        # sont plus calculés automatiquement ; l'utilisateur saisit directement
        # le prix net (achat/vente) et le montant net des dividendes. Les
        # anciennes colonnes de taux figés restent en base (non détruites) mais
        # ne sont plus lues par l'application.
        # ------------------------------------------------------------------
        ancienne_colonne = c.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'bourse_dividendes' AND column_name = 'montant_brut'
        """).fetchone()
        if ancienne_colonne:
            # Requise par l'UPDATE ci-dessous (peut être absente si bourse_parametres existait
            # déjà avant l'ajout du module Dividendes). Ne pas la sortir de ce `if` : ajoutée puis
            # supprimée à chaque démarrage, chaque cycle consomme définitivement un numéro de
            # colonne PostgreSQL, et la table atteint sa limite de 1600 colonnes.
            c.execute("ALTER TABLE bourse_parametres ADD COLUMN IF NOT EXISTS "
                      "taux_retenue_source_dividendes NUMERIC(6,4) NOT NULL DEFAULT 0.15")
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

        # Revenu du travail (salaire, prime, freelance) : sert au taux horaire (« prix en heures de travail »).
        # Ajout de la colonne : toutes les sources comptent, sauf Remboursement (de l'argent qui revient).
        if not c.execute("""SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'sources_revenus' AND column_name = 'travail'""").fetchone():
            c.execute("ALTER TABLE sources_revenus ADD COLUMN travail BOOLEAN NOT NULL DEFAULT true")
            c.execute("UPDATE sources_revenus SET travail = false WHERE nom = 'Remboursement'")

        _colonnes_modifie_le(c)

        with c.cursor() as cur:
            if c.execute("SELECT COUNT(*) n FROM categories").fetchone()["n"] == 0:
                cur.executemany("INSERT INTO categories(nom,budget,fixe) VALUES(%s,%s,%s)", CATEGORIES_DEFAUT)
            if c.execute("SELECT COUNT(*) n FROM sources_revenus").fetchone()["n"] == 0:
                cur.executemany("INSERT INTO sources_revenus(nom, travail) VALUES(%s,%s)", SOURCES_DEFAUT)
        _cles_etrangeres(c)
        # Historique des budgets : une catégorie sans historique (base antérieure) reçoit son budget
        # actuel « depuis toujours » ; une catégorie déjà désactivée, 0 (comme avant, elle ne compte plus).
        c.execute("""INSERT INTO budgets_historique(categorie_id, mois_debut, budget, fixe)
                     SELECT id, '1900-01', CASE WHEN actif=1 THEN budget ELSE 0 END, fixe FROM categories c
                     WHERE NOT EXISTS (SELECT 1 FROM budgets_historique h WHERE h.categorie_id = c.id)""")
        c.execute("INSERT INTO params(cle,valeur) VALUES('objectif_epargne',5000) ON CONFLICT DO NOTHING")
        c.execute("INSERT INTO params(cle,valeur) VALUES('objectif_lecture_annuel',%s),('objectif_lecture_mensuel',%s) "
                  "ON CONFLICT DO NOTHING", (OBJECTIF_LECTURE_ANNUEL_DEFAUT, OBJECTIF_LECTURE_MENSUEL_DEFAUT))
        if c.execute("SELECT COUNT(*) n FROM lectures_genres").fetchone()["n"] == 0:
            with c.cursor() as cur:
                cur.executemany("INSERT INTO lectures_genres(nom) VALUES(%s)", GENRES_DEFAUT)
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

        # Secteurs des titres BVC : passage de la classification anglaise
        # (Financials, Industrials...) à la classification sectorielle officielle
        # de la Bourse de Casablanca. Seules les lignes portant encore un ancien
        # libellé anglais sont réécrites — un secteur modifié à la main depuis
        # Paramètres > Titres est conservé. Idempotent.
        c.execute("ALTER TABLE bourse_titres ALTER COLUMN secteur TYPE VARCHAR(100)")
        with c.cursor() as cur:
            cur.executemany(
                "UPDATE bourse_titres SET secteur = %s WHERE code = %s AND secteur = ANY(%s)",
                [(secteur, code, ANCIENS_SECTEURS_EN) for code, _, secteur in TITRES_BVC_DEFAUT],
            )
            # Nouveaux titres de la liste par défaut, absents d'une base déjà initialisée.
            cur.executemany(
                "INSERT INTO bourse_titres(code,nom,secteur) VALUES(%s,%s,%s) ON CONFLICT (code) DO NOTHING",
                [t for t in TITRES_BVC_DEFAUT if t[0] == "GTM"],
            )
            # ISIN des titres de la liste par défaut ; un ISIN déjà renseigné est conservé. Idempotent.
            cur.executemany(
                "UPDATE bourse_titres SET isin = %s WHERE code = %s AND isin IS NULL",
                [(isin, code) for code, isin in ISIN_BVC_DEFAUT.items()],
            )
