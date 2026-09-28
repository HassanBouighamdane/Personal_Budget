# Mon Budget — Documentation technique

Application web personnelle pour suivre son budget (dépenses, revenus, épargne) et un portefeuille boursier à la Bourse de Casablanca. Toutes les valeurs sont en dirhams (DH).

- **Backend** : Python, FastAPI, PostgreSQL (driver `psycopg` v3, pool `psycopg_pool`)
- **Frontend** : HTML/CSS/JavaScript vanilla, sans framework ni build, avec Chart.js pour les graphiques
- **Déploiement** : un seul serveur. FastAPI sert à la fois l'API (`/api/...`) et les fichiers statiques du frontend (`/`).

---

## Sommaire

1. [Architecture générale](#1-architecture-générale)
2. [Installation et lancement](#2-installation-et-lancement)
3. [Backend fichier par fichier](#3-backend-fichier-par-fichier)
4. [Schéma de la base de données](#4-schéma-de-la-base-de-données)
5. [Référence de l'API](#5-référence-de-lapi)
6. [Calculs métier](#6-calculs-métier)
7. [Frontend](#7-frontend)
8. [Points restants](#8-points-restants)

---

## 1. Architecture générale

```
Personal_Budget/
├── backend/
│   ├── app.py              Point d'entrée : crée l'app FastAPI, branche les routes, sert le frontend
│   ├── config.py           Variables d'environnement (.env) et constantes
│   ├── database.py         Pool de connexions PostgreSQL + création du schéma
│   ├── securite.py         Mots de passe, sessions, limitation des tentatives de connexion
│   ├── schemas.py          Modèles Pydantic (validation des entrées et des sorties)
│   ├── requirements.txt
│   ├── scripts/
│   │   └── supprimer_bourse.py   Supprime toutes les tables du module Bourse (script manuel)
│   ├── tests/
│   │   ├── test_bourse.py        PRU, frais, arrondis, contrôle des ventes
│   │   ├── test_budget.py        Renommage en cascade, erreurs 404
│   │   └── test_mouvements.py    Apports/retraits, espèces disponibles, performance globale
│   └── routes/
│       ├── auth.py               /api/login, /logout, /me, /mot_de_passe
│       ├── configuration.py      catégories, sources de revenus, objectif d'épargne
│       ├── transactions.py       dépenses et revenus
│       ├── rapports.py           résumés jour / semaine / mois / année / global
│       └── bourse.py             module Bourse
├── frontend/
│   ├── index.html          Page unique : tous les onglets y sont, masqués/affichés en JS
│   ├── css/style.css       Thèmes sombre/clair via variables CSS, responsive
│   ├── js/app.js           Auth, saisie, dashboards, paramètres, utilitaires communs
│   ├── js/bourse.js        Onglet Bourse
│   ├── js/chart.umd.min.js Chart.js embarqué (pas de CDN)
│   └── assets/             Favicons
├── lancer_budget.bat       Lanceur Windows
└── lancer_budget.sh        Lanceur Linux
```

### Déroulement d'une requête

```
Navigateur (index.html + app.js)
   │  fetch('/api/...')  + cookie "session" (HttpOnly)
   ▼
FastAPI (app.py)
   │  Router  → dépendance utilisateur_courant() vérifie le cookie en base
   │           → validation Pydantic du corps (schemas.py)
   ▼
Fonction de route → with db() as c: requêtes SQL → commit automatique
   ▼
Réponse JSON  → le JS génère le HTML (échappé par esc()) et les graphiques Chart.js
```

### Choix de conception

- **Pas d'ORM** : les requêtes SQL sont écrites à la main, toujours paramétrées avec `%s`, donc protégées contre l'injection SQL.
- **Pool de connexions** : `db()` emprunte une connexion à un pool partagé (1 à 10 connexions), la valide (commit) puis la rend. En cas d'exception, le pool annule la transaction (rollback) avant de réutiliser la connexion. Chaque connexion est testée avant d'être prêtée et remplacée si l'hébergeur l'a coupée ; une connexion inactive depuis 5 minutes est fermée.
- **Suppression douce** : les catégories, sources et titres ne sont jamais supprimés. On met `actif=0`, et l'historique reste intact.
- **Noms stockés en texte** : une dépense référence sa catégorie par son nom, un revenu sa source, une transaction son code de titre. Renommer l'un d'eux met donc à jour en cascade les lignes déjà saisies.
- **Schéma idempotent** : il n'y a pas d'outil de migration. `init_db()` s'exécute à chaque démarrage avec `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` et `DROP COLUMN IF EXISTS`, sans risque à rejouer.
- **Nommage en français** dans tout le code (fonctions, variables, colonnes).

---

## 2. Installation et lancement

### Prérequis
- Python 3.10 ou plus récent
- Une base PostgreSQL accessible

### Fichier `backend/.env`

```env
DATABASE_URL=postgresql://user:motdepasse@hote:5432/nom_base
ADMIN_UTILISATEUR=hassan
ADMIN_MOT_DE_PASSE=un_mot_de_passe_solide
PORT=8500               # optionnel, 8500 par défaut (Render fournit PORT automatiquement)
COOKIE_SECURE=false     # true en production derrière HTTPS
CORS_ORIGINS=           # optionnel : seulement si le frontend est hébergé sur un autre domaine
```

- `DATABASE_URL` est obligatoire : sans elle, le démarrage échoue avec un message explicite.
- `ADMIN_UTILISATEUR` et `ADMIN_MOT_DE_PASSE` ne servent qu'au **premier démarrage**, pour créer le compte quand la table `utilisateurs` est vide.

### Commandes

```bash
cd backend
pip install -r requirements.txt
python app.py
```

- Interface : http://localhost:8500
- Documentation interactive de l'API (Swagger) : http://localhost:8500/docs

Les lanceurs `lancer_budget.bat` et `lancer_budget.sh` ouvrent le navigateur puis démarrent le serveur avec le Python du venv `.venv` (le `.bat` se rabat sur le Python du système s'il n'existe pas).

En production : `gunicorn app:app -k uvicorn.workers.UvicornWorker`.

### Tests

```bash
cd backend
pytest tests -v
```

⚠️ Les tests utilisent la base configurée dans `.env` : ils y créent puis suppriment des données préfixées `ZZTEST`. **Ne les lance jamais avec la configuration de production**, uniquement sur une base de développement.

---

## 3. Backend fichier par fichier

### 3.1 `config.py` — configuration

- Charge `backend/.env` via `python-dotenv` (sinon, seules les variables système sont lues).
- Définit `FRONT_DIR`, le dossier `frontend/` servi en statique.
- Lit `DATABASE_URL`, `PORT`, `COOKIE_SECURE`, `ADMIN_UTILISATEUR`, `ADMIN_MOT_DE_PASSE` et `CORS_ORIGINS`.
- Constantes :
  - `DUREE_SESSION_JOURS = 1` : une session expire au bout de 24 h ;
  - `LOGIN_MAX_ECHECS = 10` et `LOGIN_FENETRE_MIN = 15` : seuils de blocage des connexions (voir [§3.3](#33-securitepy--authentification)) ;
  - `CATEGORIES_DEFAUT` (11 catégories avec budget mensuel) et `SOURCES_DEFAUT` (Salaire, Prime, Freelance, Remboursement), insérées au premier démarrage.

### 3.2 `database.py` — base de données

**`TITRES_BVC_DEFAUT`** : environ 80 sociétés cotées à la BVC, sous la forme `(code, nom, secteur)`, insérées au premier démarrage dans `bourse_titres`. Cette table sert à l'autocomplétion du champ « Titre » et au regroupement des positions par secteur. Elle se gère ensuite depuis Bourse → Paramètres.

**`db()`** est un gestionnaire de contexte qui emprunte une connexion au pool `_pool` :
```python
with db() as c:
    c.execute("...", (params,))
# → commit automatique si aucune exception ; rollback sinon
```
`row_factory=dict_row` fait que chaque ligne est un `dict` (`row["montant"]`), directement sérialisable en JSON. `app.py` ferme le pool à l'arrêt du serveur.

**`init_db()`**, appelée au démarrage :
1. crée les tables et les index manquants (voir [§4](#4-schéma-de-la-base-de-données)) ;
2. applique les ajustements de schéma du module Bourse, tous idempotents ;
3. insère les valeurs par défaut dans les tables vides : catégories, sources, objectif d'épargne (5000), compte administrateur, paramètres Bourse, titres BVC ;
4. affiche un avertissement si le mot de passe administrateur vaut `"admin"`.

### 3.3 `securite.py` — authentification

| Élément | Rôle |
|---|---|
| `hacher_mdp(mdp)` | PBKDF2-HMAC-SHA256, 200 000 itérations, sel aléatoire de 16 octets. Format stocké : `"<sel_hex>$<hash_hex>"`. |
| `verifier_mdp(mdp, stocke)` | Recalcule le hash avec le même sel et compare en temps constant (`secrets.compare_digest`). |
| `creer_session(uid)` | Génère un jeton aléatoire, l'enregistre dans `sessions` avec sa date d'expiration et purge les sessions expirées. |
| `supprimer_session(token)` | Déconnexion. |
| `utilisateur_courant(session=Cookie)` | **Dépendance FastAPI** qui protège toutes les routes : vérifie le cookie `session` en base et renvoie `{id, nom}`, sinon erreur **401**. |
| `LimiteurEchecs` / `limiteur_login` | Anti force brute : après **10 échecs en 15 minutes** pour un même nom d'utilisateur (casse et espaces ignorés), les tentatives sont refusées (**429**) pendant 15 minutes, même avec le bon mot de passe. Une réussite remet le compteur à zéro. Protège aussi la vérification du mot de passe actuel lors d'un changement. |

Le cookie de session est `HttpOnly` (inaccessible au JavaScript), `SameSite=Lax` (protection de base contre le CSRF), et `Secure` si `COOKIE_SECURE=true`.

### 3.4 `schemas.py` — modèles Pydantic

Ces modèles valident automatiquement les données reçues. En cas d'échec, FastAPI renvoie une erreur 422.

| Modèle | Utilisation | Contraintes |
|---|---|---|
| `LoginIn` | connexion | — |
| `MdpIn` | changement de mot de passe | `nouveau` ≥ 6 caractères |
| `DepenseIn` | nouvelle dépense | `date` au format `AAAA-MM-JJ` (`DateISO`), `montant > 0` |
| `RevenuIn` | nouveau revenu | `date` au format `AAAA-MM-JJ` (`DateISO`), `montant > 0` |
| `CategorieIn` | catégorie | `nom` non vide, `budget ≥ 0` |
| `ObjectifIn`, `NomIn` | objectif, source | — |
| `ParametresBourse` | paramètres Bourse | `taux_tpcvm` entre 0 et 1 |
| `TitreBourseIn` / `TitreBourse` | référentiel des titres | `code`, `nom`, `secteur` |
| `TransactionBourseCreate` / `Out` | achat/vente | `type_instrument` ∈ {Action, Obligation, OPCVM, IPO}, `type_operation` ∈ {Achat, Vente}, `quantite > 0` |
| `DividendeCreate` / `Out`, `FraisBourseCreate` / `Out` | dividendes et frais de compte | `montant > 0` |
| `MouvementBourseCreate` / `Out` | apports et retraits | `type_mouvement` ∈ {Apport, Retrait}, `montant > 0` |
| `PositionBourse`, `GainRealise`, `DashboardBourse` | sorties calculées | — |

`DateISO` vérifie qu'il s'agit d'une vraie date (refuse `18/09/2026` ou `2026-02-30`) mais la garde sous forme de chaîne : les dates du Budget sont stockées en texte.

### 3.5 `app.py` — point d'entrée

1. Ajoute `backend/` au `sys.path`, pour que l'application se lance depuis n'importe quel dossier.
2. Appelle `init_db()`.
3. Crée l'application FastAPI. CORS n'est activé que si `CORS_ORIGINS` est renseigné, et seulement pour ces origines.
4. Branche les 5 routeurs.
5. Monte `frontend/` sur `/` **après** les routes API, pour que `/api/...` reste prioritaire.
6. Lancé directement, démarre `uvicorn` sur `0.0.0.0:PORT`.

### 3.6 `routes/auth.py`

- `POST /api/login` : vérifie les identifiants (avec limitation des tentatives), crée la session et pose le cookie. Le message d'erreur est le même que l'utilisateur existe ou non.
- `POST /api/logout` : supprime la session et le cookie.
- `GET /api/me` : renvoie le nom de l'utilisateur. Le frontend s'en sert au chargement pour savoir s'il faut afficher l'écran de connexion.
- `PUT /api/mot_de_passe` : vérifie l'ancien mot de passe, enregistre le nouveau et **supprime toutes les sessions** de l'utilisateur, ce qui le déconnecte de tous ses appareils.

### 3.7 `routes/configuration.py`

- `GET /api/categories` renvoie en une seule requête les catégories, les sources et l'objectif d'épargne.
- Les `POST` réactivent un élément désactivé du même nom au lieu de provoquer une erreur d'unicité.
- Les `PUT` (renommer) mettent à jour les lignes déjà saisies : `depenses.categorie` ou `revenus.source`.
- Les `DELETE` désactivent l'élément (`actif=0`).
- `PUT` et `DELETE` renvoient **404** si l'id n'existe pas.

### 3.8 `routes/transactions.py`

Création et suppression des dépenses et revenus (404 si la ligne n'existe pas). `GET /api/transactions?mois=AAAA-MM` liste les deux types pour un mois, avec un filtre `date LIKE '2026-09-%'`.

### 3.9 `routes/rapports.py` — tableaux de bord

| Route | Contenu calculé |
|---|---|
| `GET /api/resume_jour?date=` | totaux du jour, dépenses de la veille, répartition par catégorie, transactions, moyenne quotidienne du mois, budget journalier |
| `GET /api/resume_semaine?date=` | semaine du lundi au dimanche : totaux, comparaison avec la semaine précédente, détail par jour, répartition, top 8, budget hebdomadaire |
| `GET /api/resume?mois=` | budget prévu comparé au réel par catégorie, dépenses cumulées jour par jour, évolution sur 6 mois, top 10, comparaison avec le mois précédent, projection de fin de mois (mois en cours) |
| `GET /api/resume_annuel?annee=` | revenus/dépenses/épargne par mois, meilleur et pire mois, mois où l'objectif est atteint, épargne cumulée, totaux par catégorie comparés au budget annuel, grille catégorie × mois |
| `GET /api/resume_global` | tout l'historique : totaux et moyennes par mois actif, évolution mois par mois (mois vides inclus), épargne cumulée, bilan par année, répartition par catégorie, top 10 |

Dans « budget prévu comparé au réel », les dépenses rattachées à une catégorie désactivée apparaissent aussi, avec un budget de 0.

### 3.10 `routes/bourse.py` — module Bourse

**Précision des calculs** : tous les montants passent par `Decimal`.
- `_d(v)` convertit une valeur en `Decimal` (`None` → 0) ;
- `_r(x)` arrondit un montant à 2 décimales ;
- `_r4(x)` arrondit un ratio (performance) à 4 décimales, pour ne pas tronquer le pourcentage affiché.

**Filtre de période** : les paramètres optionnels `mois=AAAA-MM` ou `annee=AAAA` sont traduits en SQL par `_clause_periode()` pour les listes (transactions, dividendes, frais, mouvements). Les gains réalisés sont filtrés après calcul, car le PRU exige de parcourir tout l'historique.

**`_positions_et_gains()`**, la logique centrale :
1. charge toutes les transactions triées par date, les cours actuels et le taux de TPCVM ;
2. calcule pour chaque transaction `montant_net = qté × cours ± frais` (+ pour un achat, − pour une vente) ;
3. parcourt chronologiquement les transactions de chaque titre, en suivant la quantité détenue et le coût restant : un achat les augmente, une vente calcule son gain avec le PRU **du moment** puis réduit le coût restant ;
4. en déduit les **positions** (PRU, quantité, valeur comptable, valeur de marché, plus-value latente, performance) et les **gains réalisés** avec leur TPCVM.

**`_valider_vente()`** refuse une vente qui ferait passer la quantité détenue sous zéro à n'importe quel moment de l'historique, y compris pour une vente antidatée.

**Dashboard** (`/api/bourse/dashboard`) : valorisation actuelle du portefeuille, résultat de la période (gains, dividendes, frais) et état du compte Bourse (espèces disponibles, apports nets, patrimoine, performance globale). Formules au [§6.2](#62-bourse).

### 3.11 `scripts/supprimer_bourse.py`

Script manuel et **destructif** : supprime toutes les tables du module Bourse et leurs données, après confirmation (taper « oui »). Les tables sont recréées vides au démarrage suivant. Lancement depuis `backend/` : `python scripts/supprimer_bourse.py`.

---

## 4. Schéma de la base de données

### Budget

| Table | Colonnes principales | Remarques |
|---|---|---|
| `categories` | `id`, `nom` UNIQUE, `budget`, `actif` | budget mensuel en DH |
| `depenses` | `id`, `date` TEXT, `categorie` TEXT, `description`, `montant`, `paiement`, `cree_le` | catégorie stockée par son nom ; `paiement` n'est plus utilisée (conservée pour l'historique) |
| `revenus` | `id`, `date` TEXT, `source`, `montant`, `cree_le` | source stockée par son nom |
| `sources_revenus` | `id`, `nom` UNIQUE, `actif` | |
| `paiements` | `id`, `nom` UNIQUE, `actif` | n'est plus utilisée (conservée pour l'historique) |
| `params` | `cle` PK, `valeur` | contient `objectif_epargne` |
| `utilisateurs` | `id`, `nom` UNIQUE, `mdp_hash` | |
| `sessions` | `token` PK, `utilisateur_id` FK, `expire` | |

Index : `depenses(date)`, `revenus(date)`.

### Bourse

| Table | Colonnes principales | Remarques |
|---|---|---|
| `bourse_parametres` | `taux_tpcvm` | une seule ligne |
| `bourse_transactions` | `date_operation` DATE, `titre`, `isin`, `type_instrument`, `type_operation`, `quantite`, `cours_unitaire`, `autres_frais` | contraintes `CHECK` sur les types et les quantités |
| `bourse_prix` | `titre` PK, `cours_actuel`, `maj_le` | un seul cours par titre, sans historique |
| `bourse_titres` | `code` UNIQUE, `nom`, `secteur`, `actif` | référentiel BVC |
| `bourse_dividendes` | `date_operation`, `titre`, `montant` | montant net reçu |
| `bourse_frais` | `date_operation`, `libelle`, `montant` | abonnement courtier, tenue de compte, droits de garde… |
| `bourse_mouvements` | `date_operation`, `type_mouvement` (Apport / Retrait), `montant`, `libelle` | transferts banque ↔ compte Bourse |

Le module Bourse utilise les types `DATE` et `NUMERIC`. Le module Budget utilise `TEXT` pour les dates et `DOUBLE PRECISION` pour les montants.

---

## 5. Référence de l'API

Toutes les routes sauf `/api/login` et `/api/logout` exigent le cookie `session`.

| Méthode | Route | Corps / paramètres | Réponse |
|---|---|---|---|
| POST | `/api/login` | `{utilisateur, mot_de_passe}` | `{ok}` + cookie ; 429 si trop d'échecs |
| POST | `/api/logout` | — | `{ok}` |
| GET | `/api/me` | — | `{utilisateur}` |
| PUT | `/api/mot_de_passe` | `{actuel, nouveau}` | `{ok, message}` |
| GET | `/api/categories` | — | `{categories, sources, objectif_epargne}` |
| POST / PUT / DELETE | `/api/categories[/{id}]` | `{nom, budget}` | `{ok}` |
| PUT | `/api/objectif` | `{objectif}` | `{ok}` |
| POST / PUT / DELETE | `/api/sources[/{id}]` | `{nom}` | `{ok}` |
| POST / DELETE | `/api/depenses[/{id}]` | `{date, categorie, description, montant}` | `{id}` / `{ok}` |
| POST / DELETE | `/api/revenus[/{id}]` | `{date, source, montant}` | `{id}` / `{ok}` |
| GET | `/api/transactions?mois=` | — | `{depenses, revenus}` |
| GET | `/api/resume_jour?date=` | — | résumé du jour |
| GET | `/api/resume_semaine?date=` | — | résumé de la semaine |
| GET | `/api/resume?mois=` | — | résumé du mois |
| GET | `/api/resume_annuel?annee=` | — | résumé de l'année |
| GET | `/api/resume_global` | — | résumé de tout l'historique |
| GET / PUT | `/api/bourse/parametres` | `{taux_tpcvm}` | `ParametresBourse` |
| GET / POST / PUT / DELETE | `/api/bourse/titres[/{id}]` | `{code, nom, secteur}` | `TitreBourse` / `[TitreBourse]` |
| GET / POST | `/api/bourse/transactions` | `?mois=&annee=` / `TransactionBourseCreate` | `[TransactionBourseOut]` |
| DELETE | `/api/bourse/transactions/{id}` | — | 204 |
| PUT | `/api/bourse/prix/{titre}` | `{cours_actuel}` | `{titre, cours_actuel}` |
| GET / POST / DELETE | `/api/bourse/dividendes[/{id}]` | `?mois=&annee=` / `{date_operation, titre, montant}` | `[DividendeOut]` |
| GET / POST / DELETE | `/api/bourse/frais[/{id}]` | `?mois=&annee=` / `{date_operation, libelle, montant}` | `[FraisBourseOut]` |
| GET / POST / DELETE | `/api/bourse/mouvements[/{id}]` | `?mois=&annee=` / `{date_operation, type_mouvement, montant, libelle}` | `[MouvementBourseOut]` |
| GET | `/api/bourse/positions` | — | `[PositionBourse]` |
| GET | `/api/bourse/gains` | `?mois=&annee=` | `[GainRealise]` |
| GET | `/api/bourse/dashboard` | `?mois=&annee=` | `DashboardBourse` |

---

## 6. Calculs métier

### 6.1 Budget

| Indicateur | Formule |
|---|---|
| Épargne | revenus − dépenses |
| Taux d'épargne | épargne ÷ revenus × 100 |
| Reste à dépenser (mois) | somme des budgets des catégories actives − dépenses |
| Budget journalier | budget mensuel ÷ 30,44 |
| Budget hebdomadaire | budget mensuel × 12 ÷ 52 |
| Projection fin de mois | dépenses à ce jour ÷ jour actuel × nombre de jours du mois |
| Badge ▲/▼ | (actuel − précédent) ÷ précédent × 100 ; « ＝ » si l'écart est inférieur à 0,5 % |
| Couleur « budget vs réel » | vert ≤ 80 %, jaune ≤ 100 %, rouge au-delà |

### 6.2 Bourse

| Indicateur | Formule |
|---|---|
| Montant net d'un achat | qté × cours + frais de la transaction |
| Montant net d'une vente | qté × cours − frais de la transaction |
| **PRU** (coût moyen mobile) | recalculé chronologiquement, titre par titre : un achat ajoute sa quantité et son coût au stock ; une vente utilise le PRU du moment, puis retire `PRU × qté vendue` du coût restant |
| Quantité détenue | Σ achats − Σ ventes |
| Valeur comptable | PRU × quantité détenue |
| Valeur de marché | cours actuel × quantité détenue |
| Plus-value latente | valeur de marché − valeur comptable |
| Performance latente | plus-value latente ÷ valeur comptable |
| Gain brut d'une vente | montant net de la vente − PRU × qté vendue |
| TPCVM | gain brut × taux (15 % par défaut), seulement si le gain est positif |
| Gain net | gain brut − TPCVM |
| Résultat net de la période | gains nets + dividendes − frais de compte (les frais de transaction sont déjà inclus dans les gains nets) |
| **Espèces disponibles** | apports − retraits − Σ achats nets + Σ (ventes nettes − TPCVM) + dividendes − frais de compte, sur tout l'historique |
| Apports nets | apports − retraits |
| Patrimoine Bourse | valeur de marché des titres + espèces disponibles |
| **Performance globale** | patrimoine − apports nets ; en % : ÷ apports nets. Équivaut à gains nets + plus-value latente + dividendes − frais de compte : les gains réinvestis sont comptés une seule fois |

### 6.3 Règle de gestion des transferts

| Situation | Où la saisir |
|---|---|
| Virement banque → compte Bourse | **Apport** dans Bourse → Apports / Retraits (pas une dépense) |
| Achat de titres | Bourse → Transactions |
| Vente ou dividende laissé sur le compte | Bourse → Transactions / Dividendes ; s'ajoute automatiquement aux espèces |
| Réinvestissement | Un nouvel achat, sans nouvel apport |
| Argent rapatrié vers la banque | **Retrait** dans Bourse → Apports / Retraits (pas un revenu) |

Un transfert n'est ni une dépense ni un revenu du Budget : le saisir dans l'onglet Saisie fausserait l'épargne.

---

## 7. Frontend

### 7.1 `index.html`

Une seule page contient :
- l'écran de connexion ;
- l'en-tête (date, bouton de thème jour/nuit, déconnexion) ;
- quatre onglets, accessibles depuis la barre de navigation du bas :
  - **Saisie** : formulaires de dépense et de revenu, transactions du mois en cours ;
  - **Dashboard** : cinq vues (Jour / Semaine / Mois / Année / Global), avec des flèches ‹ › pour changer de période (masquées en vue Global) ;
  - **Bourse** : huit sous-vues (Transactions, Positions, Gains, Dividendes, Frais, Apports / Retraits, Dashboard, Paramètres) ;
  - **Paramètres** : objectif d'épargne, catégories et budgets, sources de revenus, mot de passe.

La navigation se fait sans routeur, en affichant ou masquant les sections. Les scripts sont chargés avec un numéro de version (`app.js?v=14`), à incrémenter à chaque mise à jour du JavaScript pour que les navigateurs rechargent les fichiers.

### 7.2 `js/app.js`

**Utilitaires** (partagés avec `bourse.js`)
- `$(id)` : raccourci pour `getElementById`.
- `esc(v)` : échappe `& < > " '` avant toute insertion d'une donnée saisie dans le HTML. Toute nouvelle donnée affichée via `innerHTML` doit passer par `esc()`.
- `fmt(v)` : formate un montant (`1 234,5 DH`).
- `lireMontant(id)` : lit un montant saisi, avec virgule ou point.
- `auj()` : date du jour en heure locale (et non UTC).
- `toast(msg, ok)` : notification verte ou rouge.
- `api(path, opts)` : enveloppe de `fetch`. Sur 401, affiche l'écran de connexion ; sur une autre erreur, affiche le message du serveur.
- `dessiner(id, cfg)` : (re)crée un graphique Chart.js en détruisant le précédent.
- `paletteActuelle()`, `regrouperAutres()`, `optionsDonutPourcentage()` : palette de 8 couleurs, regroupement des petites parts en « Autres », légendes avec pourcentages.

**Cycle de vie**
1. `init()` applique le thème enregistré, préremplit les dates des formulaires et appelle `/api/me`.
2. Si la session est valide, `demarrerApp()` ; sinon, écran de connexion.
3. `montrer(onglet)` affiche un onglet et recharge ses données à chaque ouverture.

**Dashboards** : `chargerDashJour()`, `chargerDashSemaine()`, `chargerDash()` (mois), `chargerDashAnnee()` et `chargerDashGlobal()`. Les vues Mois, Année et Global ajoutent deux indicateurs Bourse via `resumeBourseSilencieux()`, qui ne remonte jamais d'erreur, pour qu'un problème Bourse ne casse pas le dashboard Budget.

**Thème** : `appliquerTheme()` pose `data-theme` sur `<html>`, mémorise le choix et adapte les graphiques.

### 7.3 `js/bourse.js`

Réutilise les utilitaires d'`app.js`, chargé avant lui.
- `changerVueBourse(v)` : bascule entre les huit sous-vues.
- Le cours actuel d'un titre se modifie directement dans le tableau des positions.
- Le dashboard Bourse a trois modes (Global / Mois / Année) et sa propre navigation ‹ ›.
- Paramètres : taux de TPCVM (affiché en %) et gestion du référentiel des titres.
- `chargerTitresBourse()` alimente l'autocomplétion des codes BVC.

### 7.4 `css/style.css`

- Variables CSS dans `:root` (thème sombre par défaut), redéfinies dans `[data-theme="light"]` pour les fonds, bordures et textes.
- Couleurs métier identiques dans les deux thèmes : orange pour les dépenses, bleu pour les revenus, vert pour l'épargne, rouge pour les alertes.
- Responsive : `.grid2` passe sur une colonne sous 820 px, d'autres ajustements s'appliquent sous 560 px.
- Respecte `prefers-reduced-motion`.

---

## 8. Points restants

**1. Types de colonnes du Budget**
Le module Budget stocke les dates en `TEXT` et les montants en `DOUBLE PRECISION`, alors que le module Bourse utilise `DATE` et `NUMERIC`. Les montants en `float` peuvent accumuler de petites erreurs d'arrondi.
Une migration toucherait toutes les requêtes de `rapports.py` et `transactions.py`, qui filtrent les dates en texte (`LIKE`, `substr`). Elle n'est à envisager qu'après avoir couvert chaque vue du dashboard Budget par des tests.

**2. TPCVM calculée vente par vente**
Les pertes d'une vente ne compensent pas les gains d'une autre vente de la même année. Le total affiché peut donc surestimer l'impôt dû en cas de ventes gagnantes et perdantes la même année. Un avertissement figure dans Bourse → Paramètres ; la règle fiscale exacte est à confirmer avant de modifier le calcul.

**3. Hypothèse sur la TPCVM dans les espèces disponibles**
Le calcul des espèces suppose que l'intermédiaire retient la TPCVM à la source sur le produit de chaque vente. Si le prix de vente saisi est déjà net de cette taxe, elle est déduite deux fois et les espèces paraissent trop basses.

**4. Couverture des tests**
Les tests couvrent les calculs Bourse, le renommage et les 404 du Budget, et les apports/retraits (18 tests). L'authentification, la limitation des connexions et les calculs de `rapports.py` n'ont pas de tests automatisés.

**5. Limitation des connexions en mémoire**
Le compteur d'échecs est remis à zéro au redémarrage et propre à chaque processus serveur. Le blocage se fait par nom d'utilisateur (l'adresse IP n'est pas fiable derrière le proxy de l'hébergeur) : quelqu'un qui connaît le nom d'utilisateur peut bloquer la connexion pendant 15 minutes.

