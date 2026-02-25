# Daily Database Refresh (Cron)

This app refreshes the station database through the `POST /refresh` endpoint.
Use the script in this folder to call that endpoint from `cron`.

## Files

- `ops/cron/refresh-db.sh`: Bash script for the daily refresh job

## What the script handles

- Calls `POST /refresh` (the app's refresh endpoint)
- Sends `X-Admin-Token` automatically if `ADMIN_TOKEN` exists in the env file
- Logs to a file
- Treats HTTP `429` (app refresh rate limit) as a normal skip
- Fails on auth/IP errors (`401`, `403`) and unexpected statuses

## Configure

The script is configurable using environment variables (optional):

- `APP_DIR` (default: `/opt/ntrip-stations`)
- `ENV_FILE` (default: `$APP_DIR/.env`)
- `LOG_DIR` (default: `$APP_DIR/logs`)
- `LOG_FILE` (default: `$LOG_DIR/refresh-db.log`)
- `API_URL` (default: `http://127.0.0.1:8000/refresh`)

Example manual run:

```bash
APP_DIR=/opt/ntrip-stations \
ENV_FILE=/opt/ntrip-stations/.env-production \
API_URL=http://127.0.0.1:8000/refresh \
bash /opt/ntrip-stations/ops/cron/refresh-db.sh
```

## Install on server

1. Copy/pull this repo to your server (for example `/opt/ntrip-stations`).
2. Make the script executable:

```bash
chmod +x /opt/ntrip-stations/ops/cron/refresh-db.sh
```

3. Confirm the endpoint works manually:

```bash
/opt/ntrip-stations/ops/cron/refresh-db.sh
tail -n 20 /opt/ntrip-stations/logs/refresh-db.log
```

## Cron (daily at 02:00)

Edit crontab:

```bash
crontab -e
```

Add:

```cron
0 22 * * * /opt/ntrip-stations/ops/cron/refresh-db.sh
```

## Important app settings

- If `ADMIN_TOKEN` is set in `.env-production`, the script must load that file.
- If `REFRESH_ALLOWED_IPS` is set, allow the caller IP (commonly `127.0.0.1` when cron runs on the app host).
- `REFRESH_DB_RATE_LIMIT` is enforced by the app (default documented as `1/day`), so extra runs may return `429`.

