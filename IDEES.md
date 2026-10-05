# Ideas to improve the app

Suggestions from a review of the app on 2026-10-05. None of them is built yet. Within each group they are ordered by expected payoff.

## Budget

1. **Recurring transactions**: rent, subscriptions and salary are retyped every month. Add a `recurrences` table (amount, category or source, day of month) and a "generate this month's entries" button on the Saisie page.
2. **Search across all history**: Saisie lists one month at a time. Add a text search over description, category and amount across all dates.
3. **CSV / Excel export and import**: there is no way to get data out or to bulk-load a bank statement. Export is quick; import needs a column-mapping step.
4. **Budget alerts at entry time**: the green/yellow/red colouring only appears on the monthly dashboard. Show a warning when saving an expense ("Restaurants: 92 % of budget used").
5. **Per-month budgets**: `categories.budget` is a single value, so changing it rewrites the "planned vs actual" of past months. Store a budget per month, with the current one as the default.
6. **Savings goals by project**: there is one global `objectif_epargne`. Add named goals (travel, emergency fund, car) with a target amount, a deadline and a progress bar.

## Bourse

7. **Price history and portfolio value curve**: `bourse_prix` keeps one price per stock. Save a snapshot at each price update to chart portfolio value over time.
8. **Edit a transaction**: the API only has create and delete for Bourse transactions, dividends, fees and movements. Add `PUT` routes and an edit window.
9. **Dividend yield and allocation targets**: yield per stock (dividends ÷ cost), and a target weight per sector with the current gap.

## Across modules

10. **Net worth view**: one screen combining cumulative budget savings and Bourse wealth, with a curve over time. The data already exists in `resume_global` and the Bourse dashboard.
11. **Installable PWA**: the icons exist, but the React app has no manifest or service worker.
12. **Automatic backup**: a "download everything as JSON" button, or a scheduled dump of the PostgreSQL database.

## Lectures

13. **"Currently reading" and "to read" lists**: the module only records finished books. Add a status field, with a one-click "finished" action that fills the end date.

## Technical debt to do first

Both items are in DOCUMENTATION.md §8.

- **Tests for `rapports.py`**: the dashboard calculations have none, and ideas 1, 5 and 10 touch them.
- **`TEXT` dates and `DOUBLE PRECISION` amounts in the Budget tables**: ideas 2 and 5 are simpler with real `DATE` columns.

## Suggested starting point

Recurring transactions (1), search across history (2) and CSV export (3): small, independent, and they remove daily friction.
