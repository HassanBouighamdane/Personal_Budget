# Ideas to improve the app

From a review of the code on 2026-10-05, updated on 2026-10-10. Everything below is still open; what has been built is listed under [Done](#done). Within each section, items are ordered by expected payoff. Effort: **S** = an evening, **M** = a few evenings, **L** = needs design first.

## 1. Budget

1. **Recurring transactions** (M): rent, subscriptions and salary are retyped every month. Add a `recurrences` table (amount, category or source, day of month, active) and a "generate this month's entries" button on Saisie. Store the last generated month per recurrence so pressing twice does nothing, and clamp day 31 to the month's last day. Categories marked "Fixe" are the natural first candidates; "Dupliquer" already covers one-off copies.
2. **Budget alert at entry time** (S): show "Restaurants: 92 % of budget used" when saving an expense. Can be done in the frontend from the month's `/resume` data, which is usually already cached.
3. **Savings goals by project** (M): named goals (travel, emergency fund, car) with target, deadline and progress bar. This is new, not a replacement of `objectif_epargne` (which is a monthly target). Decide first how money is assigned to a goal: manual contributions are the simplest. Tags could feed the "spent" side.
4. **Same month last year** (S): the month view compares with the previous month only (up to the same day for the current month). Add the same month of the previous year, which is more meaningful for seasonal spending (Ramadan, summer, back-to-school).

## 2. Bourse

5. **Price history** (S to start, M for the chart): `bourse_prix` keeps one price per stock. Insert a row into `bourse_prix_historique(titre, date, cours)` in `maj_prix` and `_actualiser_cours` **now**, so there is history when the portfolio-value chart is built. Holdings at a past date can already be rebuilt from transactions.
6. **Bulk price update** (S): one screen listing every held stock with its price field, saved in one request, instead of one update per stock.
7. **Annualised return (XIRR)** (M): `performance_globale_pct` ignores *when* money was deposited. Deposits and withdrawals are dated, so a money-weighted annual return is computable and is the honest number to compare with a savings account or the MASI.
8. **Dividend yield on shares actually held** (S): the yield divides the last 12 months of dividends by the cost of the position held *today*. After a partial sale it is inflated (dividends were paid on more shares). Rebuild the quantity held at each dividend date from the transactions and use dividend per share × current quantity.

## 3. Across modules

9. **Full backup** (S): the CSV export covers the Budget only. Add `GET /api/export` returning every table as JSON (Bourse and Lectures included), and ideally a scheduled `pg_dump` to another place.
10. **Net worth curve** (M): net worth now includes other assets, debts and an opening balance (Carnet → Patrimoine), but only as today's figure. A curve over time needs the price history (idea 5) for the Bourse part, and a history of the manual asset values.
11. **Installable app** (S): add a web manifest (icons already exist) so it installs on the phone's home screen. Skip the service worker: offline use adds little with 24 h sessions, and caching causes stale builds after each `dist/` update.

## 5. Backend best practices

- **Real migrations** (M): `init_db()` runs all the DDL on every start (every cold start on Vercel), with no record of what ran. A `schema_version` table plus numbered SQL files in `backend/migrations/` (applied in order, once) is enough without an ORM, and makes data migrations (like the `TEXT` dates) safe.
- **`DATE` and `NUMERIC` in the Budget tables** (M): Bourse already uses them. `DOUBLE PRECISION` amounts accumulate rounding errors. Do it as the first real migration; `rapports.py` now has its first tests, extend them to the day and global views before.
- **Foreign keys instead of manual cascades** (M): `depenses.categorie`, `revenus.source` and Bourse `titre` reference names without constraints, and renames are cascaded by hand. `FOREIGN KEY ... ON UPDATE CASCADE` on the name would replace the `_verifier_categorie` and `_valider_titre` checks and the rename code. (`budgets_historique` already uses the category id.)
- **Health check** (S): `GET /api/health` doing `SELECT 1`, for Render's health check and uptime monitoring.
- **Logging** (S): no logging is configured; a 500 on Render leaves only a stack trace. Log unhandled exceptions with the route, and the start-up migrations.
- **`updated_at` columns** (S): only `depenses` and `revenus` have `cree_le`. A modification date on every table helps debugging and any future sync or export.

## 6. Security

- **Security headers** (S): add `Content-Security-Policy`, `X-Frame-Options: DENY` (or `frame-ancestors`), `X-Content-Type-Options: nosniff` and `Referrer-Policy` with a small middleware.
- **Sliding sessions** (S): sessions expire 24 h after login even during use. Extend the expiry on activity (e.g. when less than half remains), and maybe offer a longer "remember me" on the phone.
- **Rate limiter in the database** (S): the login limiter is in memory, reset on restart and per process (DOCUMENTATION.md §8). A small `echecs_login` table fixes both.
- **Input limits** (S): descriptions and names have no max length, and amounts no upper bound. Add `max_length` and `le=` to the Pydantic models. Also strip names before validating: a category or source named `"  "` passes `min_length=1` and is saved as `""`.

## 7. Tests and tooling

- **Separate test database** (S): tests run against the `.env` database and only rely on a `ZZTEST` prefix. Read `TEST_DATABASE_URL` and refuse to run if it is missing or equals `DATABASE_URL`. Tests also don't run `init_db()`, so a database behind the code fails with `UndefinedColumn` until the app has been started once.
- **More tests for `rapports.py`** (S): `test_rapports.py` and `test_budget.py` cover the projection, fixed costs, comparisons, year statistics and per-month budgets. Still missing: the global view, and outside reports, auth and the login limiter.
- **Pinned dependencies** (S): `requirements.txt` has no versions, so a deploy can pull a breaking FastAPI or psycopg release. Pin them (or use `uv` with a lock file). `package-lock.json` already covers the frontend.
- **CI** (S): a GitHub Actions workflow running `pytest` against a Postgres service container, `npm run typecheck`, and `ruff check`.
- **Frontend tests** (S to start): Vitest for `lib/format.ts`, `lib/csv.ts` (date and amount parsing of bank statements) and the filtering/total logic in `Transactions.tsx`, which is easy to break.
- **Build `dist/` on deploy** (S): committing `dist/` creates a new hashed bundle in every diff and merge conflicts. Render can run `npm ci && npm run build` at deploy time; keep the commit only if the Python-only server matters.

## Suggested order

1. Full backup (9) and the separate test database: they protect the data.
2. Start the price history (5): the history only exists from the day it is enabled.
3. Daily friction: budget alert (2), recurring transactions (1).
4. Foundations: more tests for `rapports.py`, migrations, then `DATE`/`NUMERIC`.
5. Then the larger features: net worth curve (10), XIRR (7), savings goals (3).

## Done

Built on 2026-10-10 (the three Carnet and reminder items were added the same day), with tests in `backend/tests/` and checked in a browser.

**Features**
- **Lectures: reading pace**: note today's page on a book in progress to get pages per day, an estimated finish date and a streak of reading days.
- **Lectures: note of the day**, **lent books** ("Prêtés" tab) and **Markdown export** of notes (one book, or a ZIP with one file per book).
- **Bourse: decision journal** (a note per transaction, with the price change since) and **expected dividends** over 12 months (last dividend per share × shares held today).
- **Carnet: net worth** ("Patrimoine" tab): other assets with manual values, opening balance, emergency-fund runway in months, and a zakat estimate against the nisab with its due date. The Global dashboard card uses the same total.
- **Carnet: debts and loans**: money lent or borrowed, partial repayments, "on me doit / je dois" totals. Kept out of the Budget, like Bourse deposits.
- **Carnet: deadlines**: papers, insurance, warranties, with a reminder window and recurrence; a recurring one moves to its next date with ✓.
- **Reminders and weekly summary** by Telegram or e-mail: deadline and repayment reminders each morning, on Monday a summary of the past week and on the 1st a summary of the past month (Budget, Bourse, Lectures, Carnet), as a designed HTML e-mail and a formatted Telegram message. One daily Vercel cron, protected by `CRON_SECRET`; preview and test button in Paramètres. Setup in DOCUMENTATION.md §10.
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
- **Lectures: ISBN lookup** from Open Library (title, author, pages, cover, checksum validated), on both forms; covers shown in the lists.
- **URL navigation**: tab, view and period in the address; refresh keeps the page, back/forward work, views can be bookmarked.
- **Startup in `lifespan`**: `init_db()` and the pool close moved from import time / `@app.on_event` into FastAPI's lifespan, so importing `app` no longer touches the database (needed for Vercel's build).
- **Vercel hosting**: `pyproject.toml`, `vercel.json` and DEPLOY_VERCEL.md, alongside Render.
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
