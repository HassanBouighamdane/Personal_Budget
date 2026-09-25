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
│   ├── test.py             Script utilitaire : supprime les tables Bourse (pas un test)
│   ├── requirements.txt
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
- **Une connexion par requête** : `db()` ouvre une connexion, la valide (commit) puis la ferme. C'est simple, mais il n'y a pas de pool de connexions.
- **Suppression douce** : les catégories, sources et types de paiement ne sont jamais supprimés. On met `actif=0`, et l'historique reste intact.
- **Migrations « additives »** : il n'y a ni Alembic ni outil équivalent. `init_db()` s'exécute à chaque démarrage et utilise `CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`.
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
- `DUREE_SESSION_JOURS = 1` : une session expire au bout de 24 h.
- Valeurs insérées au premier démarrage :
  - `CATEGORIES_DEFAUT` : 11 catégories de dépense, chacune avec un budget mensuel (Alimentation 1500, Loyer 300, etc.)
  - `SOURCES_DEFAUT` : Salaire, Prime, Freelance, Remboursement
  - `PAIEMENTS_DEFAUT` : Espèces, Carte, Virement

### 3.2 `database.py` — base de données

**`TITRES_BVC_DEFAUT`** : liste d'environ 80 sociétés cotées à la BVC, sous la forme `(code, nom, secteur)`. Elle alimente la table `bourse_titres`, qui sert à l'autocomplétion du champ « Titre » dans le frontend.

**`db()`** est un gestionnaire de contexte (`@contextmanager`) :
```python
with db() as c:
    c.execute("...", (params,))
# → commit automatique si aucune exception ; fermeture dans tous les cas
```
`row_factory=dict_row` fait que chaque ligne renvoyée est un `dict` (`row["montant"]`), directement sérialisable en JSON par FastAPI.

**`init_db()`** est appelée une fois au démarrage, depuis `app.py`. Elle :
1. crée toutes les tables et tous les index s'ils n'existent pas (voir [§4](#4-schéma-de-la-base-de-données)) ;
2. applique les migrations du module Bourse :
   - ajoute la colonne `taux_retenue_source_dividendes` si elle manque ;
   - si l'ancienne colonne `bourse_dividendes.montant_brut` existe, calcule le montant net (`brut × (1 − taux de retenue)`) puis supprime les anciennes colonnes. Les dividendes sont désormais saisis en net ;
3. insère les valeurs par défaut quand les tables sont vides : catégories, sources, paiements, objectif d'épargne (5000), compte administrateur, ligne de paramètres Bourse, titres BVC ;
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
| `PositionBourse`, `GainRealise`, `DroitsGarde`, `DashboardBourse` | sorties calculées | — |
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
- Les routes `DELETE` font une désactivation douce (`actif=0`).

### 3.8 `routes/transactions.py`

Création et suppression des dépenses et revenus. `GET /api/transactions?mois=AAAA-MM` liste les deux types pour un mois donné. Le filtre utilise `date LIKE '2026-09-%'`, ce qui marche parce que les dates sont stockées en texte au format ISO.

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
- `_r(x)` arrondit à 2 décimales (`ROUND_HALF_UP`) puis convertit en `float` pour le JSON.

Le filtre de période est commun à toutes les routes : les paramètres optionnels `mois=AAAA-MM` ou `annee=AAAA` sont appliqués **en Python** par `_dans_periode()`, après avoir chargé toutes les lignes.

La logique centrale se trouve dans `_positions_et_gains()` :
1. charge **toutes** les transactions triées par date, les cours actuels et le taux de TPCVM ;
2. `_calc_transaction` calcule `montant_brut = qté × cours`, puis `montant_net = brut + frais` pour un achat et `brut − frais` pour une vente ;
3. regroupe par titre : quantité achetée, quantité vendue, coût d'achat total ;
4. calcule les **positions** : PRU, quantité détenue, valeur comptable, valeur de marché, plus-value latente, performance ;
5. calcule les **gains réalisés** pour chaque vente, avec la TPCVM.

Routes : `parametres` (GET/PUT), `titres`, `transactions` (GET/POST/DELETE), `prix/{titre}` (PUT, insertion ou mise à jour du cours actuel), `dividendes`, `frais`, `positions`, `gains`, `droits_garde`, `dashboard`. Les formules sont détaillées au [§6](#6-calculs-métier).

### 3.11 `test.py`

Malgré son nom, ce n'est **pas un test**. C'est un script **destructif** qui supprime `bourse_transactions`, `bourse_prix` et `bourse_parametres` après avoir demandé de taper « oui ». Sa docstring parle de `supprimer_bourse.py`, l'ancien nom du fichier.

---

## 4. Schéma de la base de données

### Budget

| Table | Colonnes principales | Remarques |
|---|---|---|
| `categories` | `id`, `nom` UNIQUE, `budget`, `actif` | budget mensuel en DH |
| `depenses` | `id`, `date` **TEXT**, `categorie` **TEXT**, `description`, `montant`, `paiement`, `cree_le` | la catégorie est stockée **par son nom**, sans clé étrangère |
| `revenus` | `id`, `date` TEXT, `source`, `montant`, `cree_le` | |
| `sources_revenus` | `id`, `nom` UNIQUE, `actif` | |
| `paiements` | `id`, `nom` UNIQUE, `actif` | |
| `params` | `cle` PK, `valeur` | ne contient pour l'instant que `objectif_epargne` |
| `utilisateurs` | `id`, `nom` UNIQUE, `mdp_hash` | |
| `sessions` | `token` PK, `utilisateur_id` FK (ON DELETE CASCADE), `expire` | |

Index : `depenses(date)`, `revenus(date)`.

### Bourse

| Table | Colonnes principales | Remarques |
|---|---|---|
| `bourse_parametres` | taux de garde, minimum trimestriel, `taux_tpcvm`, et beaucoup d'anciens taux (courtage, TVA, OPCVM, IPO…) | une seule ligne ; les anciens taux ne sont plus lus |
| `bourse_transactions` | `date_operation` DATE, `titre`, `isin`, `type_instrument`, `type_operation`, `quantite`, `cours_unitaire`, `autres_frais`, et d'anciennes colonnes de taux figés | contraintes `CHECK` sur les types et les quantités |
| `bourse_prix` | `titre` PK, `cours_actuel`, `maj_le` | un seul cours par titre, sans historique |
| `bourse_titres` | `code` UNIQUE, `nom`, `secteur`, `actif` | référentiel BVC |
| `bourse_dividendes` | `date_operation`, `titre`, `montant` (net) | |
| `bourse_frais` | `date_operation`, `libelle`, `montant` | abonnement courtier, tenue de compte… |

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
| GET | `/api/bourse/droits_garde` | — | `DroitsGarde` |
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
| **PRU** (coût moyen pondéré) | Σ montants nets des achats ÷ Σ quantités achetées, **sur tout l'historique** |
| Quantité détenue | Σ achats − Σ ventes |
| Valeur comptable | PRU × quantité détenue |
| Valeur de marché | cours actuel × quantité détenue |
| Plus-value latente | valeur de marché − valeur comptable |
| Performance latente | plus-value latente ÷ valeur comptable |
| Gain brut d'une vente | montant net de la vente − PRU × qté vendue |
| TPCVM | gain brut × taux (15 % par défaut), seulement si le gain est positif |
| Gain net | gain brut − TPCVM |
| Droits de garde (trimestre) | max(valeur de marché × taux annuel ÷ 4, minimum trimestriel) |
| Résultat net de la période | gains nets + dividendes − frais de transactions − frais de compte |

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

### 🔴 Erreurs de calcul (module Bourse)

**1. Les frais de transaction sont déduits deux fois du résultat de la période**
[backend/routes/bourse.py:362](backend/routes/bourse.py#L362)
Les `autres_frais` sont déjà inclus dans `montant_net`, donc dans le PRU (achats) et dans le gain brut (ventes). `resultat_net_periode` les soustrait une seconde fois via `frais_transactions`.
*Exemple* : achat de 10 × 100 avec 10 DH de frais, puis vente de 10 × 120 avec 10 DH de frais. Le gain brut vaut déjà 1190 − 1010 = 180, et le gain net 153. Le dashboard affiche 153 − 20 = **133**.
*Correction* : retirer `frais_transactions` du calcul du résultat, en gardant le KPI à titre d'information seulement.

**2. Le PRU est calculé sur tout l'historique, y compris les achats postérieurs à une vente**
[backend/routes/bourse.py:259-300](backend/routes/bourse.py#L259-L300)
*Exemple* : achat de 10 × 100 en janvier, vente de 10 × 120 en février, rachat de 10 × 200 en mars. Le PRU vaut (1000 + 2000) ÷ 20 = 150, donc :
- la vente de février affiche une **perte de −300** au lieu d'un gain de +200, et la TPCVM est fausse ;
- la position de mars a une valeur comptable de 1500 au lieu de 2000.

*Correction* : parcourir les transactions dans l'ordre chronologique en tenant pour chaque titre la quantité détenue et le coût restant. À un achat, ajouter la quantité et le coût. À une vente, calculer le gain avec le PRU **courant**, puis retirer `PRU × qté` du coût restant.

**3. La performance latente est arrondie à 2 décimales alors que c'est une fraction**
[backend/routes/bourse.py:283](backend/routes/bourse.py#L283) et [:366](backend/routes/bourse.py#L366)
`_r(0.0534)` donne `0.05`, et le frontend affiche « 5,00 % » au lieu de « 5,34 % ».
*Correction* : arrondir à 4 décimales ou renvoyer directement un pourcentage.

**4. Rien n'empêche de vendre plus que ce qu'on détient**
Il n'existe aucune vérification. La quantité détenue devient négative et les valeurs calculées n'ont plus de sens.

### 🟠 Bugs fonctionnels

**5. Les dates des formulaires Bourse ne sont jamais préremplies**
Les champs `b-date`, `bd-date` et `bf-date` ne sont pas initialisés dans `init()`, contrairement à `d-date` et `r-date`. Si l'utilisateur oublie de choisir une date, l'API répond 422 et le toast affiche `[object Object]`, car `detail` est un tableau pour les erreurs de validation Pydantic.
*Correction* : initialiser ces trois champs avec `auj()` et gérer le cas où `detail` est un tableau dans `api()`.

**6. Renommer une catégorie « détache » ses anciennes dépenses**
`depenses.categorie` stocke le nom, pas l'identifiant. Après un renommage, les anciennes dépenses apparaissent dans « Budget vs Réel » sous l'ancien nom avec un budget de 0. Il en va de même pour les sources et les paiements.
*Correction* : mettre à jour `depenses.categorie` dans `modifier_categorie`, ou mieux, passer à une clé étrangère `categorie_id`.

**7. Aucune erreur 404 sur les modifications et suppressions du module Budget**
`DELETE /api/depenses/999` renvoie `{ok: true}`, même si la ligne n'existe pas. Le module Bourse, lui, vérifie `rowcount`.

**8. Plantage au démarrage si le fichier `.env` est incomplet**
Si `ADMIN_UTILISATEUR` ou `ADMIN_MOT_DE_PASSE` manque, `init_db()` échoue avec une erreur peu claire (`NOT NULL` violée, ou `None.encode()`). Si `DATABASE_URL` manque, `psycopg` échoue avant même le `print` de [app.py:61](backend/app.py#L61).
*Correction* : vérifier ces variables dans `config.py` et afficher un message explicite.

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

13. **Pas de pool de connexions.** `/api/bourse/dashboard` ouvre 3 connexions (`_positions_et_gains`, `_dividendes`, `_frais_compte`), et le dashboard du mois en ouvre 2 ou 3 de plus, sans compter celle de l'authentification. Utiliser `psycopg_pool.ConnectionPool` réglerait ce point.
14. **Filtres de période appliqués en Python** : toutes les lignes sont chargées puis filtrées. Un `WHERE date_operation BETWEEN ...` en SQL serait plus efficace.
15. **Types incohérents** : `TEXT` et `DOUBLE PRECISION` dans le module Budget, `DATE` et `NUMERIC` dans le module Bourse. Des montants en `float` accumulent des erreurs d'arrondi. Migrer le Budget vers `DATE` et `NUMERIC(14,2)` serait plus sûr.
16. **Colonnes mortes** dans `bourse_parametres` et `bourse_transactions` (anciens taux de courtage, TVA, etc.) : elles ne sont plus lues. `ParametresBourse` en sortie cache les autres champs.
17. **`test.py` est mal nommé et incomplet** : ce n'est pas un test, la docstring cite un autre nom de fichier, et le script ne supprime pas `bourse_dividendes`, `bourse_frais` ni `bourse_titres`. Le renommer `scripts/supprimer_bourse.py`.
18. **Aucun test automatisé.** Les calculs Bourse (PRU, gains, TPCVM) mériteraient des tests `pytest` avec des cas chiffrés comme ceux des points 1 et 2.
19. **La TPCVM est calculée vente par vente** : les pertes ne viennent pas compenser les gains de la même année. C'est une simplification fiscale à documenter ou à corriger selon la règle applicable.
20. Le lanceur `lancer_budget.bat` utilise le Python du système au lieu du venv, contrairement au `.sh`.
21. `README.md` ne contient que deux lignes : il pourrait renvoyer vers ce document.

---

### Priorités suggérées

1. Corriger les calculs Bourse (points 1 à 3), qui faussent directement les chiffres affichés, et les couvrir par des tests.
2. Préremplir les dates Bourse et améliorer l'affichage des erreurs 422 (point 5).
3. Échapper le HTML (point 9).
4. Gérer le renommage des catégories (point 6).
5. Ensuite : pool de connexions, types de colonnes, nettoyage.
