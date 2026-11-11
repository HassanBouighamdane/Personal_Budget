# Deploying Carnet on Vercel

Carnet runs on Vercel's free Hobby plan, with a PostgreSQL database on Neon. The app starts on demand in about 1–2 seconds and needs no credit card. This guide sets it up from scratch, or again on a new Vercel account.

Total time: about 20 minutes.

## What is already in the repository

You don't need to write any code. These files are already there:

| File | Role |
|---|---|
| `pyproject.toml` | Tells Vercel where the app is (`backend.app:app`) and which Python packages to install. |
| `vercel.json` | Schedules the morning task (`/api/cron/quotidien`) and keeps tests, the React sources and the docs out of the deployed bundle. |
| `backend/app.py` | Database setup runs when the server starts, once per deployed version, not when the file is imported. |
| `backend/tests/test_deploiement.py` | Fails if `pyproject.toml` and `backend/requirements.txt` stop listing the same packages. |

The React frontend is served from the committed `frontend-react/dist/` folder. Run `npm run build` in `frontend-react/` and commit `dist/` before pushing frontend changes.

> **When you add a Python package**, add it to both `backend/requirements.txt` (local install and tests) and the `dependencies` list in `pyproject.toml` (Vercel). The test above reminds you if you forget.

---

## Step 1 — Push the code to GitHub

Vercel deploys from a GitHub repository: push the project (with `frontend-react/dist/` built and committed) to a repository on your account.

## Step 2 — Collect what you need

1. **Neon console** → your project → **Connection Details**: copy the connection string → `DATABASE_URL`. It is the same value as in your local `backend/.env` if you use the same database.
2. `ADMIN_UTILISATEUR` and `ADMIN_MOT_DE_PASSE`: the account created on the very first start, when the database has no user yet. With an existing database, your usual login is kept and these two values are not used.
3. **Neon console** → your project → **Settings** (or the project dashboard): note the **region**, for example "AWS Europe Central 1 (Frankfurt)".

Keep them in a note for step 4.

## Step 3 — Create the Vercel account

1. Go to <https://vercel.com/signup>.
2. Choose **Hobby** (free, personal use).
3. Sign up with **Continue with GitHub**. This lets Vercel see your repositories.

## Step 4 — Import the project

1. On the Vercel dashboard: **Add New… → Project**.
2. Find `Personal_Budget` and click **Import**. If it's not listed, click **Adjust GitHub App Permissions** and give Vercel access to that repository.
3. On the configuration screen:
   - **Framework Preset**: Vercel should detect **FastAPI** by itself. If it shows "Other", leave it; the `pyproject.toml` file is enough.
   - **Root Directory**: leave `./`, the repository root.
   - **Build and Output Settings**: leave everything empty or default. There is nothing to build: the frontend is already built in `frontend-react/dist/`.
4. Open **Environment Variables** and add:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string |
   | `ADMIN_UTILISATEUR` | your login name |
   | `ADMIN_MOT_DE_PASSE` | a strong password (change it later in Paramètres) |
   | `COOKIE_SECURE` | `true` |

   Don't add `PORT`: Vercel doesn't use it.
5. Click **Deploy** and wait for the build, about 1–2 minutes.

At the end you get an address like `https://personal-budget-xxxx.vercel.app`. Don't use it seriously yet: first set the region (step 5).

## Step 5 — Put the app next to the database (important)

By default Vercel runs the app in Washington DC (`iad1`). If your Neon database is in Europe, every query would cross the Atlantic, and with several queries per screen pages would feel slow.

1. In the Vercel project: **Settings → Functions → Function Regions**.
2. Select the single region matching your Neon region (the free plan allows exactly one):

   | Neon region | Vercel region |
   |---|---|
   | AWS Europe Central 1 (Frankfurt) | `fra1` Frankfurt |
   | Azure Germany West Central | `fra1` Frankfurt |
   | AWS Europe West 2 (London) | `lhr1` London |
   | AWS US East 1 (N. Virginia) | `iad1` Washington DC |
   | AWS US East 2 (Ohio) | `cle1` Cleveland |
   | AWS US West 2 (Oregon) | `pdx1` Portland |
   | AWS Asia Pacific Southeast 1 (Singapore) | `sin1` Singapore |
   | AWS Asia Pacific Southeast 2 (Sydney) | `syd1` Sydney |
   | AWS South America East 1 (São Paulo) | `gru1` São Paulo |

3. **Save**, then redeploy so the new region is used: **Deployments** → the latest deployment → **⋯** → **Redeploy**.

Settings and environment variables only apply to new deployments. Redeploy each time you change one.

## Step 6 — Test

Open the Vercel address on your computer **and your phone**, then check:

- [ ] The login page appears, and you can log in with your usual account.
- [ ] **Saisie**: your data is there. Add a test expense (for example "ZZTEST"), then delete it.
- [ ] **Dashboard**: the Month, Year and Global views load.
- [ ] **Bourse → Positions → "Actualiser les cours"**. If the message says the sources are unreachable, the stock-exchange site blocks Vercel's servers. The last known prices stay, and you can still type a price by hand.
- [ ] **Suivi → Patrimoine**: the "Évolution" card shows today's first point.
- [ ] **Refresh** on a deep page (for example `…/#/dashboard/annee/2025`): you stay on it.
- [ ] Come back after 15+ minutes without using it: the first page should appear within 1–2 seconds.

**If something goes wrong**, look at the logs: Vercel project → **Logs**. On the free plan they are kept for **1 hour only**, so check right after the problem.

## Optional — Reminders and the weekly and monthly summaries

The app can send deadline reminders every morning, a summary of your week every Monday and a summary of the past month on the 1st, by Telegram or e-mail. `vercel.json` already schedules the daily call (`/api/cron/quotidien` at 07:00 UTC; on the Hobby plan it runs once a day, some time within that hour).

1. Get your Telegram token and chat id, or a Gmail app password: see DOCUMENTATION.md §10, "Configurer l'envoi".
2. In **Settings → Environment Variables**, add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (or the `SMTP_…` variables), plus `CRON_SECRET` with a long random value. Vercel sends this secret with each scheduled call by itself.
3. **Redeploy**, then open **Paramètres → Rappels et résumés**: the three badges should be green. "Aperçu et envoi" shows the weekly or monthly message, and "Envoyer maintenant" sends it to you.

Even without Telegram or e-mail, keep `CRON_SECRET`: the morning task also refreshes the stock prices and records the day's net worth for its chart. If it stops running, the home page says so under "À traiter".

## Step 7 — Deploying changes

- `git push` to the main branch redeploys automatically. For frontend changes, run `npm run build` in `frontend-react/` and commit `dist/` first.
- The first start of a new version runs the database migrations once (`migrations_appliquees`), so the first page after a deploy can take a few seconds more.
- Don't add a keep-alive monitor on the Vercel address. It isn't needed, and it would use your free allowance for nothing.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Build fails with "No entrypoint found" or "No FastAPI app" | `pyproject.toml` must be at the repository root, and **Root Directory** must be `./` (Settings → Build and Deployment). |
| Every page shows an error, logs say `DATABASE_URL manquant` | The variable is missing for **Production**. Add it (Settings → Environment Variables), then **Redeploy**. |
| Login seems to work but you're sent back to the login page | Check `COOKIE_SECURE` is exactly `true`, and that you use the `https://` address. |
| Pages are slow (several seconds each, not just the first) | The function region doesn't match Neon's region: redo step 5. |
| Errors mentioning "too many connections" | Unlikely for personal use. In Neon, copy the **pooled** connection string (host containing `-pooler`) into `DATABASE_URL` and redeploy. If you then see errors about "prepared statements", go back to the normal string. |
| A feature stops working for the rest of the month | A free-plan limit was exceeded, and Vercel pauses it for 30 days. Check **Usage** in the dashboard. With personal use this shouldn't happen (the limits are around 1 million requests and 4 CPU-hours a month). |
| You changed a variable but nothing changed | Variables only apply to new deployments: **Redeploy**. |

## Free plan limits (Hobby)

| Resource | Included per month |
|---|---|
| Function invocations | 1,000,000 |
| Active CPU | 4 hours |
| Data transfer | 100 GB |
| Function regions | 1 |
| Log retention | 1 hour |

Personal, non-commercial use only. Details: <https://vercel.com/docs/plans/hobby>.

## Reference

- Deploying FastAPI on Vercel: <https://vercel.com/docs/frameworks/backend/fastapi>
- Python runtime: <https://vercel.com/docs/functions/runtimes/python>
- Function regions: <https://vercel.com/docs/functions/configuring-functions/region>
