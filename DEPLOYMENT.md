# Deployment Guide: RTK2GO Station Finder

## Choose a deployment option

| | [Option A: VM / VPS](#option-a-vm--vps-deployment-reverse-proxy) | [Option B: Vercel](#option-b-vercel-deployment) (in use) |
|---|---|---|
| Runtime | uvicorn + systemd behind nginx/Apache | Serverless Python function |
| Database | Local SQLite (`rtk2go.db`) | Hosted Postgres, e.g. Neon (`DATABASE_URL`) |
| Daily refresh | System cron → `ops/cron/refresh-db.sh` → `POST /refresh` | Vercel Cron → `GET /api/cron/refresh` |
| Rate limiting | Exact (single process) | Per instance only (in-memory) |
| TLS / domain | You configure the proxy and certificates | Automatic |
| Ops effort | Server upkeep | None |

- Choose **Option A** if you already run a server, want exact rate limits, or want everything (including the database) on one machine.
- Choose **Option B** for a zero-maintenance setup with automatic HTTPS and git-push deploys.

---

## Option A: VM / VPS deployment (reverse proxy)

This part covers deploying the app in production on a Linux server behind a reverse proxy.

### Architecture Overview

```
Internet (HTTPS)
    ↓
Reverse Proxy (nginx, Apache, etc.) - port 80/443
    ↓
Uvicorn Server (127.0.0.1:8000)
    ↓
FastAPI Application
```

**Note:** You are responsible for configuring your reverse proxy. This guide focuses on the application setup.

### Prerequisites

- Linux server (Ubuntu 20.04 LTS or later recommended)
- Python 3.11+
- A reverse proxy upstream
- systemd (for service management)

### Step 1: Prepare the Server

#### Install Dependencies

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Add deadsnakes PPA for Python 3.11 (if not in default repos)
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update

# Install Python and dependencies
sudo apt install python3.11 python3.11-venv python3-pip -y

# Install git
sudo apt install git -y
```

**Note:** If `add-apt-repository` is not available or you're on a system without PPA support, use your distribution's package manager or build Python 3.11 from source.

#### Create Application User

```bash
# Create a dedicated user for the app (better security)
sudo useradd -m -s /bin/bash ntrip-app

# Create app directory
sudo mkdir -p /opt/ntrip-stations
sudo chown ntrip-app:ntrip-app /opt/ntrip-stations
```

### Step 2: Deploy Application

#### Clone Repository

```bash
cd /opt/ntrip-stations
sudo -u ntrip-app git clone <your-repo-url> .
```

#### Setup Virtual Environment

```bash
cd /opt/ntrip-stations

# Create virtual environment
sudo -u ntrip-app python3.11 -m venv venv

# Activate and install dependencies
sudo -u ntrip-app venv/bin/pip install --upgrade pip setuptools wheel
sudo -u ntrip-app venv/bin/pip install -r requirements.txt
```

#### Configure Environment

```bash
# Copy example env file
sudo -u ntrip-app cp examples/.env.production /opt/ntrip-stations/.env

# Edit .env with production settings
sudo -u ntrip-app nano .env
```

**Key production settings in `.env`:**

```env
# Must set to production
ENVIRONMENT=production

# Your domain(s)
ALLOWED_HOSTS=example.com,www.example.com

# Trusted reverse proxy IP(s) - set to your proxy server's IP
TRUSTED_HOSTS=10.0.0.1

# Your actual Geoapify API key
GEOAPIFY_API_KEY=your_actual_key_here

# Rate limiting configuration
GEOAPIFY_API_RATE_LIMIT=5/second
REFRESH_DB_RATE_LIMIT=1/day

# Distance badge thresholds (customize for your use case)
DISTANCE_BADGE_GREEN_KM=100
DISTANCE_BADGE_YELLOW_KM=300
```

**Important:** Set `TRUSTED_HOSTS` to your reverse proxy server's IP address. If the proxy is on the same machine, use `127.0.0.1`.

#### Create Database

```bash
# The database will be created automatically on first run
# Make sure the directory is writable by ntrip-app user
sudo chown ntrip-app:ntrip-app /opt/ntrip-stations
```

By default the app uses a local SQLite file (`rtk2go.db`). To use Postgres instead, set `DATABASE_URL` in `.env` (e.g. `DATABASE_URL=postgresql://user:pass@host/dbname`); tables are created automatically on startup.

### Step 3: Setup Systemd Service

#### Create Service File

```bash
sudo nano /etc/systemd/system/ntrip-app.service
```

**Paste the following:**

```ini
[Unit]
Description=RTK2GO Station Finder
After=network.target

[Service]
Type=notify
User=ntrip-app
WorkingDirectory=/opt/ntrip-stations
ExecStart=/opt/ntrip-stations/venv/bin/python /opt/ntrip-stations/run.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security options
PrivateTmp=yes
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
```

#### Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable ntrip-app
sudo systemctl start ntrip-app

# Check status
sudo systemctl status ntrip-app

# View logs
sudo journalctl -u ntrip-app -f
```

### Step 4: Configure Your Reverse Proxy

Configure your reverse proxy (nginx, Apache, HAProxy, etc.) to:

1. **Listen on ports 80/443** (public internet)
2. **Proxy requests to** `http://127.0.0.1:8000`
3. **Set headers:**
   - `X-Forwarded-For`: Client's real IP
   - `X-Forwarded-Proto`: Original scheme (http/https)
   - `X-Forwarded-Host`: Original host header
   - `X-Real-IP`: Client's real IP

**Example for nginx:**
```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
}
```

**Important:** The `X-Forwarded-For` header is critical for rate limiting to work correctly (extracts real client IP instead of proxy server IP).

### Step 5: SSL/TLS Configuration

Configure SSL/TLS at your reverse proxy level (recommended for centralized certificate management).

### Step 6: Rate Limiting Behind Proxy

The app is configured to read `X-Forwarded-For` header to extract the real client IP for rate limiting.

**Verify in `run.py` and `app/main.py`:**

- `run.py` binds to `127.0.0.1:8000` when `ENVIRONMENT=production`
- `app/main.py` has custom `get_client_ip()` that reads `X-Forwarded-For`
- nginx config includes `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`

**Rate limits work correctly** because:
1. Client connects to nginx (public IP)
2. nginx forwards to `127.0.0.1:8000` with `X-Forwarded-For: <client_ip>`
3. App extracts real client IP from header
4. Rate limiting applies per real client IP (not per nginx server IP)

### Monitoring & Maintenance

#### Check Service Status

```bash
sudo systemctl status ntrip-app
sudo journalctl -u ntrip-app -n 50  # Last 50 lines
sudo journalctl -u ntrip-app -f     # Follow logs
```

#### View Reverse Proxy Logs

Check your reverse proxy's log files for request details:
- nginx: `/var/log/nginx/access.log` or `/var/log/nginx/error.log`
- Apache: `/var/log/apache2/access.log` or `/var/log/apache2/error.log`
- Other: See your proxy's documentation

#### Update Application

Pull the latest changes from the repository and reinstall dependencies:

```bash
cd /opt/ntrip-stations

# Pull latest code from main branch (as ntrip-app user)
sudo -u ntrip-app git pull origin main

# Reinstall/update Python dependencies in case requirements changed
sudo -u ntrip-app venv/bin/pip install -r requirements.txt

# Restart the service to load new code
sudo systemctl restart ntrip-app

# Verify the update was successful
sudo systemctl status ntrip-app
```

**Important:**
- Always run `git pull` as the `ntrip-app` user (not root) to maintain proper file permissions
- The `sudo -u ntrip-app` prefix ensures the cloned files are owned by `ntrip-app`, not root
- If the pull fails due to local modifications, see the Troubleshooting section below

#### Database Refresh

Use the cron helper script in `ops/cron/refresh-db.sh` and see `ops/cron/README.md` for setup details.

The app refreshes the NTRIP station database via the `/refresh` endpoint.
Rate limiting (database timestamp-based) prevents excessive downloads.
Two optional authentication mechanisms are also available (see `.env` configuration).

##### Calling `/refresh` without authentication (default)

```bash
# No auth configured — endpoint is open
curl -X POST https://example.com/refresh
```

##### Calling `/refresh` with `ADMIN_TOKEN`

If `ADMIN_TOKEN` is set in `.env`, you must supply the token in the request header:

```bash
curl -X POST https://example.com/refresh \
     -H "X-Admin-Token: your_secret_token_here"
```

The server returns HTTP 401 if the token is missing or incorrect.

##### Calling `/refresh` with `REFRESH_ALLOWED_IPS`

If `REFRESH_ALLOWED_IPS` is set, only requests from the listed IPs are accepted.
All other callers receive HTTP 403. No header is required for allowlisted IPs.

##### Using both together (defense in depth)

When both `ADMIN_TOKEN` and `REFRESH_ALLOWED_IPS` are set, a request must satisfy
both checks simultaneously. Example:

```bash
curl -X POST https://example.com/refresh \
     -H "X-Admin-Token: your_secret_token_here"
# (caller's IP must also be in REFRESH_ALLOWED_IPS)
```

##### Generating a strong token

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output into `ADMIN_TOKEN` in your `.env` file.

### Troubleshooting

#### App won't start
```bash
# Check service logs
sudo journalctl -u ntrip-app -n 20 --no-pager

# Check if port 8000 is already in use
sudo lsof -i :8000

# Verify permissions on app directory
ls -la /opt/ntrip-stations
```

#### Rate limiting not working correctly
- Verify `X-Forwarded-For` header is passed: `sudo tail -f /var/log/nginx/ntrip-stations-access.log`
- Check `TRUSTED_HOSTS` in `.env` includes nginx server IP
- Restart app: `sudo systemctl restart ntrip-app`

#### Reverse proxy returns error (502, 504, etc.)
- Check if Uvicorn is running: `sudo systemctl status ntrip-app`
- Verify Uvicorn binds to `127.0.0.1:8000`: `sudo lsof -i :8000`
- Test connection directly: `curl http://127.0.0.1:8000/`
- Check reverse proxy configuration points to `127.0.0.1:8000`
- Verify firewall allows proxy → `127.0.0.1:8000` connection

### Security Best Practices

#### Enable Firewall (UFW)

```bash
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw default deny incoming
sudo ufw enable
```

#### Keep System Updated

```bash
# Enable automatic security updates
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure unattended-upgrades
```

#### Restrict Database Access

```bash
# Ensure database directory only readable by ntrip-app user
sudo chmod 700 /opt/ntrip-stations
sudo chown ntrip-app:ntrip-app /opt/ntrip-stations/rtk2go.db
```

#### Monitor Services

```bash
# Install monitoring tools
sudo apt install htop iotop -y

# Check resource usage
htop
```

### Production Checklist

- [ ] Environment variable `ENVIRONMENT=production`
- [ ] `ALLOWED_HOSTS` set to your domain(s)
- [ ] `TRUSTED_HOSTS` includes nginx IP if not 127.0.0.1
- [ ] `GEOAPIFY_API_KEY` set to valid key
- [ ] SSL certificate installed and auto-renewal configured
- [ ] nginx configuration tested with `nginx -t`
- [ ] Systemd service enabled and running
- [ ] Firewall rules configured (UFW)
- [ ] Database permissions set correctly
- [ ] Logs monitored and rotation configured
- [ ] Automatic updates enabled
- [ ] Backup strategy in place for database
- [ ] `ADMIN_TOKEN` set to a strong random value (or consciously left unset for open access)
- [ ] `REFRESH_ALLOWED_IPS` restricted to known admin IPs (or consciously left unset)

### Performance Tuning

#### Uvicorn Workers (if needed for high traffic)

For higher concurrency, increase workers in systemd service:

```ini
ExecStart=/opt/ntrip-stations/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 --workers 4
```

#### nginx Caching (optional)

Add to nginx config for static content:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_cache_valid 200 10m;
    proxy_cache_bypass $http_pragma $http_authorization;
    add_header X-Cache-Status $upstream_cache_status;
}
```

---

## Option B: Vercel deployment

> **The current version of the app runs on Vercel, deployed by following the steps below.**

The repository is ready for Vercel with no build step: `index.py` exposes the FastAPI `app`, and `vercel.json` schedules the daily refresh.

### Architecture Overview

```
Internet (HTTPS)
    ↓
Vercel Edge Network (TLS, custom domain)
    ↓
Python Function (index.py → app.main:app)
    ↓                         ↑
Neon Postgres            Vercel Cron (daily)
(DATABASE_URL)           GET /api/cron/refresh
```

Vercel functions have a read-only, temporary filesystem, so the local SQLite file cannot be used there. Station data, countries and search logs live in Postgres instead.

### Prerequisites

- A Vercel account (the Hobby plan is enough)
- This repository pushed to GitHub, GitLab or Bitbucket
- Optional: the [Vercel CLI](https://vercel.com/docs/cli) (`npm i -g vercel`) for local testing and manual deploys

### Step 1: Import the project

1. In the Vercel dashboard, click **Add New → Project** and import the repository.
2. Framework preset: **FastAPI** (or "Other"). Leave the build and output settings empty.
3. Don't deploy yet. First add the database and environment variables (steps 2-3).

### Step 2: Add a Postgres database

1. Open the project → **Storage** → **Create Database** → **Neon** (Serverless Postgres) and connect it to the project.
2. This adds `DATABASE_URL` (and related variables) to the project's environment. Use the **pooled** connection string (its host contains `-pooler`).

The app accepts `postgres://`, `postgresql://` and `postgresql+psycopg://` URLs. Tables are created and countries are seeded automatically on the first cold start.

### Step 3: Configure environment variables

Under **Settings → Environment Variables** (Production, plus Preview if wanted):

| Variable | Value | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | Enables `Secure` cookies (Vercel always serves HTTPS) |
| `API_KEY` | `secrets.token_hex(32)` | Login password, min 16 chars |
| `JWT_SECRET_KEY` | `secrets.token_hex(32)` | Min 32 chars |
| `GEOAPIFY_API_KEY` | your key | Required for address searches |
| `DATABASE_URL` | set by Neon | Pooled connection string |
| `CRON_SECRET` | `secrets.token_hex(32)` | Vercel sends it as `Authorization: Bearer …` to cron routes |
| `DASHBOARD_KEY` | random string | Optional, enables `/dashboard` |
| `ADMIN_TOKEN` | random string | Optional, protects manual `POST /refresh` |
| `DOCS_ADMIN_USER` / `DOCS_ADMIN_PASSWORD` | | Optional, enables `/docs` |
| `ALLOWED_HOSTS` | `<project>.vercel.app,example.com` | Optional; leave unset to allow preview URLs |
| `REFRESH_ALLOWED_IPS` | (leave unset) | Not used: Vercel Cron has no fixed IPs |
| `TRUSTED_HOSTS`, `SERVER_HOST` | (leave unset) | Not used on Vercel |

All other optional variables (rate limits, distance badges, RTK2GO settings) work the same as in Option A.

Generate secrets with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Step 4: Deploy and load the data

1. Click **Deploy** (or run `vercel --prod`). Each push to the main branch deploys again automatically.
2. The station table is empty until the first refresh. Trigger it once:
   - **Settings → Cron Jobs → Run** on `/api/cron/refresh`, or
   - `curl -X POST https://<your-app>.vercel.app/refresh -H "X-Admin-Token: <ADMIN_TOKEN>"`
3. Open `https://<your-app>.vercel.app/login`, sign in with `API_KEY` and run a search.

### Step 5: Daily refresh (Vercel Cron)

`vercel.json` schedules the refresh:

```json
{
  "crons": [{ "path": "/api/cron/refresh", "schedule": "0 3 * * *" }]
}
```

- Vercel calls `GET /api/cron/refresh` every day at 03:00 UTC with `Authorization: Bearer <CRON_SECRET>`.
- The route returns 404 if `CRON_SECRET` is unset and 401 if the token is wrong.
- It shares the database-based rate limit (`REFRESH_DB_RATE_LIMIT`) with `POST /refresh`, so a manual refresh on the same day makes the cron return 429 (harmless).
- The Hobby plan allows cron jobs at most once a day. Cron jobs only run on production deployments.
- To test by hand: `curl https://<your-app>.vercel.app/api/cron/refresh -H "Authorization: Bearer <CRON_SECRET>"`.

`ops/cron/refresh-db.sh` is not used on Vercel.

### Step 6: Custom domain (optional)

**Settings → Domains → Add**, then follow the DNS instructions. If you set `ALLOWED_HOSTS`, add the new domain to it and redeploy.

### Local testing

```bash
# Run against the Neon database with the normal dev server
DATABASE_URL="postgresql://..." python run.py

# Or emulate the Vercel runtime (pulls env vars with `vercel env pull`)
vercel dev
```

### Limitations

- **Rate limiting is per instance.** slowapi keeps counters in memory, and Vercel may run several instances at once, so `GEOAPIFY_API_RATE_LIMIT` and the login limit are approximate. The refresh limit is exact because it uses the database.
- **Cold starts.** The first request after a quiet period starts a new instance (it imports the app, connects to the database and checks tables), so it takes noticeably longer.
- **Function duration.** A refresh opens a raw TCP connection to `rtk2go.com:2101` (timeout `RTK2GO_TIMEOUT_SECS`, default 30 s). This fits within Vercel's default function time limit. Don't raise the timeout above your plan's limit.

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Deployment fails at startup with `API_KEY must be set…` / `JWT_SECRET_KEY…` | Environment variable missing or too short. Set it and redeploy |
| Cron run shows 401 | `CRON_SECRET` was changed or isn't set for the Production environment. Redeploy after changing it |
| Cron run shows 429 | Already refreshed within `REFRESH_DB_RATE_LIMIT`. Expected |
| Empty station list / "0 stations" | No refresh has run yet. See Step 4 |
| `400 Invalid host header` | The domain isn't listed in `ALLOWED_HOSTS` |
| Database connection errors | Use the **pooled** Neon URL and check that `DATABASE_URL` is set for the right environment |

Logs: **Project → Logs** (runtime logs for each function call) or `vercel logs <deployment-url>`.

---

## Support & Debugging

For issues on **Vercel**, check **Project → Logs** and the **Cron Jobs** tab first.

For issues on a **VM**:
1. Check systemd logs: `journalctl -u ntrip-app -n 50`
2. Check nginx logs: `/var/log/nginx/ntrip-stations-*.log`
3. Verify network connectivity: `curl http://127.0.0.1:8000/`
4. Test rate limiting manually with repeated requests
5. Check database exists: `ls -la /opt/ntrip-stations/rtk2go.db`
