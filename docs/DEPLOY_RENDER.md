# HeatSafe AI on Render: free temporary demonstration

This is a **temporary presentation deployment**, not an operational warning service. The root `render.yaml` defines one free web service (FastAPI plus the built dashboard at the same HTTPS origin) and one free Render Postgres database with PostGIS. It defines **no paid scheduler, cron job, or public dispatch gateway**. The optional [free GitHub Actions preload](PRELOAD_FREE_SCHEDULE.md) fetches forecast data off Render every six hours and uploads it through a dedicated restricted token; with that token configured, visitor-triggered Open-Meteo fetching is disabled.

## Important limitations

- Render's free Postgres expires **30 days** after creation and has no backups. Do not load private health data or rely on it for long-term records.
- Free web services can sleep after inactivity; first requests can be slow. Without the optional preload, the in-process refresh runs only after a signed-in dashboard is opened. With preload, GitHub Actions wakes the service but scheduled runs can be delayed or dropped.
- A first forecast run across all configured districts may take several minutes or fail under free-instance memory, upstream, or database limits. Missing, stale, or QC-failed records remain visibly blocked; historical replay remains a demonstration of the rules, not proof of forecast accuracy.
- The database is private-only in the Blueprint. The web service uses strict authentication and CAP `Test`. SMS/email are still simulated.
- The repository must first contain the README, Dockerfile, and Blueprint changes on the branch that Render uses. Creating a Blueprint from the old branch will not deploy these changes.

## Set up in Render

1. Connect Render to the GitHub repository and select the branch containing `render.yaml`.
2. Create a **Blueprint** from that file. Check that the preview shows only a **free web service** and **free Postgres**. Do not accept an unexpected paid plan.
3. When prompted for `HEATWATCH_USERS_JSON`, enter a private JSON map for one or more provisioned usernames: `viewer`, `officer`, or `admin`. Use unique strong passwords. Do **not** paste them into GitHub, chat, or a committed `.env`.
4. Confirm the generated session secret, `AUTH_MODE=strict`, `CAP_STATUS=Test`, and private Postgres access. Keep `GROQ_API_KEY` unset unless you intentionally configure it as a private environment variable.
5. Wait for the build and first deploy, then open the service's HTTPS URL. `/` must lead to the public landing page, `/login.html` to sign-in, `/signup.html` to viewer registration, and `/dashboard.html` must require an authenticated session. Check `/health`, `/readiness`, and `/auth/config`; the latter must report strict mode and `email_registration: true`. An unauthenticated `/districts` request must return 401.
6. Select a bundled historical replay for a deterministic walkthrough. Opening the dashboard also starts an on-demand live forecast run if the previous run is missing or at least six hours old. The UI shows fetching status; it does **not** turn the map green until retrieval, QC, index calculation, and alert persistence succeed. Failed runs retry after a 20-minute cooldown when a user opens or keeps the dashboard active.

## Verification checklist

- The dashboard and API load from the same HTTPS origin; the browser does not call `localhost`.
- District geometry loads and the selected replay shows its source and historical dates.
- The viewer cannot approve or dispatch; officer approval is required; CAP remains `Test`.
- The audit/event view records permitted actions; dispatch adapters state that delivery is simulated.
- A stale/missing live forecast does not appear as a current green alert.

If the container fails during startup, inspect Render logs for database provisioning/PostGIS errors or memory exhaustion. Do not switch to demo authentication or disable quality gates to make the deploy appear healthy.

## Optional Google and GitHub sign-in

Social buttons are intentionally disabled until a provider is configured. After Render assigns the final HTTPS URL, set `PUBLIC_BASE_URL` to that exact origin (for example `https://heatsafe-ai-demo.onrender.com` if that is the assigned URL). Register these callback URLs with the corresponding provider, then add the matching client ID and client secret as **private Render environment variables**:

- Google: `/auth/oauth/google/callback`, `HEATSAFE_GOOGLE_CLIENT_ID` and `HEATSAFE_GOOGLE_CLIENT_SECRET`.
- GitHub: `/auth/oauth/github/callback`, `HEATSAFE_GITHUB_CLIENT_ID` and `HEATSAFE_GITHUB_CLIENT_SECRET`.

Do not put these secrets in Git, `.env.example`, browser-side variables, or chat. New provider identities receive viewer access only; matching email text never grants officer/admin rights. The live GitHub provider is configured, but end-to-end user consent still needs verification. Google needs a personal-account OAuth project and credentials before activation. Existing privileged email/password access is provisioned with private `HEATWATCH_USERS_JSON` entries. The Blueprint sets `HEATSAFE_ALLOW_SIGNUP=true`: the sign-in page links to `/signup.html`, which creates only viewer accounts in Postgres. Registration emails are **not verified**; there is no password-reset or account-recovery service. Do not use a password you need to recover on this temporary database.

## What a persistent live deployment would require

An uninterrupted live forecast still needs a scheduled pipeline, a non-expiring database with backup/restore, enough compute for model/index and geospatial processing, monitoring, and source-rate-limit review. The free tier sleeps after inactivity and its filesystem is ephemeral, so the on-demand refresh cannot guarantee continuous freshness. Render cron jobs have a minimum monthly charge and are intentionally omitted from the free Blueprint. Before any public-authority use, complete the IMD/source validation, security, privacy, CAP profile, and real-gateway gates in [LIMITATIONS.md](LIMITATIONS.md). Upgrading service plans or creating a paid scheduler requires separate approval.

Official platform references: [Render Blueprint specification](https://render.com/docs/blueprint-spec), [free-plan limitations](https://render.com/docs/free), [supported Postgres extensions](https://render.com/docs/postgresql-extensions), and [cron job pricing/behavior](https://render.com/docs/cronjobs).
