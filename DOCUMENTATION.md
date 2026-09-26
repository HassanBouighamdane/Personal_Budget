# Mon Budget — Documentation technique

Application web personnelle pour suivre son budget (dépenses, revenus, épargne) et un portefeuille boursier à la Bourse de Casablanca. Toutes les valeurs sont en dirhams (DH).

- **Backend** : Python, FastAPI, PostgreSQL (driver `psycopg` v3)
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
8. [Problèmes détectés et recommandations](#8-problèmes-détectés-et-recommandations)

---

## 1. Architecture générale

```
Personal_Budget/
├── backend/
│   ├── app.py              Point d'entrée : crée l'app FastAPI, branche les routes, sert le frontend
│   ├── config.py           Variables d'environnement (.env) et valeurs par défaut
│   ├── database.py         Connexion PostgreSQL + création/migration du schéma
│   ├── securite.py         Hachage des mots de passe + sessions par cookie
│   ├── schemas.py          Modèles Pydantic (validation des entrées et des sorties)
│   ├── requirements.txt
│   ├── scripts/
│   │   └── supprimer_bourse.py  Supprime toutes les tables du module Bourse (script manuel, pas un test)
│   ├── tests/
│   │   ├── test_bourse.py     PRU chronologique, frais, arrondi de performance, garde-fou de vente
│   │   └── test_budget.py     Cascade de renommage (catégories/sources/paiements), erreurs 404
│   └── routes/
│       ├── auth.py            /api/login, /logout, /me, /mot_de_passe
│       ├── configuration.py   catégories, sources de revenus, types de paiement, objectif
│       ├── transactions.py    dépenses et revenus
│       ├── rapports.py        résumés jour / semaine / mois / année
│       └── bourse.py          module Bourse (transactions, positions, gains, dividendes, frais)
├── frontend/
│   ├── index.html          Page unique (SPA) : tous les onglets y sont, masqués/affichés en JS
│   ├── css/style.css       Thèmes sombre/clair via variables CSS, responsive
│   ├── js/app.js           Logique principale : auth, saisie, dashboards, paramètres
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
Réponse JSON  → le JS génère le HTML (innerHTML) et les graphiques Chart.js
```

### Choix de conception

- **Pas d'ORM** : le code écrit ses requêtes SQL à la main, toujours paramétrées avec `%s`, donc protégées contre l'injection SQL.
- **Pool de connexions** : `db()` tire une connexion d'un `psycopg_pool.ConnectionPool` partagé (1 à 10 connexions), la valide (commit) puis la remet dans le pool — en cas d'exception, le pool fait un rollback avant réutilisation. Avant, chaque `with db()` ouvrait une connexion TCP dédiée ; un seul appel au dashboard Bourse en ouvrait 3 à 4.
- **Suppression douce** : les catégories, sources et types de paiement ne sont jamais supprimés. On met `actif=0`, et l'historique reste intact. Les renommer met aussi à jour les dépenses/revenus déjà saisis sous l'ancien nom (`categorie`/`source`/`paiement` stockés par nom, pas par id).
- **Migrations « additives »** : il n'y a ni Alembic ni outil équivalent. `init_db()` s'exécute à chaque démarrage et utilise `CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` — et, depuis le nettoyage du 26/09/2026, `DROP COLUMN IF EXISTS` pour les colonnes définitivement mortes (toutes ces opérations sont idempotentes, sans risque à rejouer à chaque démarrage).
- **Nommage en français** dans tout le code (fonctions, variables, colonnes).

---

## 2. Installation et lancement

### Prérequis
- Python 3.10 ou plus récent (le code utilise la syntaxe `str | None`)
- Une base PostgreSQL accessible

### Fichier `backend/.env`

```env
DATABASE_URL=postgresql://user:motdepasse@hote:5432/nom_base
ADMIN_UTILISATEUR=hassan
ADMIN_MOT_DE_PASSE=un_mot_de_passe_solide
PORT=8500               # optionnel, 8500 par défaut (Render fournit PORT automatiquement)
COOKIE_SECURE=false     # true en production derrière HTTPS
```

`ADMIN_UTILISATEUR` et `ADMIN_MOT_DE_PASSE` ne servent qu'au **premier démarrage**, pour créer le compte quand la table `utilisateurs` est vide.

### Commandes

```bash
cd backend
pip install -r requirements.txt
python app.py
```

- Interface : http://localhost:8500
- Documentation interactive de l'API (Swagger) : http://localhost:8500/docs

Les lanceurs `lancer_budget.bat` et `lancer_budget.sh` ouvrent le navigateur puis démarrent le serveur. Le `.sh` utilise `.venv/bin/python`. Le `.bat` utilise le `python` du système, pas le venv.

`gunicorn` figure dans `requirements.txt` pour la production, par exemple :
`gunicorn app:app -k uvicorn.workers.UvicornWorker`.

---

## 3. Backend fichier par fichier

### 3.1 `config.py` — configuration

- Charge `backend/.env` via `python-dotenv`. Si la bibliothèque n'est pas installée, seules les variables système sont lues.
- Définit `BASE_DIR` et `FRONT_DIR` (le dossier `frontend/`, servi en statique).
- Lit `DATABASE_URL`, `PORT`, `COOKIE_SECURE`, `ADMIN_UTILISATEUR` et `ADMIN_MOT_DE_PASSE`.
- `DATABASE_URL` manquant fait échouer l'import avec un message explicite (`RuntimeError`), au lieu de laisser `psycopg` échouer plus loin avec une erreur peu claire. `ADMIN_UTILISATEUR`/`ADMIN_MOT_DE_PASSE` ne sont vérifiés que dans `database.py`, au moment où `init_db()` en a réellement besoin (premier démarrage, table `utilisateurs` vide) — les valider ici serait une fausse alerte pour un redémarrage normal où ces variables ont été retirées du `.env` après la création du compte.
- `DUREE_SESSION_JOURS = 1` : une session expire au bout de 24 h.
- Valeurs insérées au premier démarrage :
  - `CATEGORIES_DEFAUT` : 11 catégories de dépense, chacune avec un budget mensuel (Alimentation 1500, Loyer 300, etc.)
  - `SOURCES_DEFAUT` : Salaire, Prime, Freelance, Remboursement
  - `PAIEMENTS_DEFAUT` : Espèces, Carte, Virement

### 3.2 `database.py` — base de données

**`TITRES_BVC_DEFAUT`** : liste d'environ 80 sociétés cotées à la BVC, sous la forme `(code, nom, secteur)`. Elle alimente la table `bourse_titres`, qui sert à l'autocomplétion du champ « Titre » dans le frontend.

**`_pool`** est un `psycopg_pool.ConnectionPool` créé une fois au chargement du module (1 à 10 connexions, `row_factory=dict_row`). **`db()`** est un gestionnaire de contexte (`@contextmanager`) qui tire une connexion du pool :
```python
with db() as c:
    c.execute("...", (params,))
# → commit automatique si aucune exception ; rollback + retour au pool sinon
```
`row_factory=dict_row` fait que chaque ligne renvoyée est un `dict` (`row["montant"]`), directement sérialisable en JSON par FastAPI. `app.py` ferme le pool sur l'évènement `shutdown` de FastAPI.

**`init_db()`** est appelée une fois au démarrage, depuis `app.py`. Elle :
1. crée toutes les tables et tous les index s'ils n'existent pas (voir [§4](#4-schéma-de-la-base-de-données)) ;
2. applique les migrations du module Bourse :
   - ajoute la colonne `taux_retenue_source_dividendes` si elle manque (nécessaire à l'étape suivante) ;
   - si l'ancienne colonne `bourse_dividendes.montant_brut` existe, calcule le montant net (`brut × (1 − taux de retenue)`) puis supprime les anciennes colonnes. Les dividendes sont désormais saisis en net ;
   - supprime (`DROP COLUMN IF EXISTS`, idempotent) les anciennes colonnes de taux figés dans `bourse_parametres` et `bourse_transactions`, devenues mortes depuis la simplification du module Bourse ;
3. insère les valeurs par défaut quand les tables sont vides : catégories, sources, paiements, objectif d'épargne (5000), compte administrateur (échoue avec un message explicite si `ADMIN_UTILISATEUR`/`ADMIN_MOT_DE_PASSE` manquent), ligne de paramètres Bourse, titres BVC ;
4. affiche un avertissement si le mot de passe administrateur vaut `"admin"`.

`hacher_mdp` est importé à l'intérieur de la fonction. Un import en tête de fichier créerait une boucle, car `securite.py` importe déjà `database.py`.

### 3.3 `securite.py` — authentification

| Fonction | Rôle |
|---|---|
| `hacher_mdp(mdp)` | PBKDF2-HMAC-SHA256, 200 000 itérations, sel aléatoire de 16 octets. Format stocké : `"<sel_hex>$<hash_hex>"`. |
| `verifier_mdp(mdp, stocke)` | Recalcule le hash avec le même sel et compare avec `secrets.compare_digest`, une comparaison en temps constant qui protège contre les attaques temporelles. |
| `creer_session(uid)` | Génère un jeton aléatoire (`token_urlsafe(32)`), l'enregistre dans `sessions` avec une date d'expiration et supprime au passage les sessions expirées. |
| `supprimer_session(token)` | Déconnexion. |
| `utilisateur_courant(session=Cookie)` | **Dépendance FastAPI** qui protège toutes les routes. Elle lit le cookie `session`, fait la jointure avec `utilisateurs` et renvoie `{id, nom}`. Si le cookie manque ou a expiré, elle lève une erreur **401**. |

Le cookie est `HttpOnly` (inaccessible au JavaScript, donc à l'abri d'un vol par XSS) et `SameSite=Lax` (protection de base contre le CSRF). Il est `Secure` si `COOKIE_SECURE=true`.

### 3.4 `schemas.py` — modèles Pydantic

Ces modèles valident automatiquement les données. Si la validation échoue, FastAPI renvoie une erreur 422.

| Modèle | Utilisation | Contraintes |
|---|---|---|
| `LoginIn` | connexion | — |
| `MdpIn` | changement de mot de passe | `nouveau` ≥ 6 caractères |
| `DepenseIn` | nouvelle dépense | `montant > 0` ; `date` est une simple `str`, sans validation de format |
| `RevenuIn` | nouveau revenu | `montant > 0` |
| `CategorieIn` | catégorie | `nom` non vide, `budget ≥ 0` |
| `ObjectifIn`, `NomIn` | objectif, source, paiement | — |
| `ParametresBourse` | paramètres Bourse | taux compris entre 0 et 1 |
| `TransactionBourseCreate` / `Out` | achat/vente | `type_instrument` ∈ {Action, Obligation, OPCVM, IPO}, `type_operation` ∈ {Achat, Vente}, `quantite > 0` |
| `PositionBourse`, `GainRealise`, `DashboardBourse` | sorties calculées | — |
| `DividendeCreate` / `Out`, `FraisBourseCreate` / `Out` | dividendes et frais de compte | `montant > 0` |

### 3.5 `app.py` — point d'entrée

1. Ajoute `backend/` au `sys.path`, pour que `python backend/app.py` fonctionne depuis n'importe quel dossier.
2. Appelle `init_db()`.
3. Crée l'application FastAPI et active CORS pour toutes les origines (`*`).
4. Branche les 5 routeurs.
5. Monte `frontend/` sur `/` **après** les routes API, pour que `/api/...` reste prioritaire. Avec `html=True`, `/` sert `index.html`.
6. Si le fichier est lancé directement, démarre `uvicorn` sur `0.0.0.0:PORT`.

### 3.6 `routes/auth.py`

- `POST /api/login` : vérifie les identifiants, crée la session et pose le cookie. Le message d'erreur (« Identifiants incorrects ») est volontairement le même que l'utilisateur existe ou non.
- `POST /api/logout` : supprime la session et le cookie.
- `GET /api/me` : renvoie le nom de l'utilisateur. Le frontend s'en sert au chargement pour savoir s'il faut afficher l'écran de connexion.
- `PUT /api/mot_de_passe` : vérifie l'ancien mot de passe, enregistre le nouveau hash et **supprime toutes les sessions** de l'utilisateur, ce qui déconnecte tous ses appareils.

### 3.7 `routes/configuration.py`

Tout le routeur est protégé par `dependencies=[Depends(utilisateur_courant)]`.

- `GET /api/categories` renvoie **en une seule requête** les catégories, les sources, les types de paiement et l'objectif d'épargne.
- Les routes `POST` utilisent `ON CONFLICT (nom) DO UPDATE SET actif=1`. Si on recrée une catégorie qui avait été désactivée, elle est réactivée au lieu de provoquer une erreur d'unicité.
- Les routes `PUT` (renommer) répercutent le nouveau nom sur les lignes déjà saisies : `modifier_categorie` met à jour `depenses.categorie`, `modifier_source` met à jour `revenus.source`, `modifier_paiement` met à jour `depenses.paiement` — sinon ces lignes resteraient rattachées à l'ancien nom (catégorie « fantôme » à budget 0 dans les rapports). Elles renvoient **404** si l'id n'existe pas.
- Les routes `DELETE` font une désactivation douce (`actif=0`) et renvoient **404** si l'id n'existe pas (`rowcount == 0`).

### 3.8 `routes/transactions.py`

Création et suppression des dépenses et revenus — les suppressions renvoient **404** si la ligne n'existe pas. `GET /api/transactions?mois=AAAA-MM` liste les deux types pour un mois donné. Le filtre utilise `date LIKE '2026-09-%'`, ce qui marche parce que les dates sont stockées en texte au format ISO.

### 3.9 `routes/rapports.py` — tableaux de bord

Fonctions utilitaires : `_valider_mois`, `_valider_date`, `_somme(c, table, where, params)` (une somme SQL générique), `_objectif`, `_budget_total`.

| Route | Contenu calculé |
|---|---|
| `GET /api/resume_jour?date=` | totaux du jour, dépenses de la veille, répartition par catégorie (donut), liste des transactions, **moyenne quotidienne du mois** jusqu'à ce jour, **budget journalier** = budget mensuel ÷ 30,44 |
| `GET /api/resume_semaine?date=` | semaine du lundi au dimanche contenant la date ; totaux, comparaison avec la semaine précédente, détail jour par jour, donut, top 8 ; **budget hebdomadaire** = budget mensuel × 12 ÷ 52 |
| `GET /api/resume?mois=` | vue mensuelle complète (détail ci-dessous) |
| `GET /api/resume_annuel?annee=` | 12 mois : revenus/dépenses/épargne par mois, meilleur et pire mois, nombre de mois où l'objectif est atteint, épargne cumulée, totaux par catégorie comparés au budget annuel (budget × 12), **grille catégorie × mois** pour la carte de chaleur |

Détail de `/api/resume` :
- `budget_vs_reel` : pour chaque catégorie active, dépense réelle ÷ budget en %, triée de la plus consommée à la moins consommée. Les dépenses rattachées à des catégories inactives ou renommées apparaissent aussi, avec un budget de 0.
- `cumul_quotidien` : dépenses cumulées jour après jour, pour le graphique en courbe.
- `evolution` : revenus et dépenses des 6 derniers mois, obtenus par un `UNION ALL` des deux tables regroupé par `substr(date,1,7)`.
- `projection_fin_mois` (mois en cours seulement) : `dépenses à ce jour ÷ jour du mois × nombre de jours du mois`.
- `taux_epargne` = (revenus − dépenses) ÷ revenus × 100.
- Comparaison avec le mois précédent.

### 3.10 `routes/bourse.py` — module Bourse

Tous les montants passent par `Decimal`, pour éviter les erreurs d'arrondi des `float` :
- `_d(v)` convertit n'importe quelle valeur en `Decimal` (et `None` en 0) ;
- `_r(x)` arrondit à 2 décimales (`ROUND_HALF_UP`) pour les montants, puis convertit en `float` pour le JSON ;
- `_r4(x)` arrondit à 4 décimales, réservé aux ratios (`performance_latente`) pour ne pas tronquer le pourcentage affiché.

Le filtre de période (`mois=AAAA-MM` ou `annee=AAAA`) est construit en SQL par `_clause_periode()` (`date_operation >= ... AND date_operation < ...`) pour `lister_transactions`, `_dividendes()` et `_frais_compte()` — ces listes n'ont besoin que des lignes de la période, la base ne renvoie donc que celles-là. Exception assumée : le résultat de `_positions_et_gains()` (gains réalisés, frais de transaction dans le dashboard) reste filtré **en Python** après coup, car cette fonction doit de toute façon charger tout l'historique des transactions pour calculer un PRU chronologique correct — les lignes sont déjà en mémoire, les refiltrer ici n'ajoute aucune requête.

La logique centrale se trouve dans `_positions_et_gains()` :
1. charge **toutes** les transactions triées par date, les cours actuels et le taux de TPCVM ;
2. `_calc_transaction` calcule `montant_brut = qté × cours`, puis `montant_net = brut + frais` pour un achat et `brut − frais` pour une vente ;
3. regroupe par titre, puis parcourt **chronologiquement** les transactions de chaque titre en tenant un état courant (quantité détenue, coût restant) : un achat ajoute la quantité et le coût, une vente calcule le gain avec le PRU **courant** avant de réduire le coût restant d'autant — un achat postérieur à une vente n'influence donc jamais son PRU ;
4. calcule les **positions** : PRU (du stock détenu à l'instant présent), quantité détenue, valeur comptable, valeur de marché, plus-value latente, performance ;
5. calcule les **gains réalisés** pour chaque vente, avec la TPCVM — calculée vente par vente, sans compensation des pertes sur l'année (voir la docstring de `_positions_et_gains()` et [§8 point 19](#-qualité-et-performance)).

`_valider_vente()` reconstitue la chronologie complète d'un titre (transaction à insérer comprise) et refuse toute vente qui ferait passer la quantité détenue sous zéro à un instant quelconque — y compris pour une vente antidatée.

Routes : `parametres` (GET/PUT), `titres`, `transactions` (GET/POST/DELETE), `prix/{titre}` (PUT, insertion ou mise à jour du cours actuel), `dividendes`, `frais`, `positions`, `gains`, `dashboard`. Les formules sont détaillées au [§6](#6-calculs-métier).

### 3.11 `scripts/supprimer_bourse.py`

Script manuel (pas un test, malgré l'ancien fichier `test.py` qui portait ce nom par erreur — supprimé). Supprime `bourse_transactions`, `bourse_dividendes`, `bourse_frais`, `bourse_prix`, `bourse_parametres` et `bourse_titres` après avoir demandé de taper « oui ». Lancement : `python scripts/supprimer_bourse.py` depuis `backend/`.

---

## 4. Schéma de la base de données

### Budget

| Table | Colonnes principales | Remarques |
|---|---|---|
| `categories` | `id`, `nom` UNIQUE, `budget`, `actif` | budget mensuel en DH |
| `depenses` | `id`, `date` **TEXT**, `categorie` **TEXT**, `description`, `montant`, `paiement`, `cree_le` | catégorie/paiement stockés **par leur nom**, sans clé étrangère — un renommage côté `categories`/`paiements` met donc à jour ces colonnes en cascade (voir [§3.7](#37-routesconfigurationpy)) |
| `revenus` | `id`, `date` TEXT, `source`, `montant`, `cree_le` | `source` idem : mise à jour en cascade au renommage |
| `sources_revenus` | `id`, `nom` UNIQUE, `actif` | |
| `paiements` | `id`, `nom` UNIQUE, `actif` | |
| `params` | `cle` PK, `valeur` | ne contient pour l'instant que `objectif_epargne` |
| `utilisateurs` | `id`, `nom` UNIQUE, `mdp_hash` | |
| `sessions` | `token` PK, `utilisateur_id` FK (ON DELETE CASCADE), `expire` | |

Index : `depenses(date)`, `revenus(date)`.

### Bourse

| Table | Colonnes principales | Remarques |
|---|---|---|
| `bourse_parametres` | `taux_tpcvm` | une seule ligne ; les anciennes colonnes de taux (courtage, TVA, OPCVM, IPO…) et celles des droits de garde (`taux_droit_garde_annuel`, `droit_garde_min_trimestriel`, désormais saisis manuellement) ont été supprimées le 26/09/2026 |
| `bourse_transactions` | `date_operation` DATE, `titre`, `isin`, `type_instrument`, `type_operation`, `quantite`, `cours_unitaire`, `autres_frais` | contraintes `CHECK` sur les types et les quantités ; anciennes colonnes de taux figés supprimées le 26/09/2026 |
| `bourse_prix` | `titre` PK, `cours_actuel`, `maj_le` | un seul cours par titre, sans historique |
| `bourse_titres` | `code` UNIQUE, `nom`, `secteur`, `actif` | référentiel BVC |
| `bourse_dividendes` | `date_operation`, `titre`, `montant` (net) | |
| `bourse_frais` | `date_operation`, `libelle`, `montant` | abonnement courtier, tenue de compte, droits de garde… |

Le module Bourse utilise de vrais types `DATE` et `NUMERIC`. Le module Budget utilise `TEXT` pour les dates et `DOUBLE PRECISION` pour les montants.

---

## 5. Référence de l'API

Toutes les routes sauf `/api/login` et `/api/logout` exigent le cookie `session`.

| Méthode | Route | Corps / paramètres | Réponse |
|---|---|---|---|
| POST | `/api/login` | `{utilisateur, mot_de_passe}` | `{ok}` + cookie |
| POST | `/api/logout` | — | `{ok}` |
| GET | `/api/me` | — | `{utilisateur}` |
| PUT | `/api/mot_de_passe` | `{actuel, nouveau}` | `{ok, message}` |
| GET | `/api/categories` | — | `{categories, sources, paiements, objectif_epargne}` |
| POST / PUT / DELETE | `/api/categories[/{id}]` | `{nom, budget}` | `{ok}` |
| PUT | `/api/objectif` | `{objectif}` | `{ok}` |
| POST / PUT / DELETE | `/api/sources[/{id}]`, `/api/paiements[/{id}]` | `{nom}` | `{ok}` |
| POST / DELETE | `/api/depenses[/{id}]` | `{date, categorie, description, montant, paiement}` | `{id}` / `{ok}` |
| POST / DELETE | `/api/revenus[/{id}]` | `{date, source, montant}` | `{id}` / `{ok}` |
| GET | `/api/transactions?mois=` | — | `{depenses, revenus}` |
| GET | `/api/resume_jour?date=` | — | résumé du jour |
| GET | `/api/resume_semaine?date=` | — | résumé de la semaine |
| GET | `/api/resume?mois=` | — | résumé du mois |
| GET | `/api/resume_annuel?annee=` | — | résumé de l'année |
| GET / PUT | `/api/bourse/parametres` | `ParametresBourse` | `ParametresBourse` |
| GET | `/api/bourse/titres` | — | `[TitreBourse]` |
| GET / POST | `/api/bourse/transactions` | `?mois=&annee=` / `TransactionBourseCreate` | `[TransactionBourseOut]` |
| DELETE | `/api/bourse/transactions/{id}` | — | 204 |
| PUT | `/api/bourse/prix/{titre}` | `{cours_actuel}` | `{titre, cours_actuel}` |
| GET / POST / DELETE | `/api/bourse/dividendes[/{id}]` | `?mois=&annee=` / `{date_operation, titre, montant}` | |
| GET / POST / DELETE | `/api/bourse/frais[/{id}]` | `?mois=&annee=` / `{date_operation, libelle, montant}` | |
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
| Budget journalier | budget mensuel ÷ 30,44 (durée moyenne d'un mois) |
| Budget hebdomadaire | budget mensuel × 12 ÷ 52 |
| Projection fin de mois | dépenses à ce jour ÷ jour actuel × nombre de jours du mois |
| Badge ▲/▼ (frontend) | (actuel − précédent) ÷ précédent × 100 ; affiche « ＝ » si l'écart est inférieur à 0,5 % |
| Couleur « budget vs réel » | vert ≤ 80 %, jaune ≤ 100 %, rouge au-delà |

### 6.2 Bourse

| Indicateur | Formule |
|---|---|
| Montant net d'un achat | qté × cours + autres frais |
| Montant net d'une vente | qté × cours − autres frais |
| **PRU** (coût moyen mobile) | recalculé **chronologiquement, titre par titre** : à chaque achat, ajoute la quantité et le coût au stock détenu ; à chaque vente, utilise le PRU courant du stock à cet instant, puis retire `PRU courant × qté vendue` du coût restant. Un achat postérieur à une vente n'influence jamais le PRU utilisé pour cette vente. |
| Quantité détenue | Σ achats − Σ ventes |
| Valeur comptable | PRU (du stock actuellement détenu) × quantité détenue |
| Valeur de marché | cours actuel × quantité détenue |
| Plus-value latente | valeur de marché − valeur comptable |
| Performance latente | plus-value latente ÷ valeur comptable, arrondie à 4 décimales (pas 2, pour ne pas tronquer le pourcentage affiché) |
| Gain brut d'une vente | montant net de la vente − PRU courant × qté vendue |
| TPCVM | gain brut × taux (15 % par défaut), seulement si le gain est positif |
| Gain net | gain brut − TPCVM |
| Résultat net de la période | gains nets + dividendes − frais de compte (les frais de transaction sont déjà comptés dans `gains nets` et dans le PRU des achats — les resoustraire doublerait leur effet) |
| Validation à la vente | refusée si elle ferait passer la quantité détenue sous zéro **à un instant quelconque de l'historique** (utile pour une vente antidatée insérée après coup) |

---

## 7. Frontend

### 7.1 `index.html`

Une seule page contient :
- l'écran de connexion (`#ecran-login`) ;
- l'en-tête avec la date, le bouton de thème jour/nuit et le bouton de déconnexion ;
- quatre sections qui correspondent aux onglets de la barre de navigation du bas :
  - **Saisie** (`#tab-saisie`) : formulaires de dépense et de revenu, transactions du mois en cours ;
  - **Dashboard** (`#tab-dash`) : quatre vues (Jour / Semaine / Mois / Année) avec des flèches ‹ › pour naviguer ;
  - **Bourse** (`#tab-bourse`) : sept sous-vues (Transactions, Positions, Gains, Dividendes, Frais, Dashboard, Paramètres) ;
  - **Paramètres** (`#tab-params`) : objectif d'épargne, catégories et budgets, sources, types de paiement, mot de passe.

La navigation se fait **sans routeur** : on bascule `style.display` entre `''` et `'none'`. Les boutons appellent des fonctions globales via `onclick="..."`.

`app.js` et `bourse.js` sont chargés avec `?v=3`, pour forcer le navigateur à recharger les fichiers après une mise à jour.

### 7.2 `js/app.js`

**Utilitaires**
- `$(id)` : raccourci pour `getElementById`.
- `fmt(v)` : formate un montant en `1 234,5 DH` (locale fr-FR, 2 décimales au maximum).
- `lireMontant(id)` : accepte la virgule ou le point, retire les espaces, arrondit aux centimes.
- `auj()` : date du jour en heure **locale**. Le code évite volontairement `toISOString()`, qui passe en UTC et peut donner la date de la veille ou du lendemain.
- `toast(msg, ok)` : notification verte ou rouge pendant 1,8 s.
- `api(path, opts)` : enveloppe de `fetch`. Sur une réponse 401, elle affiche l'écran de connexion. Sur une autre erreur, elle affiche `detail` dans un toast puis lève une exception.

**Cycle de vie**
1. `init()` (fonction exécutée immédiatement) : applique le thème enregistré, préremplit les dates, appelle `/api/me`.
2. Si la session est valide, `demarrerApp()` ; sinon, écran de connexion.
3. `montrer(onglet)` affiche l'onglet et charge ses données **à chaque ouverture**. Il n'y a pas de cache.

**Saisie** : `chargerCats()` remplit les listes déroulantes et les boutons de paiement (`paySel` garde le paiement choisi). L'option « Autre… » dans les sources affiche un champ libre.

**Dashboards** : `chargerDash()` (mois), `chargerDashJour()`, `chargerDashSemaine()` et `chargerDashAnnee()`. Les vues mois et année appellent aussi `resumeBourseSilencieux()` en parallèle (`Promise.all`) pour ajouter deux indicateurs Bourse. Cet appel ne remonte jamais d'erreur, pour qu'un problème Bourse ne casse pas le dashboard Budget.

`dessiner(id, cfg)` détruit le graphique existant avant d'en créer un nouveau, ce qui évite les fuites mémoire et les superpositions. Si Chart.js n'est pas chargé, l'application fonctionne sans graphiques.

**Thème** : `appliquerTheme()` pose `data-theme` sur `<html>`, enregistre le choix dans `localStorage`, adapte les couleurs par défaut de Chart.js et redessine le dashboard s'il est affiché.

### 7.3 `js/bourse.js`

Il réutilise les utilitaires globaux d'`app.js`, qui doit donc être chargé avant lui.
- `changerVueBourse(v)` : bascule entre les sept sous-vues et charge celle qui est active.
- Le cours actuel se modifie **directement dans le tableau des positions** : un `<input>` avec `onchange` appelle `majCoursBourse()`.
- Le dashboard Bourse a trois modes (Global / Mois / Année) et sa propre navigation ‹ ›.
- Les paramètres sont affichés en % (`pct()` multiplie par 100) et renvoyés en fraction (÷ 100).
- `chargerTitresBourse()` remplit un `<datalist>` HTML5 pour l'autocomplétion des codes BVC.

### 7.4 `css/style.css`

- Variables CSS dans `:root` (thème sombre par défaut), redéfinies dans `[data-theme="light"]`.
- Couleurs métier : safran `--accent` pour les dépenses, bleu `--blue` pour les revenus, vert `--green` pour l'épargne, rouge `--red`.
- Mise en page responsive : `.grid2` passe sur une colonne sous 820 px, et d'autres ajustements s'appliquent sous 560 px.
- Respecte `prefers-reduced-motion` (animations réduites si l'utilisateur l'a demandé).

---

## 8. Problèmes détectés et recommandations

Classés par gravité. Les numéros de ligne renvoient à l'état actuel du code.

### 🔴 Erreurs de calcul (module Bourse) — ✅ corrigées le 26/09/2026

Les 4 points ci-dessous sont **résolus**, couverts par des tests automatisés
([backend/tests/test_bourse.py](backend/tests/test_bourse.py)). Gardés ici à
titre d'historique — utile pour comprendre pourquoi le code est écrit ainsi.

**1. ~~Les frais de transaction étaient déduits deux fois du résultat de la période~~**
Les `autres_frais` sont déjà inclus dans `montant_net`, donc dans le PRU (achats) et dans le gain brut (ventes). `resultat_net_periode` les soustrayait une seconde fois via `frais_transactions`.
*Exemple* : achat de 10 × 100 avec 10 DH de frais, puis vente de 10 × 120 avec 10 DH de frais. Le gain brut vaut déjà 1190 − 1010 = 180, et le gain net 153. Le dashboard affichait 153 − 20 = 133 au lieu de 153.
*Correction appliquée* : `frais_transactions` retiré du calcul de `resultat_net_periode` (le KPI reste affiché, à titre d'information uniquement). Voir [backend/routes/bourse.py](backend/routes/bourse.py) (recherche `resultat_periode`).

**2. ~~Le PRU était calculé sur tout l'historique, y compris les achats postérieurs à une vente~~**
*Exemple* : achat de 10 × 100 en janvier, vente de 10 × 120 en février, rachat de 10 × 200 en mars. L'ancien PRU global valait (1000 + 2000) ÷ 20 = 150, donc la vente de février affichait une perte de −300 au lieu d'un gain de +200, et la position de mars une valeur comptable de 1500 au lieu de 2000.
*Correction appliquée* : `_positions_et_gains()` parcourt maintenant les transactions dans l'ordre chronologique, titre par titre, avec un état courant (quantité détenue, coût restant). À un achat, la quantité et le coût s'ajoutent. À une vente, le gain est calculé avec le PRU **courant**, puis `PRU courant × qté` est retiré du coût restant.

**3. ~~La performance latente était arrondie à 2 décimales alors que c'est une fraction~~**
`_r(0.0534)` donnait `0.05`, et le frontend affichait « 5,00 % » au lieu de « 5,34 % ».
*Correction appliquée* : nouvelle fonction `_r4()` (arrondi à 4 décimales), utilisée pour `performance_latente` dans les positions et le dashboard.

**4. ~~Rien n'empêchait de vendre plus que ce qu'on détient~~**
*Correction appliquée* : `_valider_vente()` reconstitue l'historique chronologique du titre (avec la nouvelle transaction insérée à sa date) et refuse la vente (HTTP 400) si la quantité détenue passerait sous zéro à un instant quelconque — y compris pour une vente antidatée insérée entre deux transactions existantes.

### 🟠 Bugs fonctionnels — ✅ corrigés le 26/09/2026

**5. ~~Les dates des formulaires Bourse n'étaient jamais préremplies~~**
Les champs `b-date`, `bd-date` et `bf-date` n'étaient pas initialisés dans `init()`, contrairement à `d-date` et `r-date`. Si l'utilisateur oubliait de choisir une date, l'API répondait 422 et le toast affichait `[object Object]`, car `detail` est un tableau pour les erreurs de validation Pydantic.
*Correction appliquée* : `init()` initialise maintenant ces trois champs avec `auj()` ; `api()` détecte un `detail` tableau (422 Pydantic) et affiche les messages joints plutôt que `[object Object]`.

**6. ~~Renommer une catégorie « détachait » ses anciennes dépenses~~**
`depenses.categorie` stocke le nom, pas l'identifiant. Après un renommage, les anciennes dépenses apparaissaient dans « Budget vs Réel » sous l'ancien nom avec un budget de 0. Il en allait de même pour les sources et les paiements.
*Correction appliquée* : `modifier_categorie`/`modifier_source`/`modifier_paiement` mettent à jour respectivement `depenses.categorie`, `revenus.source` et `depenses.paiement` quand le nom change. Testé par [test_budget.py](backend/tests/test_budget.py).

**7. ~~Aucune erreur 404 sur les modifications et suppressions du module Budget~~**
`DELETE /api/depenses/999` renvoyait `{ok: true}`, même si la ligne n'existait pas.
*Correction appliquée* : toutes les routes de `configuration.py` et `transactions.py` vérifient maintenant `rowcount`/l'existence de la ligne et lèvent une 404, comme le fait déjà le module Bourse.

**8. ~~Plantage au démarrage si le fichier `.env` était incomplet~~**
Si `ADMIN_UTILISATEUR` ou `ADMIN_MOT_DE_PASSE` manquait, `init_db()` échouait avec une erreur peu claire (`NOT NULL` violée, ou `None.encode()`). Si `DATABASE_URL` manquait, `psycopg` échouait avant même le `print` de app.py.
*Correction appliquée* : `config.py` lève un `RuntimeError` explicite si `DATABASE_URL` manque ; `init_db()` fait de même pour `ADMIN_UTILISATEUR`/`ADMIN_MOT_DE_PASSE`, mais seulement au moment où ils sont réellement nécessaires (premier démarrage, table `utilisateurs` vide) pour ne pas gêner un redémarrage normal.

### 🟡 Sécurité

**9. Risque de XSS : des données saisies sont injectées via `innerHTML` sans échappement**
Descriptions, noms de catégories et de sources, titres et libellés de frais sont concernés. Par exemple, une description `<img src=x onerror=alert(1)>` s'exécute. Dans l'onglet Paramètres, un nom contenant `"` casse l'attribut `value="${c.nom}"`. L'application n'a qu'un utilisateur, donc le risque est faible, mais le code est fragile.
*Correction* : ajouter une fonction `esc()` (qui remplace `& < > " '`) et l'appliquer à chaque valeur insérée.

**10. Aucune limite de tentatives de connexion**
Le mot de passe peut être attaqué par force brute. PBKDF2 à 200 000 itérations ralentit chaque essai, mais n'empêche pas l'attaque.

**11. Validation des dates incomplète dans le module Budget**
`DepenseIn.date` et `RevenuIn.date` sont des `str` libres. Une date mal formée serait enregistrée et fausserait les filtres `LIKE`.
*Correction* : typer ces champs en `datetime.date`.

**12. CORS ouvert à toutes les origines (`allow_origins=["*"]`)**
C'est sans conséquence tant que `allow_credentials` n'est pas activé et que le frontend est servi par le même serveur, mais ce réglage est à restreindre si le frontend est un jour hébergé ailleurs.

### 🔵 Qualité et performance

13. ~~**Pas de pool de connexions.**~~ ✅ corrigé le 26/09/2026 — `database.py` utilise maintenant un `psycopg_pool.ConnectionPool` partagé (1 à 10 connexions) au lieu d'ouvrir une connexion TCP par `with db()`. Un seul appel au dashboard Bourse en ouvrait 3 à 4 auparavant. Testé sous 50 requêtes concurrentes (Bourse + Budget mêlées) et sur le chemin d'erreur (rollback avant réutilisation) sans corruption ni perte de connexion.
14. ~~**Filtres de période appliqués en Python.**~~ ✅ corrigé le 26/09/2026 pour les listes (`lister_transactions`, `_dividendes`, `_frais_compte`) : filtre `WHERE date_operation >= ... AND < ...` construit par `_clause_periode()`, au lieu de charger toutes les lignes. Reste volontairement en Python pour les gains/frais du dashboard, dérivés de `_positions_et_gains()` qui doit de toute façon parcourir tout l'historique pour un PRU chronologique correct (voir [§3.10](#310-routesboursepy--module-bourse)).
15. **Types incohérents** : `TEXT` et `DOUBLE PRECISION` dans le module Budget, `DATE` et `NUMERIC` dans le module Bourse. Des montants en `float` accumulent des erreurs d'arrondi.
    **Non corrigé, délibérément.** `rapports.py` et `transactions.py` s'appuient massivement sur des fonctions texte SQLite-compatibles (`date LIKE '2026-09-%'`, `substr(date,6,2)`, `substr(date,1,7)`) dans **toutes** les vues (jour/semaine/mois/année, cumul, évolution, grille thermique). Migrer `date` en `DATE` casserait chacune de ces requêtes et demanderait de les réécrire une par une ; migrer `montant`/`budget` en `NUMERIC` ferait remonter des `Decimal` qui plantent dès qu'ils sont mélangés à un littéral `float` Python (ex : `budget_total / 30.44`). Le gain (arrondis plus propres) est réel mais mineur à l'échelle d'un budget personnel ; le risque de régression sur une app déjà en usage réel est disproportionné pour un nettoyage de confort. À reprendre uniquement avec une suite de tests couvrant chaque vue du dashboard Budget au préalable.
16. ~~**Colonnes mortes** dans `bourse_parametres` et `bourse_transactions`.~~ ✅ corrigé le 26/09/2026 — supprimées par une migration additive (`DROP COLUMN IF EXISTS`, idempotente), vérifiée sans impact sur les transactions réelles existantes.
17. ~~**`test.py` était mal nommé et incomplet.**~~ ✅ corrigé le 26/09/2026 — remplacé par [scripts/supprimer_bourse.py](backend/scripts/supprimer_bourse.py), qui supprime aussi `bourse_dividendes`, `bourse_frais` et `bourse_titres` (oubliés dans l'ancien script).
18. **Tests automatisés partiels.** [test_bourse.py](backend/tests/test_bourse.py) (PRU chronologique, frais, arrondi de performance, garde-fou de vente) et [test_budget.py](backend/tests/test_budget.py) (cascade de renommage, 404) — 15 tests au total. L'authentification et les calculs de `rapports.py` n'ont toujours aucun test.
19. **La TPCVM est calculée vente par vente** : les pertes ne viennent pas compenser les gains de la même année.
    **Documenté, non corrigé** (26/09/2026) — la règle marocaine de compensation annuelle des plus/moins-values de cession n'est pas confirmée avec assez de certitude pour coder une correction fiscale sans risquer de se tromper dans l'autre sens. Avertissement ajouté dans la docstring de `_positions_et_gains()` et dans l'onglet Paramètres > Fiscalité du frontend, invitant à vérifier auprès d'un professionnel en cas de ventes multiples (gagnantes et perdantes) sur la même année.
20. ~~Le lanceur `lancer_budget.bat` utilisait le Python du système au lieu du venv.~~ ✅ corrigé le 26/09/2026 — utilise `.venv\Scripts\python.exe` s'il existe, sinon le `python` du système.
21. ~~`README.md` ne contenait que deux lignes.~~ ✅ déjà résolu — renvoie vers ce document et décrit l'installation, le déploiement et la structure du projet.

---

### Priorités suggérées

1. ~~Corriger les calculs Bourse (points 1 à 4), qui faussaient directement les chiffres affichés, et les couvrir par des tests.~~ ✅ fait le 26/09/2026.
2. ~~Préremplir les dates Bourse et améliorer l'affichage des erreurs 422 (point 5) ; gérer le renommage des catégories (point 6) ; 404 sur le module Budget (point 7) ; erreurs de démarrage explicites (point 8).~~ ✅ fait le 26/09/2026.
3. ~~Pool de connexions (13), filtres SQL (14), colonnes mortes (16), script de suppression (17), lanceur Windows (20).~~ ✅ fait le 26/09/2026.
4. Restant : échapper le HTML (point 9, sécurité), limiter les tentatives de connexion (10), valider les dates du Budget en `datetime.date` (11), restreindre CORS si le frontend est un jour hébergé ailleurs (12).
5. Types de colonnes du Budget (15) : à ne reprendre qu'avec une suite de tests complète sur `rapports.py` au préalable — voir la justification du point 15.
