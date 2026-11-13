# Ideas to improve the app

From a review of the code on 2026-10-05, updated on 2026-10-10, 2026-11-11 and 2026-11-12 (full re-read after the fourth batch, with new high-payoff ideas; the balance check, Telegram entry, provisions, alerts and Lectures references were built the same day, fifth batch). Everything below is still open; what has been built is listed under [Done](#done). Within each section, items are ordered by expected payoff. Effort: **S** = an evening, **M** = a few evenings, **L** = needs design first. Ideas marked ★ are the ones with the biggest payoff.

### Where the app stands

Almost everything is built on one number: **liquidités** = opening balance + cumulative Budget savings − Bourse deposits − money set aside − loans. Net worth, "Liquidités libres", runway, financial freedom, zakat and the net-worth curve all depend on it. That number is only as good as the entries. Since the fifth batch:
- it can be checked against the real bank balance ("Pointer le solde"), and the gap booked;
- an expense can be sent to the Telegram bot in a few seconds, without opening the app;
- deadlines with an amount are prepared month by month (provisions), and unusual spending shows on the home page.

What is left: the bank import still needs every line categorised. Recurring entries, the cash-flow forecast and the daily price history were built on 2026-11-12 (sixth batch).

## 1. Trust in the numbers

2. ★ **More frequent backup** (S): the full backup is sent on the 1st of the month only, so up to 30 days of entries can be lost, and Neon's free plan only keeps a short restore window. Send it every Monday with the weekly summary, on Telegram only (`sendDocument` accepts 50 MB), and keep the monthly e-mail copy. Add a line in Paramètres, "dernière sauvegarde envoyée le …", from `cron_journal`. **Payoff:** worst-case data loss drops from a month to a week, for a few lines in `routes/rappels.py`.

## 2. Budget: capture with less effort

5. **Categorisation rules for the CSV import** (S): bank statements have no category column, so each imported line is categorised by hand. Suggest a category in the import preview:
   - first from user rules, stored in `regles_import(motif, categorie, tags)`, for example "contient MARJANE → Courses";
   - otherwise from the category most often used for the same normalised description (digits, dates and card references removed).

   A line categorised by hand in the preview can be saved as a rule. **Payoff:** importing a month of statements takes one minute instead of thirty, so the import becomes a real way to catch the entries missed (with the balance check). The category guess of the Telegram bot (`deviner_categorie` in `routes/telegram.py`) can be reused.
6. **Offline entries** (M): the installed app opens without a network, but saving fails. Queue new expenses in IndexedDB, mark them "en attente", and send them when the connection returns (`online` event, plus a retry when the app opens). Use the existing duplicate rule (same date, amount and description) to avoid double sends. **Payoff:** nothing is lost when paying in a shop or a car park without signal. Less needed now that Telegram entry exists: Telegram keeps messages typed offline and sends them later.

## 3. Looking ahead

Nothing left here: the cash-flow forecast is built (see [Done](#done)).

## 4. Bourse

Nothing left here: price history, out-of-date prices and the MASI comparison are built (see [Done](#done)).

## 5. Backend best practices

- **Numbered migrations** (M): since 2026-11-03, `init_db()` runs once per deployed version, under a lock (`migrations_appliquees`). It still replays *all* the DDL each time, and data migrations are hidden `if` blocks in it (the `modifie_le` columns added on 2026-11-11 are one more). That is how one of them added and dropped a column on every start until the table nearly hit PostgreSQL's 1600-column limit. Numbered SQL files in `backend/migrations/`, each applied once and recorded, make data migrations like the `TEXT` dates safe. `migrations_appliquees` can become that record.
- **`DATE` and `NUMERIC` in the Budget tables** (M): Bourse already uses them. `DOUBLE PRECISION` amounts accumulate rounding errors. Do it as the first real migration; `rapports.py` has tests for the month, week and year views, extend them to the day and global views before.
- **Logging** (S): no logging is configured, and Vercel keeps logs for one hour only. Log unhandled exceptions with the route, and the start-up migrations; `cron_journal` shows that a table in the database is a simple way to keep what matters longer.
- **Health check** (S, low value on Vercel): `GET /api/health` doing `SELECT 1`, for an external uptime monitor. The home page already warns when the morning task stops.

## 6. Tests and tooling

- **More tests** (S): the login limiter, security headers and input limits are now covered (`test_securite.py`). Still missing: the global view (`calculer_resume_global`), and the login and logout routes themselves.
- **Pinned dependencies** (S): `requirements.txt` and `pyproject.toml` have no versions, so a deploy can pull a breaking FastAPI or psycopg release. Pin them (or use `uv` with a lock file). `package-lock.json` already covers the frontend.
- **CI, next steps** (S): add `ruff check` to the workflow, and make the `master` branch refuse a merge when the tests fail (needs a public repository or a paid GitHub plan for a private one).
- **Frontend tests** (S to start): Vitest for `lib/format.ts`, `lib/csv.ts` (date and amount parsing of bank statements), the budget alert of the expense form and `alerteTache` on the home page.

## Suggested order

1. **Protect the data first** (one evening): the weekly backup (2). The separate test database and CI are done.
2. **Capture**: import rules (5). With Telegram entry and recurring transactions, they remove most of the typing.
3. **Foundations**: pinned dependencies (a new Starlette already broke the CI tests once), numbered migrations, then `DATE`/`NUMERIC`.
4. Then the smaller extra: offline entries (6).

## Done

**Built on 2026-11-13, tests and preview**
- **Separate test database**: the database tests run on `TEST_DATABASE_URL` only (a Neon branch), never on `DATABASE_URL` (`tests/conftest.py`). Without it they are skipped, and any test that still opens a connection is skipped too; equal to `DATABASE_URL`, pytest refuses to start. The test database is brought up to the code (`init_db()`) once per session. Test dependencies in `backend/requirements-tests.txt` (`httpx2` for the test client of recent Starlette).
- **CI**: `.github/workflows/tests.yml` runs on each push to `preview` and each Pull Request to `master`: frontend type-check and build, then `pytest` with the `DATABASE_URL_TESTS` secret. Vercel builds `preview` as a Preview deployment on its own Neon branch.
- The first full run against a database found a real bug: choosing the category of a Telegram expense with the buttons lost the expense (`RETURNING` gave the new value, `NULL`). Fixed; the other failures were tests out of date with the code.

**Built on 2026-11-12, sixth batch** (type-checked and built; the backend suite, new tests included, passed against a throwaway local PostgreSQL, except two older failures in `test_patrimoine` and `test_telegram`)
- **Price history**: `bourse_prix_historique(titre, date, cours, manuel)` gets the closing price of each held stock once per trading day, from a second cron at 20:00 Morocco time (`/api/cron/cours-du-soir`); no row on weekends and public holidays (fixed ones in `FERIES_FIXES`, religious ones entered in Bourse → Paramètres). "Valeur du portefeuille" chart in Bourse → Positions (market value vs cost, or one stock's price). The month-end rebuild of the net-worth curve uses these prices before falling back to the last transaction price.
- **Recurring transactions**: table `recurrences`, `routes/recurrences.py`. "Récurrences" button in Saisie (create, edit, pause, delete, suggestions from the last 3 months). "Récurrences à ajouter" card in Saisie (amount editable for the month, skip a month); `auto` ones are added by the morning task on their day and mentioned in the morning message. `dernier_mois` plus a row lock make a second run do nothing; day 31 is clamped; missed months are caught up in order.
- **Import of past stock prices**: the daily file of Market Data → Cours (Bourse de Casablanca, up to 3 years, .xlsx read in the browser without a library) fills the price history before the evening closes started. Evening closes are kept; a file more than 10 % off a recorded close is refused. The portfolio chart, the rebuilt net-worth month-ends and the MASI comparison use them.
- **Compare with the MASI**: the evening task also records MASRN, MS20RN (dividends reinvested, net), MASI, MSI20 and MASIMS (`indices_historique`). "Comparaison avec l'indice" card on the Bourse dashboard: the same deposits and withdrawals placed in the chosen index (MASRN by default), value, gap in DH and annual return side by side, with both curves. Past index values are imported from a CSV file (Bourse → Paramètres), checked against the recorded ones to refuse another index's file.
- **Out-of-date prices**: held stocks with no closing price recorded for 2+ trading days (automatic), or a manual price older than 5 trading days, counted in trading days (no false alerts on Mondays or after holidays). Shown in "À traiter", as an amber badge in Positions and in the Monday message. It is the only visible sign that the evening task or the price source has stopped.
- **Cash-flow forecast**: `routes/previsions.py`, "Prévisions" card in Suivi → Patrimoine (3, 6 or 12 months): month-end cash from recurrences, the median income and average spending of the last 6 months, deadlines with an amount, debts due and goals' monthly amounts (as reserved money, "libres"), with an uncertainty band and an adjustable floor. Warnings in the card and in "À traiter".

**Built on 2026-11-12, fifth batch** (type-checked and built; the parser tests of the Telegram bot pass, the database tests were written but not run here)
- **Balance check** ("Pointer le solde", Suivi → Patrimoine): the real balance, account by account, compared with the computed liquidités of the day; the gap can be booked as an expense or income of the day (tag `pointage`). Days without any expense since the last check are listed. Table `rapprochements`; "À traiter" and the Monday message invite to check after 30 days (or if never done).
- **Quick entry from Telegram**: `45 café`, `café 45 hier`, `1200 courses #tag`, `+8000 salaire`, `?`, `solde`, `solde 12500` sent to the bot. Category guessed from the history and the category names, otherwise asked with buttons; reply with "Annuler" and "Catégorie" buttons. Webhook `POST /api/telegram/webhook` (secret derived from the bot token), switched on from Paramètres; `routes/telegram.py`, table `telegram_messages`.
- **Provisions for irregular expenses**: a deadline can have an amount and a savings goal for the same amount and date (`echeances.montant`, `objectif_id`). Reporting a recurring deadline archives the goal and opens the next one. "À mettre de côté ce mois-ci" on Échéances and in the month dashboard.
- **Unusual-spending alerts** (`routes/alertes.py`): category well above its 6-month average, price increase of a fixed recurring amount, likely duplicate. On the home page (with "Ignorer", table `alertes_ignorees`) and in the Monday morning message.
- **Lectures references**: `lectures_livres.genre` and `lectures_a_lire.genre` reference `lectures_genres.nom` (`ON UPDATE CASCADE`); an empty genre is NULL. Renaming a genre now also renames the books to read (it only renamed the books read). Old backups with empty names are restored as NULL.

**Built on 2026-11-12, fourth batch** (type-checked and built; the database tests were written but not run here)
- **Savings goals fed by a tag**: a goal can follow a tag (`tag`, `tag_depuis` on `objectifs`). Tagged expenses from that date, minus tagged income, are taken from the money set aside: a second bar shows spent vs set aside, "Liquidités libres" subtracts only what is still reserved, and overspending shows in red and on the home page. The goal's "Versements" window lists the tagged operations.

**Built on 2026-11-12, third batch** (the build script was run locally; the first Vercel deployment confirms it there)
- **Build `dist/` on deploy**: `dist/` is no longer committed. Vercel runs `backend/construire_frontend.py` (`npm ci --include=dev`, `npm run build`) through `[tool.vercel.scripts] build` in `pyproject.toml`; `lancer_budget` runs it when `dist/` is missing.

**Built on 2026-11-12, second batch** (backend only; the database tests were written but not run here)
- **Foreign keys instead of manual cascades**: `depenses.categorie`, `revenus.source` and the Bourse `titre` columns reference their parent name with `ON UPDATE CASCADE` (`CLES_ETRANGERES` in `database.py`). The rename code and `_valider_titre` are gone; `_verifier_categorie` only keeps the "active category" rule. Orphan names were added as retired parents before the constraints. A free revenue source ("Autre…") becomes a retired source; an empty one is stored as NULL.
- **Security headers**: CSP (inline theme script allowed by its sha256), `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, from a middleware in `app.py`.
- **Rate limiter in the database**: `echecs_login` table, shared by every Vercel instance.
- **Input limits**: names stripped then 1–100 characters, descriptions 500, amounts up to 10 billion, passwords 200, on every Pydantic input model.

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
