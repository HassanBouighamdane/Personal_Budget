# 💰 Mon Budget

Application web personnelle pour gérer et suivre son budget au quotidien, avec un module de suivi de portefeuille à la Bourse de Casablanca. Tous les montants sont en dirhams (DH).

## Fonctionnalités

**Budget**
- Saisie rapide des dépenses (catégorie, montant, description, moyen de paiement) et des revenus (source, montant)
- Tableaux de bord **Jour / Semaine / Mois / Année / Global** avec graphiques :
  - budget prévu comparé au réel, par catégorie
  - dépenses cumulées et projection en fin de mois
  - évolution sur 6 mois et comparaison avec la période précédente
  - épargne, taux d'épargne et suivi de l'objectif mensuel
  - grille thermique catégories × mois (vue annuelle)
- Catégories et budgets mensuels, sources de revenus et types de paiement configurables

**Bourse**
- Journal des achats et ventes (actions, obligations, OPCVM, IPO), avec autocomplétion des titres cotés à la BVC
- Positions : PRU (prix de revient unitaire), valeur de marché, plus-value latente
- Gains réalisés, avec calcul de la TPCVM (taxe sur les plus-values de cession)
- Dividendes nets et frais de compte (y compris les droits de garde, saisis manuellement)
- Apports et retraits entre la banque et le compte Bourse : espèces disponibles, patrimoine total et performance globale (gains réinvestis inclus)
- Tableau de bord global, par mois ou par année

**Autres**
- Connexion sécurisée : mot de passe haché avec PBKDF2, session dans un cookie HttpOnly
- Thème clair ou sombre, interface adaptée au mobile

## Stack

| Couche | Technologies |
|---|---|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Base de données | PostgreSQL (`psycopg` v3) |
| Frontend | HTML, CSS, JavaScript vanilla, Chart.js |

Le backend sert aussi le frontend : un seul serveur suffit.

## Installation

### 1. Cloner et installer les dépendances

```bash
git clone <url-du-repo>
cd Personal_Budget
python -m venv .venv
# Windows : .venv\Scripts\activate    |    Linux/Mac : source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. Configurer `backend/.env`

```env
DATABASE_URL=postgresql://user:motdepasse@hote:5432/nom_base
ADMIN_UTILISATEUR=mon_nom
ADMIN_MOT_DE_PASSE=un_mot_de_passe_solide
PORT=8500
COOKIE_SECURE=false      # true en production (HTTPS)
```

Au premier démarrage, l'application crée automatiquement les tables, les catégories par défaut et le compte administrateur défini dans `.env`.

### 3. Lancer

```bash
python backend/app.py
```

Sous Windows, tu peux aussi double-cliquer sur `lancer_budget.bat`. Sous Linux, lance `./lancer_budget.sh`.

- Application : http://localhost:8500
- Documentation de l'API (Swagger) : http://localhost:8500/docs

## Déploiement

L'application peut être hébergée sur une plateforme comme Render, avec une base PostgreSQL managée. Commande de démarrage :

```bash
cd backend && gunicorn app:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

Pense à définir `COOKIE_SECURE=true` quand le site est servi en HTTPS.

## Structure du projet

```
backend/
  app.py            point d'entrée FastAPI
  config.py         variables d'environnement
  database.py       connexion PostgreSQL et création du schéma
  securite.py       mots de passe et sessions
  schemas.py        modèles Pydantic
  routes/           auth, configuration, transactions, rapports, bourse
frontend/
  index.html        interface (page unique)
  js/app.js         logique budget et dashboards
  js/bourse.js      module Bourse
  css/style.css     styles et thèmes
```

## Documentation

Le fichier [DOCUMENTATION.md](DOCUMENTATION.md) décrit en détail l'architecture, chaque fichier, le schéma de la base, les routes de l'API et les formules de calcul. Il liste aussi les problèmes connus.
