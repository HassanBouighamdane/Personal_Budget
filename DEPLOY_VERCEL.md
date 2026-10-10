# Deploying Carnet on Vercel

This guide puts the app on Vercel's free Hobby plan **next to** the current Render deployment. Both use the same Neon database, so you can try Vercel for a while and switch Render off only once you are happy.

Why Vercel: on Render's free plan the app sleeps after 15 minutes and takes about a minute to wake up. On Vercel it starts on demand in about 1–2 seconds, with no credit card.

Total time: about 20 minutes.

## What is already in the repository

You don't need to write any code. These files are already there:

| File | Role |
|---|---|
| `pyproject.toml` | Tells Vercel where the app is (`backend.app:app`) and which Python packages to install. Render ignores it. |
| `vercel.json` | Keeps tests, the React sources and the docs out of the deployed bundle. |
| `backend/app.py` | Database setup now runs when the server starts, not when the file is imported. It works the same on Render. |
| `backend/tests/test_deploiement.py` | Fails if `pyproject.toml` and `backend/requirements.txt` stop listing the same packages. |

The React frontend is served from the committed `frontend-react/dist/` folder, as on Render. As today, run `npm run build` in `frontend-react/` before pushing frontend changes.

> **When you add a Python package**, add it to both `backend/requirements.txt` (Render) and the `dependencies` list in `pyproject.toml` (Vercel). The test above reminds you if you forget.

---

## Step 1 — Push the changes to GitHub

```bash
git add pyproject.toml vercel.json DEPLOY_VERCEL.md backend/app.py backend/tests/test_deploiement.py README.md DOCUMENTATION.md IDEES.md
git commit -m "Add Vercel deployment"
git push
```

Render redeploys automatically. Nothing changes for it: the startup change was tested with Render's own start command.

## Step 2 — Collect what you need

You need four values, all of which you already use on Render:

1. **Render dashboard** → your service → **Environment**: copy `DATABASE_URL`, `ADMIN_UTILISATEUR` and `ADMIN_MOT_DE_PASSE`.
2. **Neon console** → your project → **Settings** (or the project dashboard): note the **region**, for example "AWS Europe Central 1 (Frankfurt)".

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
   | `DATABASE_URL` | same as on Render |
   | `ADMIN_UTILISATEUR` | same as on Render |
   | `ADMIN_MOT_DE_PASSE` | same as on Render |
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
- [ ] **Lectures → À lire**: an ISBN search fills in the book.
- [ ] **Refresh** on a deep page (for example `…/#/dashboard/annee/2025`): you stay on it.
- [ ] Come back after 15+ minutes without using it: the first page should appear within 1–2 seconds.

**If something goes wrong**, look at the logs: Vercel project → **Logs**. On the free plan they are kept for **1 hour only**, so check right after the problem.

## Optional — Reminders and the weekly and monthly summaries

The app can send deadline reminders every morning, a summary of your week every Monday and a summary of the past month on the 1st, by Telegram or e-mail. `vercel.json` already schedules the daily call (`/api/cron/quotidien` at 07:00 UTC; on the Hobby plan it runs once a day, some time within that hour).

1. Get your Telegram token and chat id, or a Gmail app password: see DOCUMENTATION.md §10, "Configurer l'envoi".
2. In **Settings → Environment Variables**, add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (or the `SMTP_…` variables), plus `CRON_SECRET` with a long random value. Vercel sends this secret with each scheduled call by itself.
3. **Redeploy**, then open **Paramètres → Rappels et résumés**: the three badges should be green. "Aperçu et envoi" shows the weekly or monthly message, and "Envoyer maintenant" sends it to you.

If Render is still running on the same database, only one of the two sends each day's messages.

## Step 7 — Run both for a while

During the trial (a week or two is enough):

- **Same data:** both addresses read and write the same Neon database. Anything you enter on one appears on the other.
- **Separate logins:** you log in on each address separately (each has its own cookie).
- **Both deploy:** `git push` updates Render and Vercel at the same time.
- Don't add a keep-alive monitor on the Vercel address. It isn't needed, and it would use your free allowance for nothing.

## Step 8 — Switch off Render

When the Vercel version has worked well for you:

1. **Render dashboard** → your service → **Settings** → **Suspend Web Service**. The service stops but stays configured, so you can **Resume** it in one click if needed.
2. If you created an UptimeRobot / cron-job.org monitor for Render, delete it.
3. A few weeks later, if all is well: **Settings → Delete Web Service** on Render.
4. Optional cleanup afterwards: `gunicorn` in `backend/requirements.txt` and the Render section of `README.md` are no longer needed.

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
