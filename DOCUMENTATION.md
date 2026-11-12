# Carnet — Documentation technique

Application web personnelle pour suivre son budget (dépenses, revenus, épargne), un portefeuille boursier à la Bourse de Casablanca, ses lectures (livres terminés, bilan annuel) et un carnet (dettes et prêts, échéances) avec rappels et résumé hebdomadaire par Telegram ou e-mail. Toutes les valeurs sont en dirhams (DH).

- **Backend** : Python, FastAPI, PostgreSQL (driver `psycopg` v3, pool `psycopg_pool`)
- **Frontend** : React 19 + TypeScript, compilé avec Vite. Interface Mantine, données via TanStack Query, graphiques Chart.js (react-chartjs-2)
- **Déploiement** : un seul serveur. FastAPI sert à la fois l'API (`/api/...`) et le frontend compilé (`frontend-react/dist/`, sur `/`). Node.js ne sert qu'à développer et compiler, jamais à l'exécution : Vercel construit `dist/` à chaque déploiement.

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
9. [Module Lectures](#9-module-lectures)
10. [Suivi, rappels et résumés](#10-suivi-rappels-et-résumés)
11. [Patrimoine, objectifs, réserve de sécurité et zakat](#11-patrimoine-objectifs-réserve-de-sécurité-et-zakat)
12. [Accueil, sauvegarde, sessions et installation](#12-accueil-sauvegarde-sessions-et-installation)
13. [Opérations récurrentes et prévisions](#13-opérations-récurrentes-et-prévisions)

---

## 1. Architecture générale

```
Personal_Budget/
├── backend/
│   ├── app.py              Point d'entrée : crée l'app FastAPI, branche les routes, sert le frontend
│   ├── config.py           Variables d'environnement (.env) et constantes
│   ├── database.py         Pool de connexions PostgreSQL + création du schéma
│   ├── cours_bvc.py        Cours automatiques des titres BVC (site officiel, Médias24 en secours ; voir §6.3)
│   ├── securite.py         Mots de passe, sessions, limitation des tentatives de connexion
│   ├── sauvegarde.py       Sauvegarde complète en JSON et restauration (voir §12)
│   ├── messagerie.py       Envoi des rappels et du résumé : Telegram et/ou e-mail (voir §10)
│   ├── resume_rendu.py     Mise en forme du résumé hebdomadaire : texte, message Telegram, e-mail HTML
│   ├── schemas.py          Modèles Pydantic (validation des entrées et des sorties)
│   ├── requirements.txt
│   ├── scripts/
│   │   ├── supprimer_bourse.py   Supprime toutes les tables du module Bourse (script manuel)
│   │   └── restaurer_sauvegarde.py   Recharge une sauvegarde complète dans la base (script manuel)
│   ├── tests/
│   │   ├── test_bourse.py        PRU, frais, arrondis, contrôle des ventes
│   │   ├── test_budget.py        Renommage en cascade, erreurs 404
│   │   ├── test_mouvements.py    Apports/retraits, espèces disponibles, performance globale
│   │   ├── test_lectures.py      Bilan annuel, objectifs, relectures, genres
│   │   ├── test_lectures_suivi.py  Rythme, série, note du jour, export Markdown, livres prêtés
│   │   ├── test_patrimoine.py    Patrimoine net, réserve de sécurité, zakat
│   │   ├── test_carnet.py        Reste dû, remboursements refusés, échéances récurrentes
│   │   └── test_rappels.py       Jours de rappel, contenu du résumé, protection de la tâche planifiée
│   └── routes/
│       ├── auth.py               /api/login, /logout, /me, /mot_de_passe
│       ├── configuration.py      catégories, sources de revenus, objectif d'épargne
│       ├── transactions.py       dépenses et revenus
│       ├── rapports.py           résumés jour / semaine / mois / année / global
│       ├── bourse.py             module Bourse
│       ├── lectures.py           module Lectures (livres lus, objectifs, bilan annuel)
│       ├── carnet.py             onglet Suivi (dettes et prêts, échéances)
│       ├── patrimoine.py         patrimoine net, autres actifs, réserve de sécurité, zakat (voir §11)
│       └── rappels.py            message du matin, résumé hebdomadaire, tâche planifiée
├── frontend-react/         Frontend React (voir §7)
│   ├── src/                Code source TypeScript
│   ├── public/             Favicons (copiés tels quels dans dist/)
│   ├── dist/               Build de production servi par FastAPI (généré par npm run build, non versionné)
│   ├── package.json        Dépendances et scripts npm
│   └── vite.config.ts      Build + proxy /api vers FastAPI en développement
├── frontend/               Ancien frontend HTML/JS : servi seulement si frontend-react/dist/ n'existe pas
├── lancer_budget.bat       Lanceur Windows
└── lancer_budget.sh        Lanceur Linux
```

### Déroulement d'une requête

```
Navigateur (application React de frontend-react/dist)
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
- **Schéma idempotent** : il n'y a pas d'outil de migration. `init_db()` s'exécute au démarrage avec `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` et `DROP COLUMN IF EXISTS`, sans risque à rejouer. En production, une seule fois par version déployée (voir `migrations_a_faire()` ci-dessous).
- **Nommage en français** dans tout le code (fonctions, variables, colonnes).

---

## 2. Installation et lancement

### Prérequis
- Python 3.10 ou plus récent
- Une base PostgreSQL accessible
- Node.js 20 ou plus récent, **uniquement pour modifier le frontend** (pas pour lancer l'application)

### Fichier `backend/.env`

```env
DATABASE_URL=postgresql://user:motdepasse@hote:5432/nom_base
ADMIN_UTILISATEUR=hassan
ADMIN_MOT_DE_PASSE=un_mot_de_passe_solide
PORT=8500               # optionnel, 8500 par défaut (lancement local)
COOKIE_SECURE=false     # true en production derrière HTTPS
CORS_ORIGINS=           # optionnel : seulement si le frontend est hébergé sur un autre domaine

# Optionnel : rappels et résumé hebdomadaire (voir §10)
TELEGRAM_BOT_TOKEN=     # jeton du bot donné par @BotFather
TELEGRAM_CHAT_ID=       # identifiant de ta conversation avec le bot
SMTP_HOTE=              # ex : smtp.gmail.com
SMTP_PORT=587
SMTP_UTILISATEUR=       # adresse d'envoi
SMTP_MOT_DE_PASSE=      # Gmail : mot de passe d'application
EMAIL_DESTINATAIRE=     # par défaut : SMTP_UTILISATEUR
CRON_SECRET=            # secret exigé par /api/cron/quotidien
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

### Développer le frontend

```bash
cd frontend-react
npm install          # une seule fois
npm run dev          # http://localhost:5173, rechargement à chaud
```

Le backend doit tourner en parallèle sur le port 8500 : Vite lui redirige les appels `/api` (même origine pour le navigateur, donc cookie de session et CORS inchangés).

Pour voir une modification servie par le backend (port 8500) :

```bash
npm run build        # vérifie les types (tsc) puis produit dist/
```

`dist/` n'est pas versionné (`.gitignore`) : chaque build changeait le nom du bundle et créait des conflits de fusion. Vercel le construit à chaque déploiement : `[tool.vercel.scripts] build` dans `pyproject.toml` lance `backend/construire_frontend.py` (`npm ci --include=dev` puis `npm run build`), après l'installation des paquets Python. Le même script sert en local : `lancer_budget.bat` / `.sh` l'appellent si `dist/index.html` manque. Ne pas définir de « Build Command » dans Vercel (tableau de bord ou `vercel.json`) : elle remplacerait ce script (`tests/test_deploiement.py` vérifie `vercel.json`).

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
- Définit `FRONT_DIR`, le dossier servi en statique : `frontend-react/dist/` s'il contient un `index.html`, sinon l'ancien `frontend/`.
- Lit `DATABASE_URL`, `PORT`, `COOKIE_SECURE`, `ADMIN_UTILISATEUR`, `ADMIN_MOT_DE_PASSE` et `CORS_ORIGINS`.
- Constantes :
  - `DUREE_SESSION_JOURS = 1` et `DUREE_SESSION_LONGUE_JOURS = 30` (« Rester connecté ») : durée d'une session, prolongée pendant l'utilisation (voir §12) ;
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

**`migrations_a_faire()`** : décide si le démarrage doit lancer `init_db()` et `remplir_tpcvm_manquantes()`. La version déployée (`VERSION_DEPLOYEE` : commit Git fourni par Vercel) est notée dans la table `migrations_appliquees` une fois ses migrations réussies ; les démarrages à froid suivants de la même version ne font plus qu'une requête. Un verrou PostgreSQL (`pg_advisory_xact_lock`) empêche plusieurs instances Vercel lancées en même temps d'exécuter les mêmes `CREATE`/`ALTER` en parallèle, ce qui provoquait des erreurs 500 à la première ouverture. En local, sans version connue, les migrations tournent à chaque lancement.

**`init_db()`**, appelée au démarrage (si `migrations_a_faire()` le demande) :
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
| `LimiteurEchecs` / `limiteur_login` | Anti force brute : après **10 échecs en 15 minutes** pour un même nom d'utilisateur (casse et espaces ignorés), les tentatives sont refusées (**429**) pendant 15 minutes, même avec le bon mot de passe. Une réussite remet le compteur à zéro. Protège aussi la vérification du mot de passe actuel lors d'un changement. Les échecs sont gardés en base (`echecs_login`, seulement ceux de la fenêtre en cours) : le compteur est partagé par toutes les instances Vercel et survit aux redémarrages. |

Le cookie de session est `HttpOnly` (inaccessible au JavaScript), `SameSite=Lax` (protection de base contre le CSRF), et `Secure` si `COOKIE_SECURE=true`.

**En-têtes de sécurité** (middleware `entetes_securite` dans `app.py`, sur toutes les réponses) :

| En-tête | Valeur | Rôle |
|---|---|---|
| `Content-Security-Policy` | `default-src 'self'` ; scripts : le bundle et le petit script de thème de `index.html`, autorisé par son empreinte sha256 calculée au démarrage ; styles en ligne (Mantine) et Google Fonts ; images `https:` (couvertures de livres) ; `frame-ancestors 'none'` | un script injecté ne s'exécute pas, l'application ne peut pas être affichée dans un cadre |
| `X-Frame-Options` | `DENY` | même protection pour les anciens navigateurs |
| `X-Content-Type-Options` | `nosniff` | le navigateur respecte le type annoncé d'un fichier |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | les adresses internes (`#/dashboard/...`) ne partent pas vers d'autres sites |
| `Permissions-Policy` | caméra, micro, position et paiement coupés | |

La documentation interactive (`/docs`, `/redoc`, `/openapi.json`) n'a pas de CSP : elle charge ses scripts depuis un CDN. Vercel ajoute lui-même `Strict-Transport-Security`. Si `index.html` reçoit un nouveau script en ligne, son empreinte est prise en compte au démarrage suivant, sans rien modifier.

### 3.4 `schemas.py` — modèles Pydantic

Ces modèles valident automatiquement les données reçues. En cas d'échec, FastAPI renvoie une erreur 422.

Limites communes (types `Nom`, `Libelle`, `Description`, `Montant`... en tête du fichier) : les espaces autour d'un texte sont retirés **avant** de vérifier sa longueur, donc un nom fait d'espaces est refusé. Noms : 100 caractères, codes de titre : 60, libellés : 200, descriptions : 500, notes et commentaires : 2 000 à 5 000. Montants : au plus 10 milliards de DH (`MONTANT_MAX`), cours d'un titre : 10 millions, 50 tags au plus avant nettoyage. Mot de passe : 200 caractères (jamais modifié, espaces compris).

| Modèle | Utilisation | Contraintes |
|---|---|---|
| `LoginIn` | connexion | — |
| `MdpIn` | changement de mot de passe | `nouveau` ≥ 6 caractères |
| `DepenseIn` | nouvelle dépense | `date` au format `AAAA-MM-JJ` (`DateISO`), `montant > 0` |
| `RevenuIn` | nouveau revenu | `date` au format `AAAA-MM-JJ` (`DateISO`), `montant > 0` |
| `CategorieIn` | catégorie | `nom` non vide, `budget ≥ 0` |
| `ObjectifIn`, `NomIn` | objectif, source | — |
| `ParametresBourse` | paramètres Bourse | `taux_tpcvm` entre 0 et 1 (ne sert plus qu'à remplir la TPCVM des ventes anciennes) |
| `TitreBourseIn` / `TitreBourse` | référentiel des titres | `code`, `nom`, `secteur` |
| `TransactionBourseCreate` / `Out` | achat/vente | `type_instrument` ∈ {Action, Obligation, OPCVM, IPO}, `type_operation` ∈ {Achat, Vente}, `quantite > 0` |
| `DividendeCreate` / `Out`, `FraisBourseCreate` / `Out` | dividendes et frais de compte | `montant > 0` |
| `MouvementBourseCreate` / `Out` | apports et retraits | `type_mouvement` ∈ {Apport, Retrait}, `montant > 0` |
| `PositionBourse`, `GainRealise`, `DashboardBourse` | sorties calculées | — |
| `LivreIn` / `LivreOut` | livre terminé | `titre` non vide, `pages > 0`, `note` entre 1 et 5, `date_debut ≤ date_fin` |
| `GenreOut`, `ObjectifsLecture` | genres, objectifs de lecture | objectifs entiers ≥ 0 |

`DateISO` vérifie qu'il s'agit d'une vraie date (refuse `18/09/2026` ou `2026-02-30`) mais la garde sous forme de chaîne : les dates du Budget sont stockées en texte.

### 3.5 `app.py` — point d'entrée

1. Ajoute `backend/` au `sys.path`, pour que l'application se lance depuis n'importe quel dossier.
2. Déclare le cycle de vie (`lifespan`) : `init_db()` et `remplir_tpcvm_manquantes()` s'exécutent au démarrage du serveur, pas à l'import du module, et une seule fois par version déployée (`migrations_a_faire()`) ; le pool de connexions est fermé à l'arrêt. Importer `app` (tests, build Vercel) ne touche donc pas la base.
3. Crée l'application FastAPI. CORS n'est activé que si `CORS_ORIGINS` est renseigné, et seulement pour ces origines.
4. Branche les routeurs (un par fichier de `routes/`, plus celui de la tâche planifiée `/api/cron`).
5. Monte `FRONT_DIR` sur `/` **après** les routes API, pour que `/api/...` reste prioritaire.
6. Lancé directement, démarre `uvicorn` sur `0.0.0.0:PORT`.

### 3.6 `routes/auth.py`

- `POST /api/login` : vérifie les identifiants (avec limitation des tentatives), crée la session et pose le cookie. Le message d'erreur est le même que l'utilisateur existe ou non.
- `POST /api/logout` : supprime la session et le cookie.
- `GET /api/me` : renvoie le nom de l'utilisateur. Le frontend s'en sert au chargement pour savoir s'il faut afficher l'écran de connexion.
- `PUT /api/mot_de_passe` : vérifie l'ancien mot de passe, enregistre le nouveau et **supprime toutes les sessions** de l'utilisateur, ce qui le déconnecte de tous ses appareils.

### 3.7 `routes/configuration.py`

- `GET /api/categories` renvoie en une seule requête les catégories, les sources et l'objectif d'épargne.
- Les `POST` réactivent un élément désactivé du même nom au lieu de provoquer une erreur d'unicité.
- Les `PUT` (renommer) mettent à jour les lignes déjà saisies (`depenses.categorie`, `revenus.source`) par la clé étrangère `ON UPDATE CASCADE`, sans code dans la route (voir « Clés étrangères » au §4).
- Les `DELETE` désactivent l'élément (`actif=0`).
- `PUT` et `DELETE` renvoient **404** si l'id n'existe pas.

### 3.8 `routes/transactions.py`

Création, modification (`PUT`, tous les champs y compris la date) et suppression des dépenses et revenus (404 si la ligne n'existe pas). `GET /api/transactions?mois=AAAA-MM` liste les deux types pour un mois, avec un filtre `date LIKE '2026-09-%'`.

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
1. charge toutes les transactions triées par date (avec la TPCVM saisie sur chaque vente) et les cours actuels ;
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
| `depenses` | `id`, `date` TEXT, `categorie` TEXT, `description`, `montant`, `paiement`, `cree_le` | catégorie stockée par son nom (clé étrangère vers `categories.nom`) ; `paiement` n'est plus utilisée (conservée pour l'historique) |
| `revenus` | `id`, `date` TEXT, `source`, `description`, `montant`, `cree_le` | source stockée par son nom (clé étrangère vers `sources_revenus.nom`), NULL sans source ; une source libre (« Autre… ») est ajoutée aux sources comme retirée |
| `echecs_login` | `id`, `cle`, `le` | échecs de mot de passe de la fenêtre en cours (anti force brute, §3.3) |
| `sources_revenus` | `id`, `nom` UNIQUE, `actif` | |
| `paiements` | `id`, `nom` UNIQUE, `actif` | n'est plus utilisée (conservée pour l'historique) |
| `params` | `cle` PK, `valeur` | contient `objectif_epargne`, `prevision_plancher` |
| `recurrences` | `id`, `type` (`depense`/`revenu`), `categorie`, `source`, `description`, `montant`, `jour` (1–31), `tags`, `auto`, `actif`, `debut`, `dernier_mois` | opérations récurrentes (§13) ; `categorie` et `source` : clés étrangères vers les noms, `debut` et `dernier_mois` en AAAA-MM |
| `utilisateurs` | `id`, `nom` UNIQUE, `mdp_hash` | |
| `sessions` | `token` PK, `utilisateur_id` FK, `expire` | |

Index : `depenses(date)`, `revenus(date)`.

### Bourse

| Table | Colonnes principales | Remarques |
|---|---|---|
| `bourse_parametres` | `taux_tpcvm`, `cours_auto_le` | une seule ligne ; `cours_auto_le` date la dernière récupération automatique des cours |
| `bourse_transactions` | `date_operation` DATE, `titre`, `isin`, `type_instrument`, `type_operation`, `quantite`, `cours_unitaire`, `autres_frais` | contraintes `CHECK` sur les types et les quantités |
| `bourse_prix` | `titre` PK, `cours_actuel`, `maj_le`, `manuel` | un seul cours par titre, sans historique ; `manuel` = saisi à la main, non écrasé par les cours automatiques |
| `bourse_titres` | `code` UNIQUE, `nom`, `secteur`, `isin`, `actif` | référentiel BVC ; l'ISIN rapproche le titre de la source de cours de secours ; `titre` des transactions, dividendes, cours et cours passés y fait référence (clé étrangère) |

**Clés étrangères** (`database.CLES_ETRANGERES`). `depenses.categorie` → `categories.nom`, `revenus.source` → `sources_revenus.nom`, et le `titre` de `bourse_transactions`, `bourse_dividendes`, `bourse_prix` et `bourse_cours_historique` → `bourse_titres.code`, toutes `ON UPDATE CASCADE` : renommer une catégorie, une source ou un code renomme les lignes qui y font référence, et la base refuse un nom inconnu, même écrit hors de l'application. Une catégorie, une source ou un titre n'est jamais supprimé, seulement retiré (`actif = 0`). La violation d'une clé devient une erreur **400** lisible (`references_valides()` dans les routes, et un gestionnaire global dans `app.py` en filet de sécurité). Lors de la pose des clés, chaque nom orphelin déjà saisi a été ajouté comme élément retiré, sans rien perdre.
| `bourse_dividendes` | `date_operation`, `titre`, `montant` | montant net reçu |
| `bourse_frais` | `date_operation`, `libelle`, `montant` | abonnement courtier, tenue de compte, droits de garde… |
| `bourse_mouvements` | `date_operation`, `type_mouvement` (Apport / Retrait), `montant`, `libelle` | transferts banque ↔ compte Bourse |

### Lectures

| Table | Colonnes principales | Remarques |
|---|---|---|
| `lectures_livres` | `titre`, `auteur`, `genre`, `date_debut` (optionnelle), `date_fin`, `pages`, `note` (1 à 5), `commentaire` | `genre` : clé étrangère vers `lectures_genres.nom` (`ON UPDATE CASCADE`, comme `lectures_a_lire.genre`), NULL sans genre (`""` dans l'API) ; `CHECK date_debut ≤ date_fin` |
| `lectures_genres` | `id`, `nom` UNIQUE, `actif` | suppression douce, comme les catégories |

| `lectures_progression` | `a_lire_id`, `date`, `page` | page atteinte dans un livre en cours, une ligne par jour ; supprimée avec le livre |
| `lectures_jours` | `date` | jours où l'on a lu (série), gardés quand un livre est terminé |
| `lectures_prets` | `titre`, `personne`, `date_pret`, `date_retour` (NULL = pas rendu), `note` | livres prêtés |

Les objectifs de lecture sont dans `params` : `objectif_lecture_annuel` (24 par défaut) et `objectif_lecture_mensuel` (2).

### Suivi

| Table | Colonnes principales | Remarques |
|---|---|---|
| `dettes` | `sens` (`pret` / `emprunt`), `personne`, `montant`, `date_operation`, `echeance` (optionnelle), `libelle` | `pret` : on me doit ; `emprunt` : je dois |
| `dettes_remboursements` | `dette_id`, `date_operation`, `montant`, `libelle` | supprimés avec leur dette (`ON DELETE CASCADE`) |
| `echeances` | `titre`, `categorie`, `date_echeance`, `rappel_jours`, `recurrence_mois` (NULL = ponctuelle), `note`, `montant` (optionnel), `objectif_id` | `objectif_id` : objectif qui provisionne l'échéance (`ON DELETE SET NULL`, voir §10) |

| `actifs` | `nom`, `type`, `valeur`, `verse`, `zakat`, `maj_le`, `note` | actifs hors Bourse, valeur saisie à la main (voir §11) |

`bourse_transactions.note` garde la raison d'un achat ou d'une vente. Trois clés de `params` règlent le patrimoine : `solde_depart`, `zakat_prix_or` (DH par gramme) et `zakat_debut_hawl` (numéro de jour).

Deux clés de `params` servent à la tâche planifiée : `cron_dernier_jour` (dernier jour traité, en numéro de jour) et `resume_hebdo_patrimoine` (valeur du compte Bourse au dernier résumé).

| `objectifs` | `nom`, `cible`, `date_limite` (optionnelle), `note`, `archive`, `tag`, `tag_depuis` | objectifs d'épargne par projet (voir §11) ; `tag` : objectif suivi par les dépenses portant ce tag, depuis `tag_depuis` |
| `objectifs_versements` | `objectif_id`, `date_operation`, `montant` (négatif = argent repris), `libelle` | supprimés avec leur objectif (`ON DELETE CASCADE`) |
| `patrimoine_historique` | `date` PK, `total`, `liquidites`, `bourse`, `autres_actifs`, `creances`, `dettes`, `estime`, `maj_le` | patrimoine noté une fois par jour, pour sa courbe (voir §11) ; `estime` = fin de mois reconstituée après coup |
| `bourse_cours_historique` | (`titre`, `date`) PK, `cours`, `cree_le` | cours passés saisis à la main (relevés de fin de mois du courtier), pour la reconstitution de la courbe |
| `rapprochements` | `date`, `solde_reel`, `solde_calcule`, `comptes` (JSONB `[{nom, montant}]`), `regle` (`depense` / `revenu` / NULL), `note` | pointages du solde (voir §11) |
| `alertes_ignorees` | `cle` PK, `le` | alertes de dépenses écartées à la main (voir §11) |
| `telegram_messages` | `update_id` PK, `le`, `attente` (JSONB) | messages reçus du bot, traités une seule fois, gardés 7 jours ; `attente` : dépense qui attend sa catégorie. Hors sauvegarde |

Les modules Bourse et Suivi utilisent les types `DATE` et `NUMERIC`. Le module Budget utilise `TEXT` pour les dates et `DOUBLE PRECISION` pour les montants.

**`modifie_le`** : chaque table de données (Budget, Bourse, Lectures, Suivi, objectifs, `params`, `utilisateurs`) a une colonne `modifie_le TIMESTAMPTZ`, mise à jour par le déclencheur `trg_modifie_le` (fonction `maj_modifie_le()`) à chaque `UPDATE`, y compris fait hors de l'application. À sa création, elle a reçu `cree_le` pour les lignes existantes (ou la date de la migration pour les tables qui n'en ont pas). La liste est `TABLES_MODIFIE_LE` dans `database.py`.

`cron_journal` garde les 30 derniers appels de la tâche planifiée (`le`, `etat`, `detail`) ; `migrations_appliquees` les versions déployées dont les migrations ont tourné.

---

## 5. Référence de l'API

Toutes les routes sauf `/api/login`, `/api/logout` et `/api/cron/quotidien` (protégée par `CRON_SECRET`) exigent le cookie `session`.

| Méthode | Route | Corps / paramètres | Réponse |
|---|---|---|---|
| POST | `/api/login` | `{utilisateur, mot_de_passe}` | `{ok}` + cookie ; 429 si trop d'échecs |
| POST | `/api/logout` | — | `{ok}` |
| GET | `/api/me` | — | `{utilisateur}` |
| PUT | `/api/mot_de_passe` | `{actuel, nouveau}` | `{ok, message}` |
| GET | `/api/categories` | — | `{categories, sources, objectif_epargne}` |
| POST / PUT / DELETE | `/api/categories[/{id}]` | `{nom, budget, fixe, a_partir_de}` | `{ok}` ; budget et « fixe » valables à partir du mois `a_partir_de` (AAAA-MM, mois en cours par défaut), les mois antérieurs gardent les leurs ; 409 si le nom existe déjà |
| GET | `/api/categories/{id}/historique` | — | `[{mois_debut, budget, fixe}]` (table `budgets_historique`) |
| DELETE | `/api/categories/{id}/historique/{mois}` | — | `{ok}` ; retire un changement de budget (pas le dernier restant) |
| PUT | `/api/objectif` | `{objectif}` | `{ok}` |
| POST / PUT / DELETE | `/api/sources[/{id}]` | `{nom}` | `{ok}` |
| POST / PUT / DELETE | `/api/depenses[/{id}]` | `{date, categorie, description, montant, tags}` | `{id}` / `{ok}` / la ligne supprimée ; catégorie active obligatoire |
| POST / PUT / DELETE | `/api/revenus[/{id}]` | `{date, source, description, montant, tags}` | `{id}` / `{ok}` / la ligne supprimée |
| POST | `/api/depenses/restaurer`, `/api/revenus/restaurer` | la ligne renvoyée par DELETE | `{id}` ; « Annuler » une suppression (même identifiant) |
| GET | `/api/recherche` | `?q=&limite=&decalage=` ; `#tag`, montant exact, texte | `{resultats, nb, total_depenses, total_revenus}` sur tout l'historique |
| GET | `/api/suggestions` | `?type=depenses\|revenus&nom=` | 5 dernières descriptions `[{description, montant}]` |
| GET | `/api/tags` | — | `[{tag, nb, depenses, revenus, premier, dernier}]` |
| GET | `/api/export/csv` | `?debut=&fin=` (AAAA-MM-JJ, facultatifs) | fichier CSV (« ; », virgule décimale, BOM) |
| POST | `/api/import` | `{lignes: [{type, date, nom, description, montant, tags}], simulation}` | statut de chaque ligne (`ajoutee`, `doublon`, `erreur`) ; rien n'est écrit si `simulation` |
| GET | `/api/transactions?mois=` | — | `{depenses, revenus}` |
| GET | `/api/resume_jour?date=` | — | résumé du jour |
| GET | `/api/resume_semaine?date=` | — | résumé de la semaine |
| GET | `/api/resume?mois=` | — | résumé du mois, comparé au mois précédent et au même mois l'an dernier (`*_annee_precedente`, `budget_vs_reel[].an_dernier`) |
| GET | `/api/resume_annuel?annee=` | — | résumé de l'année |
| GET | `/api/resume_global` | — | résumé de tout l'historique |
| GET / PUT | `/api/bourse/parametres` | `{taux_tpcvm}` | `ParametresBourse` |
| GET / POST / PUT / DELETE | `/api/bourse/titres[/{id}]` | `{code, nom, secteur, isin}` | `TitreBourse` / `[TitreBourse]` |
| GET / POST | `/api/bourse/transactions` | `?mois=&annee=` / `TransactionBourseCreate` | `[TransactionBourseOut]` |
| PUT / DELETE | `/api/bourse/transactions/{id}` | `TransactionBourseCreate` / — | `TransactionBourseOut` / 204 ; refusé si une quantité détenue deviendrait négative |
| PUT | `/api/bourse/prix/{titre}` | `{cours_actuel}` | `{titre, cours_actuel}` ; passe le titre en cours manuel (verrouillé) |
| PUT | `/api/bourse/prix/{titre}/auto` | — | `CoursActualisation` ; déverrouille le titre puis récupère les cours |
| POST | `/api/bourse/cours/actualiser` | `?force=` | `CoursActualisation` |
| GET | `/api/bourse/historique/couverture` | — | `[{titre, premier_achat, detenu, nb, nb_import, debut, fin}]` |
| POST / DELETE | `/api/bourse/historique/{titre}/import` | `{valeurs: [{date, valeur}]}` | `{importees, deja_notees, debut, fin}` ; 400 si le fichier ne correspond pas au titre / 204 |
| GET | `/api/bourse/indices` | — | `{defaut, premier_mouvement, indices: [{code, nom, dividendes, nb, nb_import, debut, fin, derniere}]}` |
| GET | `/api/bourse/indices/comparaison` | `?indice=` (MASRN par défaut) | `{etat, manque_avant, toi: {valeur, rendement}, reference: {valeur, rendement}, ecart, points: [{date, indice, toi}], …}` |
| POST / DELETE | `/api/bourse/indices/{code}/import` | `{valeurs: [{date, valeur}]}` | `{importees, deja_notees, debut, fin}` ; 400 si le fichier ne correspond pas à l'indice / 204 |
| GET | `/api/bourse/cours-en-retard` | — | `[{titre, manuel, depuis, jours}]` (jours de bourse) |
| GET / POST / DELETE | `/api/bourse/jours-feries[/{date}]` | `{date, libelle}` | `{variables: [{date, libelle}], fixes: [{mois, jour, libelle}]}` / 201 / 204 |
| GET | `/api/bourse/historique` | `?jours=`, `?titre=` (facultatifs) | sans titre : `{titres, points: [{date, valeur, cout}]}` ; avec titre : `{titre, points: [{date, cours, manuel}]}` |
| GET / POST / PUT / DELETE | `/api/bourse/dividendes[/{id}]` | `?mois=&annee=` / `{date_operation, titre, montant}` | `[DividendeOut]` |
| GET / POST / PUT / DELETE | `/api/bourse/frais[/{id}]` | `?mois=&annee=` / `{date_operation, libelle, montant}` | `[FraisBourseOut]` |
| GET / POST / PUT / DELETE | `/api/bourse/mouvements[/{id}]` | `?mois=&annee=` / `{date_operation, type_mouvement, montant, libelle}` | `[MouvementBourseOut]` |
| GET | `/api/bourse/positions` | — | `[PositionBourse]`, avec dividendes des 12 derniers mois ramenés aux actions détenues aujourd'hui et rendement (sur coût, sur valeur de marché) |
| GET / PUT | `/api/bourse/cibles` | `{cibles: [{secteur, cible}]}` (ratio, somme ≤ 1) | `[{secteur, cible}]` ; PUT remplace toutes les cibles |
| GET | `/api/bourse/fiscalite` | `?annee=` | plus et moins-values, résultat de cession, TPCVM retenue et « au taux », dividendes, détail par titre |
| GET | `/api/bourse/gains` | `?mois=&annee=` | `[GainRealise]` |
| GET | `/api/bourse/dashboard` | `?mois=&annee=` | `DashboardBourse`, dont `rendement_annualise` (TRI, `null` avant 3 mois) |
| GET / POST / PUT / DELETE | `/api/lectures/livres[/{id}]` | `?annee=` / `LivreIn` | `[LivreOut]` / `LivreOut` / 204 |
| GET | `/api/lectures/auteurs` | — | `[str]` (autocomplétion) |
| GET / POST / PUT / DELETE | `/api/lectures/a_lire[/{id}]` | `ALireIn` (`date_debut` renseignée = en cours) | `[ALireOut]` / `ALireOut` / 204 |
| POST | `/api/lectures/a_lire/{id}/terminer` | `LivreIn` | `LivreOut` ; le livre passe au journal avec ses notes |
| GET / POST / PUT / DELETE | `/api/lectures/notes[/{id}]` | `?livre_id=` ou `?a_lire_id=` / `{livre_id \| a_lire_id, type, texte, page}` | `[NoteOut]` / `NoteOut` / 204 |
| GET / POST / PUT / DELETE | `/api/lectures/genres[/{id}]` | `{nom}` | `[GenreOut]` / `{ok}` ; 409 si le nouveau nom existe déjà |
| GET / PUT | `/api/lectures/objectifs` | `{annuel, mensuel}` | `ObjectifsLecture` |
| GET | `/api/lectures/bilan` | `?annee=` | bilan de l'année (voir §9) |
| PUT | `/api/lectures/a_lire/{id}/progression` | `{page}` | `ALireOut` avec `page_actuelle`, `pages_par_jour`, `fin_estimee` ; 400 au-delà du nombre de pages |
| GET | `/api/lectures/serie` | — | `{serie, record, lu_aujourdhui}` |
| GET | `/api/lectures/note_du_jour` | `?decalage=` | une note ou citation avec le titre et l'auteur du livre, ou `null` |
| GET | `/api/lectures/notes/export` | `?livre_id=` ou `?a_lire_id=` | fichier Markdown du livre |
| GET | `/api/lectures/notes/export_tout` | — | archive ZIP, un fichier Markdown par livre annoté |
| GET / POST / PUT / DELETE | `/api/lectures/prets[/{id}]` | `PretLivreIn` | `[PretLivreOut]` (avec `jours`) / `PretLivreOut` / 204 |
| GET | `/api/bourse/dividendes/calendrier` | — | `{total, lignes}` : dividendes attendus sur 12 mois |
| GET | `/api/patrimoine` | — | composition, actifs, réserve de sécurité, zakat (voir §11) ; note aussi le patrimoine du jour dans `patrimoine_historique` |
| GET | `/api/patrimoine/historique` | `?jours=` (facultatif) | `[{date, estime, total, liquidites, bourse, autres_actifs, creances, dettes}]`, du plus ancien au plus récent |
| POST | `/api/patrimoine/historique/reconstituer` | — | recalcule les fins de mois passées (`{points, debut, fin}`) |
| GET | `/api/patrimoine/cours-passes` | `?jour=AAAA-MM-JJ` | titres détenus ce jour-là : `{titre, quantite, saisi, estime, source, source_date}` |
| PUT | `/api/patrimoine/cours-passes` | `{jour, cours: [{titre, cours\|null}]}` | enregistre (ou retire, `null`) des cours passés, puis recalcule les fins de mois |
| GET | `/api/patrimoine/rapprochements` | — | `{solde_calcule, historique, jours_sans_depense, depuis, a_refaire_jours}` : liquidités du jour, 12 derniers pointages, jours sans dépense depuis le dernier |
| POST | `/api/patrimoine/rapprochements` | `{comptes: [{nom, montant}], note, enregistrer_ecart, categorie}` | le pointage avec son `ecart` ; avec `enregistrer_ecart`, l'écart devient une dépense (dans `categorie`, 400 sans elle) ou un revenu du jour, tag `pointage` |
| DELETE | `/api/patrimoine/rapprochements/{id}` | — | 204 (l'opération d'écart reste dans le Budget) |
| GET | `/api/alertes` | — | `[{cle, type: categorie\|hausse\|doublon, categorie, titre, detail, montant}]` : dépenses inhabituelles (voir §11) |
| POST | `/api/alertes/ignorer` | `{cle}` | 204 : l'alerte ne revient plus |
| GET | `/api/telegram/etat` | — | `{configure, actif, adresse, erreur}` : saisie par Telegram (voir §10) |
| POST | `/api/telegram/activer` · `/desactiver` | — | déclare (ou retire) le webhook auprès de Telegram, à l'adresse de la requête ; 400 en local |
| POST | `/api/telegram/webhook` | mise à jour Telegram ; en-tête `X-Telegram-Bot-Api-Secret-Token` | `{ok}` ; **sans session** : appelé par Telegram ; 401 sans le secret, 503 si Telegram n'est pas configuré |
| GET / POST / PUT / DELETE | `/api/objectifs[/{id}]` | `{nom, cible, date_limite, note, archive, tag, tag_depuis}` (PUT : tous les champs, un tag absent est retiré) | `[ProjetOut]` / `ProjetOut` (avec `verse`, `reste`, `progression`, `mois_restants`, `par_mois`, `en_retard`, `versements`, `depense`, `reserve`, `depassement`, `operations`) / 204 |
| POST | `/api/objectifs/{id}/versements` | `{date_operation, montant, libelle}` (montant négatif = argent repris) | `ProjetOut` ; 400 si l'on reprend plus que ce qui est de côté |
| DELETE | `/api/objectifs/versements/{id}` | — | 204 ; 400 si le total mis de côté deviendrait négatif |
| GET / POST / PUT / DELETE | `/api/recurrences[/{id}]` | `{type, nom, description, montant, jour, tags, auto, actif, debut}` (`nom` : catégorie ou source) | récurrences avec `prochain_mois`, `prochaine_date`, `en_attente` / 204 |
| GET | `/api/recurrences/a-generer` | — | `[{id, type, nom, description, montant, auto, mois, date, a_venir}]` jusqu'au mois en cours |
| POST | `/api/recurrences/generer` | `{elements: [{id, mois, montant?}]}` | `{generees, ignorees}` (un mois déjà fait ou sauté est ignoré) |
| POST | `/api/recurrences/{id}/passer` | `{mois}` | `{ok}` ; 409 si ce n'est pas le prochain mois attendu |
| GET | `/api/recurrences/suggestions` | — | `[{type, nom, description, montant, jour, tags, moyenne}]` |
| GET | `/api/previsions` | `?mois=` (1–12, 6 par défaut) | `{depart, plancher, mois: [{mois, revenus, depenses, echeances, dettes, solde, bas, haut, reserve, libre, detail}], point_bas, epargne_prevue, rythme_objectifs, alertes}` |
| PUT | `/api/previsions/reglages` | `{plancher}` | `{ok}` |
| PUT | `/api/patrimoine/reglages` | `{solde_depart, prix_or_gramme, debut_hawl}` | `{ok}` |
| POST / PUT / DELETE | `/api/patrimoine/actifs[/{id}]` | `ActifIn` | l'actif / 204 |
| GET | `/api/sauvegarde` | — | fichier JSON de toutes les tables (sans comptes ni sessions) |
| GET / POST / PUT / DELETE | `/api/carnet/dettes[/{id}]` | `DetteIn` | `[DetteOut]` / `DetteOut` (avec `rembourse`, `reste`, `remboursements`) / 204 ; 400 si le montant passe sous le déjà remboursé |
| POST | `/api/carnet/dettes/{id}/remboursements` | `{date_operation, montant, libelle}` | `DetteOut` ; 400 si le montant dépasse le reste dû ou précède le prêt |
| DELETE | `/api/carnet/remboursements/{id}` | — | 204 |
| GET / POST / PUT / DELETE | `/api/carnet/echeances[/{id}]` | `EcheanceIn` (avec `montant`, `provisionner`) | `[EcheanceOut]` / `EcheanceOut` (avec `jours_restants`, `a_rappeler`, `montant`, `objectif_id`, `provision`) / 204 |
| POST | `/api/carnet/echeances/{id}/reporter` | — | `EcheanceOut` : la date avance de `recurrence_mois` (et l'objectif de provision passe à la période suivante) ; 400 si l'échéance est ponctuelle |
| GET | `/api/rappels/etat` | — | `{canaux, cron, envois, passages, dernier_succes}` (aucun secret) ; `dernier_succes` : dernier appel de la tâche planifiée qui n'a pas échoué |
| GET | `/api/rappels/apercu` | `?periode=semaine\|mois\|annee` | `{rappels, sujet, resume, html}` : ce qui serait envoyé maintenant (`html` : l'e-mail) |
| POST | `/api/rappels/envoyer` | `?periode=semaine\|mois\|annee` | `{canaux}` : envoie le résumé choisi tout de suite ; 502 si aucun canal ou envoi refusé |
| GET | `/api/cron/quotidien` | en-tête `Authorization: Bearer <CRON_SECRET>`, `?force=` | `{etat, envoyes}` ; **sans session** ; 401 sans le secret, 503 si `CRON_SECRET` est vide |

---

## 6. Calculs métier

### 6.1 Budget

| Indicateur | Formule |
|---|---|
| Épargne | revenus − dépenses |
| Taux d'épargne | épargne ÷ revenus × 100 |
| Liquidités (vue Globale) | épargne totale − apports nets Bourse |
| Patrimoine net (vue Globale) | liquidités + patrimoine Bourse (titres au cours actuel + espèces) ; remplace la carte « Épargne totale » quand les données Bourse sont disponibles |
| Reste à dépenser (mois) | somme des budgets des catégories actives − dépenses |
| Budget journalier | budget mensuel des catégories variables ÷ 30,44, comparé aux dépenses variables du jour (les catégories cochées « Fixe » — loyer, factures — en sont exclues) |
| Budget hebdomadaire | budget mensuel des catégories variables × 12 ÷ 52, comparé aux dépenses variables de la semaine |
| Projection fin de mois | Σ catégories fixes max(dépensé, budget) + dépenses variables à ce jour ÷ jour actuel × nombre de jours du mois |
| Badge ▲/▼ | (actuel − précédent) ÷ précédent × 100 ; « ＝ » si l'écart est inférieur à 0,5 %. Pour le mois ou la semaine en cours, la période précédente est prise jusqu'au même jour (le 1er–10 contre le 1er–10) |
| Badge « N−1 » (vue Mois) | même calcul contre le même mois de l'année précédente, plus parlant pour les dépenses saisonnières (été, rentrée, fêtes) ; même règle du « jusqu'au même jour » pour le mois en cours. Dans « Budget vs Réel », l'info-bulle d'une catégorie donne son montant l'an dernier |
| Alerte de saisie | à la saisie d'une dépense : ce que la catégorie a déjà consommé de son budget du mois (celui de la date saisie), puis le pourcentage avec cette dépense. Après l'enregistrement, une notification ambre à partir de 80 %, rouge au-delà de 100 %. Calculé dans le navigateur à partir de `/api/resume` |
| Moyennes, meilleur/pire mois, objectif atteint (vues Année et Globale) | calculés sur les mois terminés uniquement : le mois en cours est exclu |
| Budget annuel par catégorie (vue Année) | budget mensuel × mois écoulés (ex : 9,3 au 10 octobre) pour l'année en cours, × 12 pour une année passée |
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
| TPCVM | saisie manuellement sur chaque vente (montant de l'avis d'opéré), aucun calcul |
| Gain net | gain brut − TPCVM |
| Résultat net de la période | gains nets + dividendes − frais de compte (les frais de transaction sont déjà inclus dans les gains nets) |
| **Espèces disponibles** | apports − retraits − Σ achats nets + Σ (ventes nettes − TPCVM) + dividendes − frais de compte, sur tout l'historique |
| Apports nets | apports − retraits |
| Patrimoine Bourse | valeur de marché des titres + espèces disponibles |
| **Performance globale** | patrimoine − apports nets ; en % : ÷ apports nets. Équivaut à gains nets + plus-value latente + dividendes − frais de compte : les gains réinvestis sont comptés une seule fois. Ce % ignore la date des apports : un apport d'hier le fait baisser |
| **Rendement annualisé** (TRI) | taux annuel r tel que Σ flux ÷ (1 + r)^(jours depuis le premier flux ÷ 365) = 0, avec les apports en négatif, les retraits en positif et le patrimoine Bourse du jour comme dernier flux positif (`taux_rendement_annualise()`, résolu par dichotomie). Tient compte de la date de chaque apport : comparable à un livret ou au MASI. Non calculé avant 90 jours d'historique |
| Dividende par action | montant reçu ÷ quantité détenue le jour du versement (`dividendes_par_action()`) |
| Rendement des dividendes d'une position | Σ dividende par action × quantité détenue aujourd'hui, sur les 12 derniers mois, ÷ valeur comptable (et ÷ valeur de marché). Ramené à la quantité actuelle : après une vente partielle, le dividende reçu avait été versé sur plus d'actions |

### 6.3 Cours automatiques

`cours_bvc.py` récupère les cours auprès de deux sources, essayées dans l'ordre. Aucune n'est une API documentée : elles peuvent changer ou devenir injoignables.

1. **Bourse de Casablanca** (`casablanca-bourse.com/live-market/actions`) : les cours sont dans le JSON embarqué dans la page, identifiés par le code BVC. Cinq codes de l'application diffèrent du symbole officiel (`SYMBOLES_OFFICIELS`). Le site n'envoie pas son certificat intermédiaire : il est fourni dans `backend/certs/sectigo_dv_r36.pem` (valable jusqu'en 2036, à remplacer si le site change d'autorité de certification). La vérification TLS reste active.
2. **Médias24** (secours) : flux JSON identifié par ISIN, d'où la colonne `isin` de `bourse_titres`. Protégé par Cloudflare, il refuse souvent les serveurs des hébergeurs (HTTP 403) : il ne sert en pratique qu'en local.

- **Déclenchement** : chaque matin par la tâche planifiée (§10), à l'ouverture du Dashboard ou de la Bourse (`useCoursAuto`), au plus une fois toutes les 15 minutes, et par le bouton « Actualiser les cours » (sans délai).
- **Titres concernés** : ceux détenus qui ne sont pas en cours manuel.
- **Cours manuel** : saisir un cours dans Positions le verrouille ; il n'est plus écrasé jusqu'à sa remise en automatique (icône à côté de « manuel »).
- **Échec** : si aucune source ne répond, rien n'est modifié, les derniers cours connus restent affichés et la cause est écrite dans les logs du serveur (ligne `[cours]`).
- **Historique** : la clôture du jour, notée **une fois par jour de bourse** dans `bourse_prix_historique(titre, date, cours, manuel)` par la tâche du soir `GET /api/cron/cours-du-soir` (Vercel Cron à 19 h UTC, soit 20 h au Maroc, 19 h pendant le Ramadan : toujours après la clôture de 15 h 30). `cours_du_soir()` récupère les cours (`force=True`) puis `noter_cours_du_jour()` écrit une ligne par titre détenu : le cours tout juste récupéré, ou le cours saisi à la main pour un titre en manuel. Un titre automatique dont le cours n'a pas pu être récupéré n'a pas de ligne ce jour-là (un ancien cours ne passe pas pour une clôture). Rien n'est noté ailleurs : ni le matin, ni à l'actualisation, ni à la saisie manuelle. Les sources ne donnent que le cours du jour : l'historique commence le jour de sa mise en place.
- **Jours de bourse** (`raison_fermeture()`) : ni samedi, ni dimanche, ni jour férié. Les fêtes à date fixe sont dans `FERIES_FIXES` (`routes/bourse.py`) ; les fêtes religieuses, à date variable, se saisissent dans **Bourse → Paramètres → Jours fériés de la Bourse** (table `bourse_jours_feries`, `GET / POST /api/bourse/jours-feries`, `DELETE /api/bourse/jours-feries/{date}`). Ajouter un jour férié retire le cours éventuellement noté ce jour-là.
- **Cours passés importés** (Bourse → Paramètres → « Cours passés des titres », ou le bouton sous la courbe « Valeur du portefeuille » ; `POST /api/bourse/historique/{titre}/import`) : le fichier « Market Data → Cours » de la Bourse de Casablanca (jusqu'à 3 ans) remplit `bourse_prix_historique` avant le début des clôtures du soir, avec `source = 'import'`. Une clôture notée le soir n'est jamais remplacée ; si le fichier s'en écarte de plus de 10 % un même jour, tout est refusé (fichier d'un autre titre). `DELETE …/import` retire les cours importés ; `GET /api/bourse/historique/couverture` liste, pour chaque titre déjà acheté, les cours connus et la date du premier achat à couvrir. Les cours importés servent à la courbe du portefeuille (qui commence au premier achat), aux fins de mois reconstituées du patrimoine et à la comparaison avec l'indice.
- **Lecture des fichiers** (`frontend-react/src/lib/tableur.ts`, sans bibliothèque) : .xlsx (archive zip décompressée par le navigateur avec `DecompressionStream`, première feuille, chaînes partagées, dates Excel en numéro de série), « Excel » qui est en fait un tableau HTML, ou CSV ; l'ancien format .xls est refusé avec un message. La fenêtre d'import (`components/ImportSerie.tsx`, commune aux titres et aux indices) trouve la ligne d'en-tête (celle avant la première date), devine la colonne de clôture et le format des dates (jour/mois ou mois/jour), modifiables, et montre un aperçu avant l'envoi.
- **Indices de référence** (`routes/indices.py`) : la tâche du soir note aussi la clôture de `MASRN` (MASI Rentabilité Net), `MS20RN` (MASI 20 Rentabilité Net), `MASI`, `MSI20` et `MASIMS` (Mid and Small Cap), lus sur la page « Indices » du site officiel (`cours_bvc.telecharger_indices`), dans `indices_historique(indice, date, valeur, source)`. Les versions « Rentabilité Net » réinvestissent les dividendes après retenue : ce sont elles qui se comparent honnêtement au compte ; les autres sont signalées « hors dividendes ».
- **Comparaison** (carte du tableau de bord Bourse, `GET /api/bourse/indices/comparaison?indice=`) : chaque apport au compte Bourse achète des parts d'indice à sa valeur du jour (la dernière connue un week-end ou un jour férié), chaque retrait en revend (`portefeuille_virtuel()`, fonction pure). Le compte (`patrimoine_total`) est comparé à ce portefeuille virtuel : valeur, écart en DH et rendement annuel (même `taux_rendement_annualise()` que « Performance globale », mêmes flux, seule la valeur finale change). Courbes : le portefeuille virtuel et le compte (titres + espèces, reconstitué comme la courbe du patrimoine) aux dates connues de l'indice, 260 points au plus. Si un apport précède la première valeur connue, la carte propose d'importer l'historique.
- **Import des valeurs passées** (Bourse → Paramètres → Indices de référence, ou depuis la carte ; `POST /api/bourse/indices/{code}/import`) : fichier CSV lu dans le navigateur (colonnes date et valeur devinées et modifiables, dates jour/mois ou mois/jour). Une valeur notée le soir n'est jamais remplacée ; si le fichier s'en écarte de plus de 5 % un même jour, tout est refusé (fichier d'un autre indice, par exemple le MASI au lieu du MASI Rentabilité Net). `DELETE …/import` retire les valeurs importées.
- **Cours en retard** (`cours_en_retard()`, `GET /api/bourse/cours-en-retard`, règle pure `detecter_retards()`), comptés en jours de bourse : un titre automatique sans clôture notée depuis au moins 2 jours de bourse jusqu'à hier (la clôture du jour n'arrive que le soir ; on ne compte qu'à partir du début de l'historique et de l'achat du titre), ou un cours saisi à la main depuis plus de 5 jours de bourse. Signalés dans « À traiter » sur l'accueil, par un badge ambre sous le cours dans Positions et dans le message du lundi matin. C'est le seul signe visible d'une tâche du soir arrêtée ou d'une source qui ne répond plus : ses résultats ne sont que dans les logs.
- **Courbe** (Bourse → Positions, « Valeur du portefeuille ») : `GET /api/bourse/historique` donne, pour chaque jour noté, la valeur de marché des titres détenus ce jour-là et leur coût (PRU × quantité, `valeur_aux_dates()`, fonction pure) ; un titre sans cours noté ce jour-là prend le prix de sa dernière transaction. `?titre=ATW` donne les cours notés d'un seul titre.

### 6.4 Règle de gestion des transferts

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

Application React d'une seule page, dans `frontend-react/src/`. Il n'y a pas de routeur : l'onglet affiché est un état de `App.tsx`.

### 7.1 Bibliothèques

| Rôle | Bibliothèque |
|---|---|
| Interface (formulaires, tableaux, fenêtres, notifications, thème clair/sombre) | Mantine 9 (`@mantine/core`, `dates`, `modals`, `notifications`) |
| Chargement et cache des données | TanStack Query 5 |
| Graphiques | Chart.js 4 via `react-chartjs-2` |
| Icônes | Tabler Icons |
| Dates (sélecteur, locale française) | Day.js |

### 7.2 Organisation du code

```
src/
├── main.tsx              Fournisseurs : Mantine, dates (fr, lundi), TanStack Query, fenêtres, notifications
├── App.tsx               Connexion, barre latérale (ordinateur) / barre d'onglets du bas (mobile), état de navigation
├── theme.ts              Thème Mantine « indigo & ardoise » : marque indigo, rose (dépenses), bleu (revenus), émeraude (épargne)
├── global.css            Couleurs métier, fond dégradé et trame zellige, grille thermique
├── lib/
│   ├── api.ts            api() : fetch, message d'erreur du serveur, 401 → écran de connexion
│   ├── queries.ts        Une fonction use… par route de lecture + useEcriture() pour les écritures
│   ├── types.ts          Types TypeScript des réponses de l'API
│   ├── format.ts         fmt(), lireMontant(), auj(), dates en français
│   └── palette.ts        Palette de 8 couleurs, regrouperAutres(), couleurs des séries
├── components/
│   ├── ui.tsx            EnTetePage, Carte, Kpi, Pastille, Aide, Variation, confirmer(), tableaux triables, états vides
│   ├── Logo.tsx          Logo de l'application
│   ├── champs.tsx        ChampDate (JJ/MM/AAAA ↔ AAAA-MM-JJ), ChampMontant (virgule ou point)
│   ├── Graphique.tsx     Graphique, Donut (légende en %), options communes, couleurs selon le thème
│   ├── Transactions.tsx  FormDepense / FormRevenu (ajout ou modification) et TransactionsDuMois, utilisés par la Saisie
│   └── Protection.tsx    Affiche un message au lieu d'une page blanche en cas d'erreur d'affichage
└── pages/
    ├── Connexion.tsx
    ├── Saisie.tsx
    ├── Parametres.tsx
    ├── accueil/          Accueil.tsx : l'essentiel du jour, page par défaut
    ├── dashboard/        Dashboard.tsx (navigation ‹ ›, choix de vue) + Vues.tsx (Jour/Semaine/Mois/Année/Global)
    ├── bourse/           Bourse.tsx (sous-onglets) + Journaux, Portefeuille, Fiscalite, ParametresBourse
    ├── lectures/         Lectures.tsx (sous-onglets, navigation par année) + Journal, ALire, Bilan, ParametresLectures, communs (couverture, notes)
    └── carnet/           Carnet.tsx (sous-onglets) + Dettes (prêts, emprunts, remboursements), Echeances, Patrimoine
```

### 7.3 Données

- **Lecture** : chaque écran appelle un hook de `queries.ts` (ex. `useResumeMois(mois)`). Les clés commencent par `['budget', …]` ou `['bourse', …]`. Un écran recharge ses données à chaque affichage ; en changeant de période, l'ancien contenu reste visible pendant le chargement.
- **Écriture** : `useEcriture('budget' | 'bourse' | 'lectures')` envoie la requête, affiche la notification de succès puis invalide tout le module, ce qui recharge les écrans concernés (y compris les KPI Bourse du dashboard Budget).
- **Erreurs** : `api()` affiche le message renvoyé par le serveur (erreurs Pydantic comprises). Un 401 ramène à l'écran de connexion, sauf sur `/api/login`, où il signifie « identifiants incorrects ». Les réponses 204 (suppressions Bourse) sont gérées.
- **Résumé Bourse du dashboard Budget** : `useResumeBourseSilencieux()` ne notifie jamais d'erreur, pour qu'un problème Bourse ne casse pas le dashboard Budget.

### 7.4 Comportements à connaître

- **Navigation dans l'URL** (`lib/routes.ts`) : l'onglet, la vue et la période sont dans l'adresse (`#/dashboard/mois/2026-10`, `#/bourse/fiscalite/2026`, `#/lectures/bilan/2025`, `#/saisie/recherche/%23voyage`). Chaque module expose `chemin()` et `appliquer(segments)` ; `App.tsx` lit l'adresse au démarrage, l'écrit à chaque changement (nouvelle entrée d'historique pour un onglet ou une vue, remplacement pour une période) et suit les boutons Retour / Avancer.
- **Suppression dans Saisie** : immédiate, avec « Annuler » dans la notification (la ligne revient sous son identifiant d'origine). Les autres modules gardent une confirmation.

- React échappe automatiquement tout texte affiché : une saisie contenant du HTML s'affiche telle quelle, sans être interprétée.
- Le thème est mémorisé dans `localStorage` sous la clé `theme` (`light` / `dark`), la même que l'ancien frontend. Un script dans `index.html` l'applique avant le premier affichage.
- La navigation (vue du dashboard, période affichée, sous-onglet Bourse) est conservée quand on change d'onglet.
- Les suppressions et désactivations passent par une fenêtre de confirmation.
- La Saisie liste les transactions d'un mois : le mois en cours par défaut, les mois passés via les flèches ‹ › de l'en-tête. Le crayon ouvre la modification d'une ligne dans une fenêtre.
- Les tableaux de la Bourse (transactions, positions, gains) se trient en cliquant sur l'en-tête des colonnes.
- Navigation : barre latérale sur ordinateur (à partir de 768 px), barre d'onglets en bas sur mobile.
- Les notifications s'affichent en bas à droite (au-dessus de la barre d'onglets sur mobile), pour ne jamais masquer la navigation.
- Saisie : un seul formulaire avec un choix Dépense / Revenu ; la saisie en cours est conservée en changeant de type. Les transactions du mois sont groupées par jour, avec les totaux du mois.
- Dashboard : le bouton « Aujourd'hui » ramène à la période en cours.
- Sous 600 px de large, les légendes des donuts passent sous le graphique.

---

## 8. Points restants

**1. Types de colonnes du Budget**
Le module Budget stocke les dates en `TEXT` et les montants en `DOUBLE PRECISION`, alors que le module Bourse utilise `DATE` et `NUMERIC`. Les montants en `float` peuvent accumuler de petites erreurs d'arrondi.
Une migration toucherait toutes les requêtes de `rapports.py` et `transactions.py`, qui filtrent les dates en texte (`LIKE`, `substr`). Elle n'est à envisager qu'après avoir couvert chaque vue du dashboard Budget par des tests.

**2. TPCVM dans les espèces disponibles**
La TPCVM saisie sur une vente est retirée du montant encaissé : l'application suppose que l'intermédiaire la retient à la source. Le prix de vente doit donc être saisi AVANT TPCVM, sinon elle est déduite deux fois et les espèces paraissent trop basses.

**3. Couverture des tests**
Les tests (`backend/tests/`, un fichier par module) couvrent les calculs Bourse et le TRI, les rapports du Budget (projection, charges fixes, comparaisons au mois précédent et à l'an dernier, statistiques annuelles), le Suivi, les objectifs d'épargne, le patrimoine, les rappels, les sauvegardes et le déploiement. La limitation des connexions, les en-têtes de sécurité et les limites des saisies sont testés (`test_securite.py`) ; l'authentification et la vue Globale n'ont pas de tests automatisés. Ils tournent sur la base de `backend/.env` (données préfixées `ZZTEST` ou datées de 1901).

**4. Limitation des connexions par nom d'utilisateur**
Le blocage se fait par nom d'utilisateur (l'adresse IP n'est pas fiable derrière le proxy de l'hébergeur) : quelqu'un qui connaît le nom d'utilisateur peut bloquer la connexion pendant 15 minutes.

**5. Dossier `frontend-react/src/lib/`**
La règle Python `lib/` du `.gitignore` excluait ce dossier, qui n'a jamais été versionné. Il a été reconstruit à partir du build de production, et une exception `!frontend-react/src/lib/` a été ajoutée au `.gitignore`.

---

## 9. Module Lectures

Journal des livres terminés et bilan annuel. Un livre compte pour l'année et le mois de sa **date de fin**. Une relecture se saisit comme un nouveau livre et compte donc deux fois.

### Calculs du bilan (`GET /api/lectures/bilan?annee=`)

| Indicateur | Formule |
|---|---|
| Livres lus | nombre de livres dont la date de fin est dans l'année |
| Pages lues, pages moyennes | somme et moyenne des pages, sur les livres où elles sont renseignées |
| Avis moyen | moyenne des notes, sur les livres notés |
| Durée moyenne | (date de fin − date de début + 1 jour), sur les livres avec une date de début |
| Attendu à date | objectif annuel × part de l'année écoulée (année passée : objectif entier ; année future : 0) |
| Avance / retard | livres lus − attendu à date, arrondi |
| Mois réussis | mois écoulés de l'année où les livres terminés ≥ objectif mensuel (0 si l'objectif mensuel vaut 0) |
| Records | mieux noté, plus long et plus court (à égalité, le plus récent) ; 5 auteurs les plus lus |
| Historique | nombre de livres et de pages par année, sur tout l'historique |

`calculer_bilan(annee, aujourdhui)` reçoit la date du jour en paramètre, pour que les tests fixent la date de référence.

### Frontend

Onglet **Lectures**, avec trois sous-onglets :
- **Journal** : formulaire (titre, auteur avec autocomplétion, genre, dates de début et de fin, pages, avis en étoiles, note personnelle) et liste de l'année groupée par mois, avec modification (fenêtre) et suppression ;
- **Bilan annuel** : KPI des objectifs et de lecture, livres par mois (barres vertes quand l'objectif mensuel est atteint), progression cumulée comparée au rythme de l'objectif, genres, records, tableau triable des livres, historique par année ;
- **Paramètres** : objectifs annuel et mensuel, genres.

### Suivi de la lecture en cours

- **Page du jour** : `PUT /a_lire/{id}/progression` garde une page par jour et par livre (la dernière saisie du jour remplace la précédente). Noter une page fait passer un livre « à lire » en cours.
- **Rythme** (`rythme()`) : pages lues ÷ jours écoulés, du début de la lecture (page 0 à `date_debut`) à la dernière page notée. La **fin estimée** prolonge ce rythme à partir d'aujourd'hui sur les pages restantes ; elle est vide sans nombre de pages.
- **Série** (`calculer_serie()`) : jours de lecture consécutifs. Un jour compte dès qu'une page en avance sur la précédente est notée, ou qu'un livre est terminé ce jour-là. La série tient encore si le dernier jour lu est hier.
- **Note du jour** (`note_du_jour()`) : une note ou citation tirée de tous les livres, la même toute la journée ; `decalage` en fait défiler d'autres.
- **Export Markdown** : une fiche par livre (en-tête, avis, citations puis notes dans l'ordre des pages). Le nom du fichier vient du titre, sans accents ni ponctuation ; un titre non latin est conservé.
- **Livres prêtés** : onglet « Prêtés », avec la durée du prêt (jusqu'à aujourd'hui, ou jusqu'au retour).

---

## 10. Suivi, rappels et résumés

> L'onglet s'appelle **Suivi** dans l'interface (`#/suivi`). Dans le code, il garde son premier nom : `routes/carnet.py`, `/api/carnet/…`, `pages/carnet/`. « Carnet » est aujourd'hui le nom de l'application (auparavant « Mon Budget » ; les sauvegardes faites sous cet ancien nom restent lisibles).

### Dettes et prêts

Un **prêt** (`sens = pret`) est de l'argent qu'on me doit ; un **emprunt** (`sens = emprunt`) est de l'argent que je dois. Le reste dû vaut `montant − somme des remboursements` ; une dette est soldée quand il atteint 0.

- Ce sont des **transferts**, comme les apports Bourse : ils ne se saisissent pas dans le Budget. Un prêt saisi en dépense puis son remboursement saisi en revenu fausseraient les dépenses, le taux d'épargne et les comparaisons du mois.
- Un remboursement ne peut ni dépasser le reste dû, ni précéder la date du prêt. Le montant d'une dette ne peut pas descendre sous ce qui est déjà remboursé.
- Liste : les dettes en cours d'abord (échéance la plus proche en tête, celles sans échéance ensuite), puis les soldées.

### Échéances

Tout ce qui a une date limite : CIN, passeport, assurance, visite technique, vignette, garanties, abonnements.

- `jours_restants` = date limite − aujourd'hui (fuseau `FUSEAU`), négatif si elle est dépassée. `a_rappeler` est vrai dès que `jours_restants ≤ rappel_jours` : l'échéance passe alors dans « À traiter ».
- Une échéance **récurrente** (`recurrence_mois`) se reporte avec ✓ : sa date avance d'une période à partir de la date prévue (pas d'aujourd'hui) ; un 31 devient le dernier jour d'un mois plus court. Une échéance ponctuelle se modifie (nouvelle date d'expiration) ou se supprime.

**Provisions** : une échéance qui coûte (assurance, Aïd al-Adha, rentrée scolaire, vacances) peut avoir un `montant`. Avec « Mettre de côté chaque mois d'ici là » (`provisionner`), un **objectif d'épargne** du même montant et pour la même date est créé (`objectif_id`, note « Provision pour l'échéance … ») : son `par_mois` dit ce qu'il faut mettre de côté chaque mois, pour que la dépense ne tombe pas d'un coup sur un seul mois.
- Modifier l'échéance met l'objectif à jour (nom, montant, date). Décocher la case, ou supprimer l'échéance, supprime l'objectif s'il est vide ; s'il contient déjà de l'argent, il reste dans Objectifs (à reprendre ou archiver).
- Reporter une échéance récurrente (✓) archive l'objectif avec ce qui a été mis de côté (l'argent a servi) et en ouvre un nouveau pour la période suivante ; le tag éventuel suit, compté à partir du lendemain. Un objectif encore vide est seulement décalé.
- Le total à mettre de côté ce mois-ci (somme des `par_mois` des provisions en cours) s'affiche sur l'écran Échéances et dans la carte Épargne du dashboard du mois en cours. Un objectif de provision porte le badge « échéance » dans Objectifs.

### Rappels du jour

`rappels_du_jour(auj)` renvoie les lignes à envoyer :

- une échéance est rappelée au début de sa fenêtre (`rappel_jours` avant), puis à J−7 et J−1 s'ils tombent dans la fenêtre, et le jour même. Exemple avec « 1 mois avant » : J−30, J−7, J−1, J ;
- une dette non soldée qui a une échéance est rappelée à J−3 et le jour même ;
- une échéance dépassée n'est plus rappelée chaque jour : elle figure dans le résumé du lundi tant qu'elle n'est pas traitée ;
- le **lundi**, s'ajoutent les dépenses inhabituelles (`alertes.calculer_alertes`, voir §11) et l'invitation à pointer le solde s'il ne l'a jamais été ou pas depuis 30 jours (`rappels_du_lundi`).

### Message du matin

`message_du_matin(auj)` réunit ces rappels et la **note ou citation du jour** des Lectures (`lectures.note_du_jour`, la même que sur l'accueil ce jour-là) en un seul message, en texte, Telegram et e-mail (`rendre_matin`). Sans rappel, la note part seule ; sans note ni rappel, rien ne part. ### Canaux de chaque envoi

La note du jour, le résumé de la semaine, le bilan du mois et celui de l'année se choisissent **canal par canal** dans Paramètres → Rappels et résumés : `PUT /api/rappels/envois` avec `{envoi: note|semaine|mois|annee, canal: telegram|email, actif}`, gardé dans `params` sous `envoi_<envoi>_<canal>` (tout est activé par défaut ; `GET /api/rappels/etat` renvoie les choix dans `envois`). Un canal choisi mais non configuré sur le serveur ne reçoit rien.

Les rappels et la sauvegarde mensuelle partent toujours sur tous les canaux : avec la note sur Telegram seulement, l'e-mail ne reçoit que les rappels, et rien les jours sans rappel. Le résumé de la semaine coupé partout note quand même la valeur du portefeuille chaque lundi, pour que la comparaison reste sur une semaine quand il est réactivé. Le bouton « Envoyer maintenant » de l'aperçu envoie sur tous les canaux configurés, quels que soient ces choix.

### Résumé hebdomadaire

`resume_hebdo(auj)` couvre la **dernière semaine terminée** (du lundi au dimanche) :

| Section | Contenu |
|---|---|
| En-tête | la semaine couverte et une phrase de bilan (sous le budget avec la marge restante, ou dépassé de combien) |
| Budget | dépenses et variation sur la semaine d'avant, revenus et épargne, jauge du budget variable, dépenses jour par jour, premières catégories, plus grosse dépense, jour le plus dépensier, jours sans dépense, mois en cours (dépensé, budget, projection à partir du 5) |
| Bourse | valeur du compte (titres + espèces), écart depuis le résumé précédent (apports et retraits compris), performance globale |
| Lectures | livres terminés dans la semaine, livres en cours, avancement de l'objectif annuel |
| Suivi | total qu'on me doit et que je dois, dettes dont l'échéance est dépassée, échéances à traiter |

Une section vide est omise ; une section qui lève une erreur est ignorée et journalisée, les autres partent quand même.

`routes/rappels.py` réunit les données, `resume_rendu.py` les met en forme en trois versions : un **e-mail HTML** (cartes, barres jour par jour et par catégorie, jauges ; styles en ligne uniquement, pour Gmail), un **message Telegram** (HTML de Telegram : phrase de bilan en citation, chiffres alignés dans des blocs à chasse fixe de 24 caractères au plus, barres jour par jour) et un **texte brut**, joint à l'e-mail comme repli et envoyé sur Telegram si la mise en forme est refusée ou dépasse 4 000 caractères. Les textes saisis (catégories, descriptions, titres) sont échappés. L'aperçu des Paramètres affiche l'e-mail tel qu'il part.

### Bilan du mois

`resume_mensuel(auj)` couvre le **dernier mois terminé** ; il part le 1er du mois suivant.

| Section | Contenu |
|---|---|
| En-tête | le mois et une phrase de bilan : objectif d'épargne atteint, manqué de combien, ou mois dans le rouge |
| Bilan | dépenses et variation sur le mois d'avant, revenus, épargne et taux d'épargne, jauges du budget du mois et de l'objectif d'épargne |
| Au fil du mois | dépenses par tranche de 7 jours (1–7, 8–14, …) |
| Catégories | réel comparé au budget, catégories dépassées signalées |
| Plus grosses dépenses | les cinq premières, avec leur catégorie et leur date |
| Derniers mois | dépenses des six derniers mois (e-mail seulement) |
| Bourse | valeur du compte, résultat, dividendes, apports et retraits du mois, performance globale |
| Lectures | livres terminés dans le mois, livres en cours, objectif annuel |
| Suivi | dettes en cours, échéances à traiter ou qui tombent dans les 31 jours qui viennent |

Mêmes trois versions et mêmes règles que le résumé de la semaine.

### Bilan de l'année

`resume_annuel(auj)` couvre la **dernière année terminée** ; il part le 1er janvier. Contenu : épargne de l'année et taux d'épargne, dépenses comparées à l'année d'avant, dépense mensuelle moyenne, mois où l'objectif d'épargne est atteint, meilleur mois et mois le plus difficile, dépenses mois par mois, budget annuel par catégorie, plus grosses dépenses, résultat et dividendes Bourse de l'année, livres et pages lus, patrimoine net du jour.

### Tâche planifiée

`GET /api/cron/quotidien` envoie le message du matin (rappels et note du jour), **le lundi** le résumé de la semaine, **le 1er du mois** le bilan du mois avec une copie de sauvegarde en pièce jointe, et **le 1er janvier** le bilan de l'année (plusieurs le même jour si les dates coïncident). Elle n'utilise pas de session : elle exige l'en-tête `Authorization: Bearer <CRON_SECRET>`.

- **Vercel** : `vercel.json` déclare la tâche (`0 7 * * *`, soit entre 8 h et 9 h au Maroc ; l'offre gratuite autorise une exécution par jour, à une minute non garantie dans l'heure). Vercel envoie `CRON_SECRET` tout seul dès que la variable existe.
- Au plus un envoi par jour : le jour traité est noté dans `params`, un second appel répond `deja_fait` (`?force=true` passe outre). Si l'envoi échoue, le jour n'est pas noté et un nouvel appel réessaie.
- Avant les envois, et même si aucun canal n'est configuré : les cours de la Bourse sont actualisés, puis le patrimoine du jour est noté dans `patrimoine_historique` (courbe du §11). Un échec de l'un ou de l'autre n'empêche pas les envois.
- Chaque appel est noté dans `cron_journal` (Paramètres affiche les derniers). Si le dernier appel réussi date de plus de 36 heures, ou si le dernier a échoué, l'accueil le signale dans « À traiter » avec un lien vers les Paramètres. Rien n'est signalé tant que `CRON_SECRET` n'est pas configuré ou que la tâche n'a encore jamais tourné.

### Configurer l'envoi

Un canal est actif dès que ses variables sont renseignées ; les deux peuvent l'être en même temps. Paramètres → « Rappels et résumés » indique ce qui est configuré ; « Aperçu et envoi » montre le résumé de la semaine ou le bilan du mois et l'envoie tout de suite.

**Telegram**
1. Dans Telegram, écrire à **@BotFather** : `/newbot`, choisir un nom. Il renvoie le jeton → `TELEGRAM_BOT_TOKEN`.
2. Ouvrir la conversation avec le nouveau bot et lui envoyer un message (un bot ne peut pas écrire en premier).
3. Ouvrir `https://api.telegram.org/bot<JETON>/getUpdates` dans le navigateur : la valeur `"chat":{"id": …}` → `TELEGRAM_CHAT_ID`.

**Saisie par Telegram** (avec le même bot) : une fois l'application en ligne, Paramètres → « Saisie par Telegram » → **Activer la saisie**. Le bouton déclare le webhook auprès de Telegram (`setWebhook`, adresse `https://<site>/api/telegram/webhook`, et les commandes /aide, /reste, /solde). En local, Telegram ne peut pas joindre l'application : le bouton refuse. Le secret que Telegram renvoie à chaque appel (`TELEGRAM_WEBHOOK_SECRET`) est tiré du jeton du bot par défaut : rien de plus à configurer. Seuls les messages de la conversation `TELEGRAM_CHAT_ID` sont acceptés. Ce qu'on peut écrire au bot (`routes/telegram.py`) :

| Message | Effet |
|---|---|
| `45 café`, `café 45`, `45 café hier`, `avant-hier 30 taxi` | dépense ; montant au début ou à la fin, `hier` / `avant-hier` pour la date |
| `1200 courses #maison` | avec un ou plusieurs tags |
| `+8000 salaire` | revenu ; la source est devinée par son nom, sinon le revenu reste sans source |
| `?` ou `/reste` | reste à dépenser aujourd'hui et ce mois-ci |
| `solde` · `solde 12500` | liquidités calculées et dernier pointage · note un pointage du solde réel (voir §11) |
| `aide`, `/start` | mode d'emploi |

La catégorie d'une dépense est devinée : celle le plus souvent utilisée pour la même description, sinon celle dont le nom contient un mot du message (« café » → « Restaurants & Cafés », sans tenir compte des accents), sinon celle des descriptions passées qui contiennent un de ses mots. Sinon, le bot demande la catégorie par boutons (la dépense attend dans `telegram_messages.attente`). La réponse donne le reste du budget de la catégorie ce mois-ci, avec les boutons « Annuler » (supprime l'opération) et « Catégorie » (la change). Un message reçu deux fois n'est traité qu'une fois ; la route répond toujours 200, sinon Telegram renverrait le même message.

**E-mail (exemple Gmail)**
1. Activer la validation en deux étapes du compte Google, puis créer un **mot de passe d'application** (myaccount.google.com/apppasswords).
2. `SMTP_HOTE=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_UTILISATEUR=` l'adresse Gmail, `SMTP_MOT_DE_PASSE=` le mot de passe d'application. `EMAIL_DESTINATAIRE` seulement pour recevoir sur une autre adresse.

**Envoi automatique** : `CRON_SECRET=` une longue chaîne aléatoire (par exemple `python -c "import secrets; print(secrets.token_urlsafe(32))"`).

Sur Vercel, ces variables se règlent dans **Settings → Environment Variables**, puis il faut redéployer.

### Frontend

Onglet **Suivi**, avec quatre sous-onglets :
- **Dettes et prêts** : totaux (on me doit, je dois, solde net), formulaire, dettes en cours avec leur avancement, fenêtre des remboursements (le champ montant vide solde la dette), dettes soldées ;
- **Échéances** : formulaire (catégorie, date limite, délai de rappel, récurrence, montant, provision), « À traiter » et « Plus tard », et le total à mettre de côté ce mois-ci pour les provisions. Le nombre d'échéances à traiter s'affiche sur l'onglet ;
- **Objectifs** : objectifs d'épargne par projet (voir §11) ;
- **Patrimoine** : voir §11.

---

## 11. Patrimoine, objectifs, réserve de sécurité et zakat

Onglet **Suivi → Patrimoine** (`routes/patrimoine.py`). La carte « Patrimoine net » de la vue Global du dashboard affiche le même total.

### Patrimoine net

```
liquidités = solde de départ + épargne cumulée du Budget
             − apports nets au compte Bourse − argent versé dans les autres actifs
             − argent prêté + argent emprunté
patrimoine = liquidités + compte Bourse + autres actifs + ce qu'on me doit − ce que je dois
```

- Le **solde de départ** est l'argent détenu avant la première saisie ; sans lui, les liquidités ne comptent que l'épargne faite depuis.
- Un **actif** (or, compte épargne, placement, immobilier) a une valeur saisie à la main et une date de relevé. `verse` est l'argent sorti de l'épargne pour lui **sans** être saisi en dépense : il est retiré des liquidités, donc seul le gain de valeur augmente le patrimoine. Un actif saisi en dépense, ou détenu avant l'application, garde `verse = 0` et s'ajoute en entier.
- Un prêt ou un emprunt déplace de l'argent entre les liquidités et les créances ou dettes : le total ne change pas.

### Pointage du solde

Les liquidités sont **calculées** (formule ci-dessus), jamais saisies : une dépense oubliée les fausse sans que rien ne le montre, et avec elles le patrimoine, la réserve, la liberté financière et la zakat. La carte « Pointer le solde » (Patrimoine) compare le solde réel, tapé compte par compte (Banque, Espèces, autres), aux **liquidités du jour** (`liquidites_du_jour` : celles du patrimoine sans les opérations du Budget datées de demain ou après).

- L'écart (réel − calculé) s'affiche en direct ; négatif, il manque de l'argent (une dépense oubliée, un retrait, des frais bancaires). Les jours sans aucune dépense depuis le dernier pointage (31 jours au plus affichés) aident à retrouver l'oubli.
- « Enregistrer l'écart » crée une dépense (catégorie à choisir, « Imprévus » proposée) ou un revenu du jour, description « Écart de pointage du solde », tag `pointage` : la suite repart juste. « Noter sans l'enregistrer » garde seulement le pointage.
- Chaque pointage est gardé dans `rapprochements`. `GET /api/patrimoine` renvoie le dernier dans `pointage` (`{date, jours, ecart, regle, a_refaire}`) ; au-delà de 30 jours, ou s'il n'y en a jamais eu, l'accueil (« À traiter ») et le message du lundi invitent à pointer. Sur Telegram, `solde 12500` note un pointage (sans enregistrer l'écart).

### Dépenses inhabituelles

`routes/alertes.py`, affichées dans « À traiter » sur l'accueil et le lundi matin (§10) :

| Alerte | Règle |
|---|---|
| Catégorie | ce mois-ci, au moins 30 % **et** 300 DH au-dessus de sa moyenne sur les 6 derniers mois terminés (moyenne faite sur les mois où l'application a des dépenses, au moins 3) |
| Hausse d'un montant récurrent | même catégorie et même description (casse et espaces près), vue dans au moins 3 mois sur 200 jours, à un montant fixe jusque-là (écart ≤ 2 %), dont le dernier montant, récent (45 jours), est plus élevé d'au moins 5 % et 5 DH : un abonnement qui augmente |
| Doublon | sur 14 jours, au moins deux dépenses le même jour avec la même catégorie, la même description et le même montant |

Chaque alerte a une clé (`categorie:2026-11:Courses`, `hausse:…:75.00`, `doublon:<id>:<n>`) : la croix « Ignorer » la range dans `alertes_ignorees`, elle ne revient plus (une nouvelle hausse ou un autre mois donnent une nouvelle clé). Les clés de plus de 400 jours sont effacées.

### Évolution du patrimoine

Le patrimoine n'est connu qu'au jour le jour : les cours passés ne sont pas conservés, la valeur passée des actifs non plus. `noter_patrimoine()` écrit donc chaque jour une ligne dans `patrimoine_historique` (une par date, remplacée par le dernier calcul de la journée) : à chaque matin par la tâche planifiée, et à chaque lecture de `/api/patrimoine` (écran Patrimoine, accueil, vue Globale). La carte « Évolution » trace cette courbe sur 3 mois, 1 an ou tout l'historique, avec la part Bourse et l'écart depuis le premier point affiché. L'axe horizontal est en temps réel (un mois de points mensuels prend autant de place qu'un mois de points quotidiens).

**Mois passés reconstitués.** « Reconstituer les mois passés » (`reconstituer_historique()`) ajoute un point par fin de mois, de la plus ancienne opération jusqu'au premier vrai point noté, marqué `estime` et tracé en pointillé. Chaque point rejoue les opérations datées jusqu'à ce jour avec les formules de `calculer_patrimoine` (`patrimoine_aux_dates()`, fonction pure) :

- exacts : épargne du Budget, apports et retraits Bourse, espèces du compte Bourse (achats, ventes moins TPCVM, dividendes, frais), quantités détenues, prêts et emprunts avec leurs remboursements ;
- estimés : la valeur des titres, au dernier cours connu ce jour-là. Par ordre de priorité à date égale : cours saisi à la main pour cette date (`bourse_cours_historique`, bouton « Cours de fin de mois »), cours actuel (`bourse_prix`, à sa date de relevé), cours noté ce jour-là (`bourse_prix_historique`, §6.3), prix de la dernière transaction ;
- approximatifs : un autre actif compte à sa valeur actuelle à partir de la plus ancienne de sa date de création et de sa date de relevé.

Un vrai point du jour remplace toujours un point estimé, jamais l'inverse. Une fois des points estimés présents, la tâche du matin les recalcule chaque jour : corriger une ancienne saisie met la courbe à jour.

### Objectifs d'épargne par projet

Onglet **Suivi → Objectifs** (`routes/objectifs.py`). Un objectif (voyage, fonds d'urgence, voiture) a un montant visé et, s'il le faut, une date limite. On y met de l'argent de côté par **versements** ; un versement négatif reprend de l'argent (par exemple quand on dépense pour le projet).

- Mettre de côté **ne déplace pas d'argent** : il reste dans les liquidités, il est seulement réservé. Ce n'est ni une dépense du Budget ni un transfert, et le patrimoine ne change pas. La carte « Liquidités libres » affiche les liquidités moins tout ce qui est réservé aux objectifs en cours.
- `verse` = Σ versements ; `reste` = max(cible − verse, 0) ; `progression` = verse ÷ cible (peut dépasser 100 %).
- **Rythme à tenir** : `par_mois` = reste ÷ `mois_restants`, où `mois_restants` compte le mois en cours et celui de la date limite (le 11 novembre pour le 31 décembre : 2). Rien sans date limite, une fois l'objectif atteint ou archivé.
- `en_retard` : date limite dépassée sans avoir atteint la cible ; l'objectif apparaît alors dans « À traiter » sur l'accueil.
- On ne peut pas reprendre plus que ce qui est de côté, ni supprimer un versement si le total devenait négatif.
- **Suivi par un tag** (facultatif, champ « Suivre les dépenses du tag ») : les dépenses du Budget portant le tag de l'objectif (ex : `#turquie-2027`), datées de `tag_depuis` ou après, sont prises sur l'argent mis de côté, sans « Reprendre » à la main. Les revenus portant le même tag (un remboursement d'hôtel) les diminuent.
  - `depense` = Σ dépenses taggées − Σ revenus taggés (0 au plus bas) ; `reserve` = max(verse − depense, 0) ; `depassement` = max(depense − verse, 0). Sans tag, `depense` = 0 et `reserve` = `verse`.
  - L'avancement de l'épargne (`verse` sur `cible`) ne change pas : l'argent a bien été mis de côté. Une seconde barre montre le dépensé sur le mis de côté.
  - « Liquidités libres » retire `reserve` (et non plus `verse`) : une dépense du projet a déjà fait baisser les liquidités, la retirer encore comme réservée la compterait deux fois.
  - `tag_depuis` vaut par défaut le jour où le tag est ajouté : les dépenses d'un ancien projet du même tag ne comptent pas. Le formulaire prévient si le tag sert déjà avant cette date.
  - Un dépassement (dépensé au-delà de l'enveloppe) apparaît en rouge sur l'objectif et dans « À traiter » sur l'accueil, tant que l'objectif n'est pas archivé.
  - « Reprendre » est limité à ce qui reste dans l'enveloppe. La fenêtre « Versements » liste les 50 dernières opérations du tag (`operations`).
- **Archiver** sort un objectif (atteint ou abandonné) de la liste en cours sans perdre ses versements. Supprimer efface ses versements, pas l'argent, qui n'a jamais quitté les liquidités.
- À ne pas confondre avec l'**objectif d'épargne mensuel** du Budget (`params.objectif_epargne`), qui est un montant à épargner chaque mois.

### Réserve de sécurité

Mois de dépenses couverts = argent disponible ÷ dépense mensuelle moyenne. L'argent disponible est la somme des liquidités (si positives) et des actifs de type « Compte épargne ». La moyenne porte sur les 6 derniers mois **terminés** ayant des dépenses. Repères affichés : moins de 3 mois fragile, 3 à 6 correct, au-delà confortable.

### Zakat (estimation)

- **Assiette** = liquidités + compte Bourse à sa valeur de marché + actifs cochés « Compte pour la zakat » + ce qu'on me doit − ce que je dois (les parts négatives comptent pour 0).
- **Nisab** = 85 g d'or × le prix du gramme saisi. Assiette ≥ nisab : zakat = 2,5 % de l'assiette ; sinon rien.
- **Échéance** = début de l'année en cours + 354 jours (année lunaire). « Zakat payée » redémarre l'année à la date du jour.
- C'est une aide au calcul, pas un avis religieux : le traitement des actions, des dettes et le choix du nisab (or ou argent) varient selon les avis.

### Bourse : journal des décisions et dividendes attendus

- Chaque transaction peut porter une **note** (pourquoi j'achète ou je vends). L'onglet Transactions les rassemble dans « Journal des décisions », avec l'évolution du cours depuis pour les titres encore détenus.
- **Dividendes attendus** (`calculer_calendrier_dividendes()`) : chaque dividende reçu depuis un an sur un titre encore détenu est supposé revenir un an plus tard, au même montant **par action** (montant reçu ÷ quantité détenue ce jour-là), appliqué à la quantité détenue aujourd'hui. Le rendement des positions utilise le même calcul (`dividendes_par_action()`).

---

## 12. Accueil, sauvegarde, sessions et installation

### Accueil

Page par défaut (`#/accueil`, aussi ouverte par un clic sur le logo). Elle ne demande aucune route de plus : elle réunit des données déjà servies aux autres écrans.

| Bloc | Source |
|---|---|
| Reste à dépenser aujourd'hui | budget journalier − dépenses variables du jour (`/api/resume_jour`) |
| Reste ce mois-ci, carte du mois | `/api/resume` : dépensé, budget, épargne, projection |
| Portefeuille, carte Bourse | `/api/bourse/dashboard` (masqués sans compte Bourse), avec le rendement annuel une fois 3 mois d'historique |
| Patrimoine net | `/api/patrimoine` : total et réserve de sécurité |
| Note du jour | `/api/lectures/note_du_jour` |
| Lecture en cours | `/api/lectures/a_lire` et `/serie` |
| À traiter | échéances dans leur fenêtre de rappel, dettes dont l'échéance est dépassée, objectifs d'épargne dont la date limite est passée ou l'enveloppe dépassée, tâche du matin arrêtée ou en échec (`/api/rappels/etat`), solde à pointer (`pointage` de `/api/patrimoine`), dépenses inhabituelles (`/api/alertes`, avec une croix pour les ignorer) |

Sur mobile, la barre du bas garde six onglets (Accueil, Saisie, Dashboard, Bourse, Lectures, Suivi) ; les Paramètres passent dans l'en-tête.

### Sauvegarde complète

- **Télécharger** : Paramètres → Import / export → « Télécharger toutes mes données » (`GET /api/sauvegarde`). Un fichier JSON lisible : `{application, format, cree_le, tables: {nom: [lignes]}}`.
- **Contenu** : toutes les tables de la base, découvertes à l'export (une table ajoutée plus tard est sauvegardée sans rien changer). Les comptes et les sessions sont exclus : aucun mot de passe, même haché, ne sort.
- **Copie automatique** : le 1er de chaque mois, la tâche planifiée envoie le fichier compressé (`.json.gz`) en pièce jointe par Telegram et par e-mail, selon les canaux configurés. Un échec est journalisé sans bloquer les résumés.
- **Restaurer** :

  ```bash
  cd backend
  python scripts/restaurer_sauvegarde.py chemin/vers/carnet-2026-10-01.json.gz
  ```

  Le script affiche la base visée et demande confirmation (`--oui` pour s'en passer). Le contenu des tables sauvegardées est **remplacé**, dans une seule transaction : en cas d'erreur, rien ne change. Les tables parentes sont insérées avant celles qui les référencent, et les identifiants automatiques repartent après le plus grand restauré. Une table ou une colonne absente de la base est ignorée ; une colonne absente du fichier prend sa valeur par défaut. Les comptes ne sont pas touchés : sur une base neuve, le compte est créé par `ADMIN_UTILISATEUR` / `ADMIN_MOT_DE_PASSE`.

### Sessions

| | Durée sans utilisation | Cookie |
|---|---|---|
| « Rester connecté » coché (par défaut) | 30 jours | durable (400 jours, le maximum des navigateurs) |
| Décoché | 1 jour | de session : effacé à la fermeture du navigateur |

La session est **glissante** : `utilisateur_courant` la fait repartir pour sa durée entière dès qu'il en reste moins de la moitié (une écriture tous les 15 jours au plus pour une session longue). C'est la date d'expiration en base qui fait foi, pas la durée de vie du cookie. Changer le mot de passe ferme toutes les sessions, sur tous les appareils.

### Installer l'application

`public/manifest.json` (nom, couleurs, icônes 192 et 512, icône « maskable », raccourcis) et les balises de `index.html` rendent l'application installable :

- **Android (Chrome)** : menu ⋮ → « Installer l'application » ou « Ajouter à l'écran d'accueil » ;
- **iPhone (Safari)** : bouton Partager → « Sur l'écran d'accueil ».

Elle s'ouvre alors en plein écran, sans barre d'adresse. Il n'y a pas de service worker : l'application ne fonctionne pas hors connexion, et chaque ouverture charge la dernière version.


## 13. Opérations récurrentes et prévisions

### Opérations récurrentes

`routes/recurrences.py`, bouton **Saisie → Récurrences**. Une récurrence (loyer, abonnement, facture, salaire) donne une dépense ou un revenu par mois, au jour choisi ; un jour 29, 30 ou 31 tombe au dernier jour des mois plus courts. `debut` est le premier mois concerné : par défaut le mois en cours si le jour n'est pas encore passé, sinon le suivant (un loyer du 1er créé le 12 a sans doute déjà été saisi à la main).

- **Ajout manuel** : la carte « Récurrences à ajouter » de Saisie liste tout ce qui n'est pas encore ajouté jusqu'au mois en cours (`GET /api/recurrences/a-generer`), cochée si sa date est arrivée. Le montant se corrige pour ce mois seulement (facture qui varie) ; ⏭ passe le mois sans rien ajouter (`POST /api/recurrences/{id}/passer`). Une récurrence manuelle qui tombe aujourd'hui est rappelée dans le message du matin.
- **Ajout automatique** (`auto`) : la tâche du matin ajoute l'opération le jour venu (`generer_automatiques()`), avant de noter le patrimoine du jour, et le message du matin le signale (« Ajouté au Budget : … »). Une récurrence dont la catégorie a été désactivée est laissée de côté.
- **Une seule fois par mois** : `dernier_mois` garde le dernier mois généré ou passé. `POST /api/recurrences/generer` n'ajoute un mois que s'il est le prochain attendu, sous verrou de ligne (`SELECT … FOR UPDATE`) : un second passage, ou deux passages simultanés, ne font rien. Des mois manqués (tâche arrêtée) sont rattrapés dans l'ordre.
- Une opération générée est une opération ordinaire : elle se modifie ou se supprime dans Saisie. Modifier ou supprimer une récurrence ne touche pas les opérations déjà ajoutées ; la mettre en pause (`actif`) arrête les suivantes.
- **Suggestions** (`GET /api/recurrences/suggestions`, fonction pure `suggerer()`) : une opération présente une seule fois dans chacun des 3 derniers mois terminés, avec la même catégorie (ou source) et la même description (casse et espaces ignorés), à des montants à ±10 % de leur moyenne, et pas déjà couverte par une récurrence.

### Prévisions de trésorerie

`routes/previsions.py`, carte **Prévisions** de Suivi → Patrimoine (3 mois, 6 mois ou 1 an). Les liquidités fin de mois, du mois en cours (son reste) aux suivants :

    solde(M) = solde(M−1) + revenus attendus − dépenses attendues − échéances − emprunts à rembourser

- **Départ** : `liquidites_du_jour()` (sans les opérations datées d'après aujourd'hui, ajoutées à leur mois).
- **Revenus** par source : ses récurrences pas encore générées ni passées ce mois-là ; sans récurrence, la **médiane** de ses montants mensuels sur les 6 derniers mois terminés (une prime isolée ne gonfle pas chaque mois), moins ce qui est déjà saisi ce mois-là.
- **Dépenses** par catégorie : le plus grand de ses récurrences pas encore générées et de ce qui manque pour atteindre sa moyenne sur 6 mois (ou son budget, pour une catégorie « Fixe » dont le budget est plus haut). Le plus grand et non la somme : un loyer récurrent, aussi présent dans la moyenne, n'est compté qu'une fois. Une catégorie désactivée sans récurrence n'attend plus rien.
- **Échéances** avec un montant, au mois où elles tombent (reports des échéances récurrentes compris). **Emprunts** : le reste dû au mois de l'échéance, ou dans le mois en cours s'il est en retard. L'argent qu'on me doit n'est pas compté.
- **Objectifs** : ils ne sortent pas d'argent. Leur réserve grandit de `par_mois` chaque mois jusqu'à la date limite ; une échéance provisionnée par un objectif vide sa réserve le mois où elle est payée. « Libres » = solde − réservé (pointillé bleu).
- **Fourchette** : écart-type des dépenses mensuelles des 6 derniers mois × √(numéro du mois).
- **Hors calcul** : opérations de pointage (tag `pointage`), apports en Bourse et argent versé dans les autres actifs (des choix, pas des dépenses prévues).
- **Alertes** (carte et « À traiter » de l'accueil) : un mois finit sous le **plancher** (`PUT /api/previsions/reglages`, 0 = sous zéro) ; les objectifs réservent plus que les liquidités ; leur rythme mensuel dépasse l'épargne prévue d'un mois entier.

Le calcul (`projeter()`) ne lit pas la base : `tests/test_previsions.py` le vérifie sans base de données.
