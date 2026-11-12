# Ideas to improve the app

From a review of the code on 2026-10-05, updated on 2026-10-10 and 2026-11-11. Everything below is still open; what has been built is listed under [Done](#done). Within each section, items are ordered by expected payoff. Effort: **S** = an evening, **M** = a few evenings, **L** = needs design first.

## 1. Budget

1. **Recurring transactions** (M): rent, subscriptions and salary are retyped every month. Add a `recurrences` table (amount, category or source, day of month, active) and a "generate this month's entries" button on Saisie. Store the last generated month per recurrence so pressing twice does nothing, and clamp day 31 to the month's last day. Categories marked "Fixe" are the natural first candidates; "Dupliquer" already covers one-off copies.
2. **Savings goals fed by a tag** (S): a goal is filled by hand today ("Mettre de côté" / "Reprendre"). Optionally link a goal to a tag (`#voyage-turquie`): expenses with that tag would show as "already spent" on the goal, so the trip budget is followed without retyping.

## 2. Bourse

5. **Price history** (S to start, M for the chart): `bourse_prix` keeps one price per stock. Insert a row into `bourse_prix_historique(titre, date, cours)` in `maj_prix` and `_actualiser_cours`, so a portfolio-value chart per stock becomes possible. The daily task already calls `_actualiser_cours` every morning, so this fills itself with no extra request (one row per stock and day: `ON CONFLICT (titre, date) DO UPDATE`). Holdings at a past date can already be rebuilt from transactions. Like the net-worth curve, the history only exists from the day it is enabled. Rows written there could also feed the month-end rebuild of the net-worth curve (today it uses `bourse_cours_historique`, typed by hand, then the last transaction price).
6. **Bulk price update** (S, now low value): prices are fetched automatically every morning and when the app opens, so a bulk screen only helps for stocks set to manual or when the sources fail. A smaller version is an "out-of-date prices" list: held stocks whose price is more than 3 days old.

## 5. Backend best practices

- **Numbered migrations** (M): since 2026-11-03, `init_db()` runs once per deployed version, under a lock (`migrations_appliquees`). It still replays *all* the DDL each time, and data migrations are hidden `if` blocks in it (the `modifie_le` columns added on 2026-11-11 are one more). That is how one of them added and dropped a column on every start until the table nearly hit PostgreSQL's 1600-column limit. Numbered SQL files in `backend/migrations/`, each applied once and recorded, make data migrations like the `TEXT` dates safe. `migrations_appliquees` can become that record.
- **`DATE` and `NUMERIC` in the Budget tables** (M): Bourse already uses them. `DOUBLE PRECISION` amounts accumulate rounding errors. Do it as the first real migration; `rapports.py` has tests for the month, week and year views, extend them to the day and global views before.
- **Foreign keys instead of manual cascades** (M): `depenses.categorie`, `revenus.source` and Bourse `titre` reference names without constraints, and renames are cascaded by hand. `FOREIGN KEY ... ON UPDATE CASCADE` on the name would replace the `_verifier_categorie` and `_valider_titre` checks and the rename code. (`budgets_historique` already uses the category id.)
- **Logging** (S): no logging is configured, and Vercel keeps logs for one hour only. Log unhandled exceptions with the route, and the start-up migrations; `cron_journal` shows that a table in the database is a simple way to keep what matters longer.
- **Health check** (S, low value on Vercel): `GET /api/health` doing `SELECT 1`, for an external uptime monitor. The home page already warns when the morning task stops.

## 6. Security

- **Security headers** (S): add `Content-Security-Policy`, `X-Frame-Options: DENY` (or `frame-ancestors`), `X-Content-Type-Options: nosniff` and `Referrer-Policy` with a small middleware.
- **Rate limiter in the database** (S): the login limiter is in memory, reset on restart and per process (DOCUMENTATION.md §8). On Vercel each instance has its own, so it barely limits anything. A small `echecs_login` table fixes both.
- **Input limits** (S): Budget descriptions and names have no max length, and amounts no upper bound (the newer Suivi and goal models have them). Add `max_length` and `le=` to the remaining Pydantic models. Also strip names before validating: a category or source named `"  "` passes `min_length=1` and is saved as `""`.

## 7. Tests and tooling

- **Separate test database** (S): tests run against the `.env` database and only rely on a `ZZTEST` prefix or dates in 1901. Read `TEST_DATABASE_URL` and refuse to run if it is missing or equals `DATABASE_URL`. Tests also don't run `init_db()`, so a database behind the code fails with `UndefinedColumn` until the app has been started once (after the 2026-11-11 changes: start the app locally once before `pytest`).
- **More tests** (S): still missing the global view, auth and the login limiter.
- **Pinned dependencies** (S): `requirements.txt` and `pyproject.toml` have no versions, so a deploy can pull a breaking FastAPI or psycopg release. Pin them (or use `uv` with a lock file). `package-lock.json` already covers the frontend.
- **CI** (S): a GitHub Actions workflow running `pytest` against a Postgres service container, `npm run typecheck`, and `ruff check`.
- **Frontend tests** (S to start): Vitest for `lib/format.ts`, `lib/csv.ts` (date and amount parsing of bank statements), the budget alert of the expense form and `alerteTache` on the home page.
- **Build `dist/` on deploy** (S): committing `dist/` creates a new hashed bundle in every diff and merge conflicts. Vercel can run `npm ci && npm run build` in `frontend-react/` at deploy time (a build command in `vercel.json`); the committed `dist/` then only serves local runs.

## Suggested order

1. The separate test database: it protects the data, and the test suite keeps growing.
2. Price history (5): like the net-worth curve, it only exists from the day it is enabled.
3. Daily friction: recurring transactions (1).
4. Foundations: numbered migrations, then `DATE`/`NUMERIC`, then pinned dependencies and CI.
5. Then the smaller extras: goals fed by a tag (2), out-of-date prices (6).

## Done

**Built on 2026-11-12** (type-checked and built; the database tests were written but not run here)
- **Backfill the net-worth curve**: "Reconstituer les mois passés" on the Évolution card adds one estimated point per month-end, from the first entry to the first real daily point (`estime` in `patrimoine_historique`, dashed on the chart). Everything dated is replayed; each stock is valued at its last transaction price, unless a month-end price is typed from the broker statement ("Cours de fin de mois", table `bourse_cours_historique`). Manual assets count at their current value from their date. Recomputed every morning once enabled.

**Built on 2026-11-11** (type-checked and built; the backend tests below need a database and were written but not run here)
- **Budget alert at entry time** (Saisie): under the category, how much of its monthly budget is already spent (for the month of the expense's date) and the % with the amount typed. After saving, an amber notification from 80 %, red above 100 %. Computed in the browser from `/api/resume`.
- **Savings goals by project** (Suivi → Objectifs): goals with a target and an optional deadline, contributions in and out ("Mettre de côté" / "Reprendre"), progress, monthly amount needed to meet the deadline, late goals on the home page, archive. The money stays in the cash total: "Liquidités libres" shows cash minus what is set aside. Tables `objectifs`, `objectifs_versements`; `routes/objectifs.py`; `tests/test_objectifs.py`.
- **Same month last year** (Dashboard → Mois): an "N−1" badge on income and spending, same "up to the same day" rule for the current month, and last year's amount per category in the "Budget vs Réel" tooltip.
- **Annualised return (XIRR)**: `taux_rendement_annualise()` (bisection), from 90 days of history; shown under "Performance globale" (Bourse) and on the home page.
- **Dividend yield on shares actually held**: `dividendes_par_action()` is shared by the yield and the expected dividends; a partial sale no longer inflates the yield.
- **Net worth curve**: `patrimoine_historique` gets one row a day (morning task, and each read of `/api/patrimoine`); "Évolution" card over 3 months, 1 year or everything, with the Bourse part. The morning task now refreshes prices and records the snapshot even without a message channel.
- **Warn when the daily task stops**: "À traiter" on the home page shows it when the last successful run is more than 36 hours old or the last run failed (`dernier_succes` in `/api/rappels/etat`).
- **One host (Vercel)**: Render removed from the code and docs (`RENDER_GIT_COMMIT`, `gunicorn`); `requirements.txt` is kept for local installs and must match `pyproject.toml`.
- **`modifie_le` columns**: on every data table, kept up to date by the `trg_modifie_le` trigger; existing rows got their `cree_le`.

Built on 2026-10-10 (the three Suivi and reminder items were added the same day), with tests in `backend/tests/` and checked in a browser.

**Features**
- **Home page**: today's remaining budget, the month, the portfolio, the book in progress and streak, the note of the day (also as a popup when the app opens, with "Ne plus l'afficher aujourd'hui" to hide it until the next day on that device), and what needs action. Default page; settings moved to the header on phones.
- **Full backup**: one JSON file with every table (no accounts or sessions), a copy sent on the 1st of each month by Telegram and e-mail, and `scripts/restaurer_sauvegarde.py` to restore it.
- **Stay logged in**: 30-day sessions that renew with use; ordinary sessions also renew, within one day.
- **Year in review**: sent on 1 January, same design as the monthly summary.
- **Installable app**: web manifest and icons, and a service worker (`vite-plugin-pwa`): the app shell opens offline, `/api` is never cached, an "Hors connexion" screen replaces the login page without network, and a new version is offered with a "Recharger" button.
- **Lectures: reading pace**: note today's page on a book in progress to get pages per day, an estimated finish date and a streak of reading days.
- **Lectures: note of the day**, also sent every morning with the reminders. The note and the weekly, monthly and yearly summaries are each sent by Telegram, e-mail or both, chosen in a grid in Paramètres; **lent books** ("Prêtés" tab) and **Markdown export** of notes (one book, or a ZIP with one file per book).
- **Bourse: decision journal** (a note per transaction, with the price change since) and **expected dividends** over 12 months (last dividend per share × shares held today).
- **Suivi: net worth** ("Patrimoine" tab): other assets with manual values, opening balance, emergency-fund runway in months, and a zakat estimate against the nisab with its due date. The Global dashboard card uses the same total.
- **Suivi: financial freedom** (Patrimoine tab): target = annual spending ÷ withdrawal rate (4 % → 25×, adjustable), progress, years of lifestyle covered, estimated date (monthly compounding at an adjustable real return of 4 %), and years gained by spending 500 DH less per month. Averages over the last 12 completed months; housing and vehicle excluded.
- **Price in hours of work** (Saisie): under the amount of an expense, "≈ 3,6 jours de travail" from 2 h up. Hourly rate = average work income (sources ticked "Travail" in Paramètres; Remboursement isn't) over the last 12 completed months ÷ hours per month (191 h by default, the legal 44 h week).
- **Suivi: debts and loans**: money lent or borrowed, partial repayments, "on me doit / je dois" totals. Kept out of the Budget, like Bourse deposits.
- **Suivi: deadlines**: papers, insurance, warranties, with a reminder window and recurrence; a recurring one moves to its next date with ✓.
- **Reminders and weekly summary** by Telegram or e-mail: deadline and repayment reminders each morning, on Monday a summary of the past week and on the 1st a summary of the past month (Budget, Bourse, Lectures, Suivi), as a designed HTML e-mail and a formatted Telegram message. One daily Vercel cron, protected by `CRON_SECRET`; preview and test button in Paramètres. Setup in DOCUMENTATION.md §10.
- **Search across all history** (Saisie): text, exact amount and `#tag`, paginated, with totals of everything found. The search is in the URL.
- **Form date follows the browsed month**: today for the current month, the last day of a past month, the 1st of a future one.
- **CSV export and import** (Paramètres > Import / export): export per period (Excel-friendly). Import with column mapping (amount or debit/credit, type, category, tags), French and English number and date formats, a preview, and duplicates (same date, amount and description) skipped.
- **Tags** on expenses and income (lowercase, up to 10), suggested while typing, clickable to search, and totalled per tag in the dashboard's Global view.
- **Duplicate / quick entry**: "Dupliquer" on each line (inside the edit window on phones), and the last 5 descriptions of the chosen category or source as suggestions, which also fill the amount.
- **Undo after delete** (Saisie): immediate delete with "Annuler" in the notification; the line comes back under its original id, even if its category was deactivated since.
- **Per-month budgets**: `budgets_historique` keeps each category's budget and "fixe" flag from a given month; changes apply from a chosen month (current month by default), with a history window per category. A new category has no budget in past months; a deactivated one keeps its budget in the months before.
- **Bourse: edit** transactions, dividends, fees and movements, with the holdings check on the old and new stock.
- **Bourse: cash warning** in the buy form when it would take available cash below zero.
- **Bourse: annual tax summary** ("Fiscalité" tab): gains, losses, net result, TPCVM withheld and at the configured rate, dividends, detail per stock.
- **Bourse: dividend yield** per position (12 months, on cost and on market value) and **sector targets** with the gap and the amount to buy or trim.
- **Lectures: "À lire" tab**: to-read list and books in progress; "Terminé" moves the book to the journal with its notes.
- **Lectures: notes and quotes** per book (page, note or quote), also while reading.
- **Lectures: ISBN lookup** from Open Library: removed on 2026-10-10 at the user's request. Covers already fetched are kept and still shown; the `isbn` columns stay in the database but are no longer filled.
- **URL navigation**: tab, view and period in the address; refresh keeps the page, back/forward work, views can be bookmarked.
- **Startup in `lifespan`**: `init_db()` and the pool close moved from import time / `@app.on_event` into FastAPI's lifespan, so importing `app` no longer touches the database (needed for Vercel's build).
- **Vercel hosting**: `pyproject.toml`, `vercel.json` and DEPLOY_VERCEL.md (Render was switched off later).
- **Migrations once per version** (2026-11-03): `migrations_a_faire()` runs `init_db()` only on the first start of a deployed version (`VERSION_DEPLOYEE`, the Git commit from Vercel), under `pg_advisory_xact_lock`. This fixed the 500s when several Vercel instances started at once. A test checks that a start no longer uses up PostgreSQL column numbers.
- **Daily task log** (2026-10-12): each call of `/api/cron/quotidien` is saved in `cron_journal` (last 30) with what was sent and on which channels, or the error, and the last runs are shown in Paramètres.
- **Old frontend removed**: `frontend/` (HTML/JS, no longer maintained) is deleted; the server only serves `frontend-react/dist/` and prints a warning if it is missing.

**Bugs**
- **B1. Deleting a Bourse buy left negative holdings:** the deletion is refused when later sales depend on that buy (`_historique_negatif`).
- **B2. Renaming to an existing name returned a 500:** categories, sources and Bourse stock codes now return a 409 with a readable message, like Lectures genres already did.
- **B3. Expenses accepted any category:** a new expense must use an active category; an edited expense may keep its current one even if deactivated since.
- **B4. "Today" was the server's date:** `config.aujourdhui()` uses `Africa/Casablanca` (override with the `FUSEAU` variable); used by the reports and the Lectures bilan. `tzdata` added to `requirements.txt` for Windows.

**Dashboard figures**
- **Fixed costs:** a "Fixe" checkbox on categories (Paramètres). The month-end projection counts fixed categories at their budget (or actual if higher) and extrapolates only variable spending; the daily and weekly budgets use variable categories only. Existing categories start as not fixed: tick Loyer and Factures once.
- **Comparisons over the same length:** for the current month or week, the ▲/▼ badges compare with the previous period up to the same day, with the full total in the tooltip or help text.
- **Year and global statistics on finished months:** average, best/worst month and "Objectif atteint" leave out the current month; the annual budget per category is scaled to the months elapsed (`budget_a_date`).
- **Bourse stock codes checked:** a transaction needs a code from Paramètres > Titres (or one already in the journal), and a dividend needs a buy of that stock on or before its date. The stock field shows the company name, or a hint when the code is unknown.
