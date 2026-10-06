# HeatSafe AI on Render: free temporary demonstration

This is a **temporary presentation deployment**, not an operational warning service. The root `render.yaml` defines one free web service (FastAPI plus the built dashboard at the same HTTPS origin) and one free Render Postgres database with PostGIS. It deliberately defines **no scheduler, cron job, public dispatch gateway, or production alert feed**.

## Important limitations

- Render's free Postgres expires **30 days** after creation and has no backups. Do not load private health data or rely on it for long-term records.
- Free web services can sleep after inactivity; first requests can be slow. The plan has resource limits, so a full India forecast pipeline has **not** been established on this tier.
- The dashboard has no continuously refreshed live forecast in this configuration. Missing or stale forecast records must remain visibly blocked. Historical replay remains a demonstration of the rules, not proof of forecast accuracy.
- The database is private-only in the Blueprint. The web service uses strict authentication and CAP `Test`. SMS/email are still simulated.
- The repository must first contain the README, Dockerfile, and Blueprint changes on the branch that Render uses. Creating a Blueprint from the old branch will not deploy these changes.

## Set up in Render

1. Connect Render to the GitHub repository and select the branch containing `render.yaml`.
2. Create a **Blueprint** from that file. Check that the preview shows only a **free web service** and **free Postgres**. Do not accept an unexpected paid plan.
3. When prompted for `HEATWATCH_USERS_JSON`, enter a private JSON map for one or more provisioned usernames: `viewer`, `officer`, or `admin`. Use unique strong passwords. Do **not** paste them into GitHub, chat, or a committed `.env`.
4. Confirm the generated session secret, `AUTH_MODE=strict`, `CAP_STATUS=Test`, and private Postgres access. Keep `GROQ_API_KEY` unset unless you intentionally configure it as a private environment variable.
5. Wait for the build and first deploy, then open the service's HTTPS URL. Check `/health`, `/readiness`, `/auth/config`, and the landing dashboard. `/auth/config` must report strict mode.
6. Select a bundled historical replay for a deterministic walkthrough. The **live forecast** view is expected to show a blocked/unavailable state until a separate, explicitly authorized data-refresh arrangement exists.

## Verification checklist

- The dashboard and API load from the same HTTPS origin; the browser does not call `localhost`.
- District geometry loads and the selected replay shows its source and historical dates.
- The viewer cannot approve or dispatch; officer approval is required; CAP remains `Test`.
- The audit/event view records permitted actions; dispatch adapters state that delivery is simulated.
- A stale/missing live forecast does not appear as a current green alert.

If the container fails during startup, inspect Render logs for database provisioning/PostGIS errors or memory exhaustion. Do not switch to demo authentication or disable quality gates to make the deploy appear healthy.

## What a persistent live deployment would require

A live forecast needs a scheduled pipeline, a non-expiring database with backup/restore, enough compute for model/index and geospatial processing, monitoring, and source-rate-limit review. Render cron jobs have a minimum monthly charge and are intentionally omitted from the free Blueprint. Before any public-authority use, complete the IMD/source validation, security, privacy, CAP profile, and real-gateway gates in [LIMITATIONS.md](LIMITATIONS.md). Upgrading service plans or creating a paid scheduler requires separate approval.

Official platform references: [Render Blueprint specification](https://render.com/docs/blueprint-spec), [free-plan limitations](https://render.com/docs/free), [supported Postgres extensions](https://render.com/docs/postgresql-extensions), and [cron job pricing/behavior](https://render.com/docs/cronjobs).
