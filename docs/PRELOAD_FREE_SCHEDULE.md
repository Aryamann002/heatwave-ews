# Free six-hour forecast preload

The scheduled GitHub Actions runner fetches Open-Meteo's seven-day forecast **outside Render**, packages all 641 districts, and sends the package to a restricted HTTPS upload endpoint. Render verifies the manifest, per-file checksums, district coverage, and timestamps, then runs the existing quality checks, heat indices, and alert pipeline. The browser reads only a complete, current run. This avoids repeated Open-Meteo requests from Render's rate-limited network and works while your laptop is off. It does not expose Postgres, add a paid Render service, or bypass quality checks.

## One-time setup

1. Deploy the branch containing `backend/app/forecast_upload.py`, `backend/app/main.py`, `scripts/preload_forecast.py`, and `.github/workflows/preload-forecast.yml` to the **HeatSafe AI web service**. Do not set the upload token until this code is deployed.
2. Generate one cryptographically random 48-byte secret locally. In Windows PowerShell, run:

   ```powershell
   $bytes = New-Object byte[] 48
   $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
   $rng.GetBytes($bytes)
   $rng.Dispose()
   $token = ([BitConverter]::ToString($bytes)).Replace('-', '')
   Set-Clipboard -Value $token
   ```

   Do not print the value, paste it in chat, or commit it. Do not regenerate it between the Render and GitHub entries.
3. In Render, open the HeatSafe AI web service → **Environment** → **Add Environment Variable**. Set the key `HEATSAFE_FORECAST_UPLOAD_TOKEN` and paste the clipboard value. Save and deploy. The token is only for forecast upload/status; it does not grant account or database administration. With it set, visitor-triggered Open-Meteo fetching is disabled, preventing more Render-side 429s.
4. In the fork `GhxstOSINT/heatwave-ews`, open **Settings → Secrets and variables → Actions → New repository secret**. Create `HEATSAFE_FORECAST_UPLOAD_TOKEN` with the **same** clipboard value. Keep the value only in the two secret stores. Clear the PowerShell variable and clipboard after both are saved with `Remove-Variable token` and `Set-Clipboard -Value ''`.
5. Merge the branch into the fork's **default branch** (or make this branch the default). GitHub scheduled workflows run only from the default branch. In the fork's **Actions** tab, enable Actions and the **Preload seven-day forecast** workflow if prompted. Choose **Run workflow** for an immediate test. A successful log ends with `Fresh seven-day forecast is ready` and a run ID.

The GitHub workflow runs at **00:23, 06:23, 12:23 and 18:23 UTC** (05:53, 11:53, 17:53 and 23:53 IST). It also supports manual runs. Its token-protected verification checks seven dates, 641 districts, and 4,487 alert rows before reporting success.

## Preload immediately from this computer

If the next scheduled run is hours away, use the same script locally after the Render deploy and token setup:

```powershell
Set-Location -LiteralPath 'C:\Users\aksha\Desktop\Projects\(M) SIH - Heatwave\heatwave-ews'
$env:HEATSAFE_FORECAST_UPLOAD_TOKEN = $token
python scripts/preload_forecast.py
Remove-Item Env:HEATSAFE_FORECAST_UPLOAD_TOKEN
```

The script fetches the current Open-Meteo forecast unless `HEATSAFE_PRELOAD_RAW_DIR` points to a recently fetched, complete local run. Do not use an old bundle. Never put the token in the script, a command argument, a log, or a screenshot.

## Failures and limitations

- `401` from `/forecast-upload`: the Render and GitHub token values differ or the deployed code is old.
- `422`: bundle is stale, incomplete, has a checksum mismatch, or does not cover the configured 641 districts. Fetch again; do not bypass validation.
- `429` from Open-Meteo on GitHub: the source itself is rate-limiting the runner. The fetch retries with backoff; use a later manual run if it continues. Moving the fetch off Render reduces the observed Render-specific block but is not a promise of unlimited source access.
- Render restarts or timeouts can interrupt its in-process QC job. The next upload can recover a stale lease; check Render logs for the underlying failure.
- A red GitHub Actions run means the refresh did not meet the complete-data check. The website deliberately blocks stale or failed forecasts rather than claiming they are live.

GitHub may delay or drop scheduled runs and disables schedules in inactive public repositories after 60 days. Check Actions history before a presentation. Render free Postgres expires after **30 days** and has no backups; this is a temporary demo, not an unattended operational warning service.

References: [GitHub scheduled-workflow rules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [Render free-tier limits](https://render.com/docs/free), and [Open-Meteo pricing and limits](https://open-meteo.com/en/pricing).
