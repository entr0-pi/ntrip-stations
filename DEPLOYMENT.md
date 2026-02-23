# Deployment Guide: RTK2GO Station Finder

This guide covers deploying the RTK2GO Station Finder app for production environments behind a reverse proxy.

## Architecture Overview

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

## Prerequisites

- Linux server (Ubuntu 20.04 LTS or later recommended)
- Python 3.11+
- A reverse proxy upstream
- systemd (for service management)

## Step 1: Prepare the Server

### Install Dependencies

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

### Create Application User

```bash
# Create a dedicated user for the app (better security)
sudo useradd -m -s /bin/bash ntrip-app

# Create app directory
sudo mkdir -p /opt/ntrip-stations
sudo chown ntrip-app:ntrip-app /opt/ntrip-stations
```

## Step 2: Deploy Application

### Clone Repository

```bash
cd /opt/ntrip-stations
sudo -u ntrip-app git clone <your-repo-url> .
```

### Setup Virtual Environment

```bash
cd /opt/ntrip-stations

# Create virtual environment
sudo -u ntrip-app python3.11 -m venv venv

# Activate and install dependencies
sudo -u ntrip-app venv/bin/pip install --upgrade pip setuptools wheel
sudo -u ntrip-app venv/bin/pip install -r requirements.txt
```

### Configure Environment

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
```

**Important:** Set `TRUSTED_HOSTS` to your reverse proxy server's IP address. If the proxy is on the same machine, use `127.0.0.1`.

### Create Database

```bash
# The database will be created automatically on first run
# Make sure the directory is writable by ntrip-app user
sudo chown ntrip-app:ntrip-app /opt/ntrip-stations
```

## Step 3: Setup Systemd Service

### Create Service File

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

### Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable ntrip-app
sudo systemctl start ntrip-app

# Check status
sudo systemctl status ntrip-app

# View logs
sudo journalctl -u ntrip-app -f
```

## Step 4: Configure Your Reverse Proxy

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

## Step 5: SSL/TLS Configuration

Configure SSL/TLS at your reverse proxy level (recommended for centralized certificate management).

If you need certificate management advice, see the `DEPLOYMENT.md` file in version control for Let's Encrypt examples.

## Step 6: Rate Limiting Behind Proxy

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

## Monitoring & Maintenance

### Check Service Status

```bash
sudo systemctl status ntrip-app
sudo journalctl -u ntrip-app -n 50  # Last 50 lines
sudo journalctl -u ntrip-app -f     # Follow logs
```

### View Reverse Proxy Logs

Check your reverse proxy's log files for request details:
- nginx: `/var/log/nginx/access.log` or `/var/log/nginx/error.log`
- Apache: `/var/log/apache2/access.log` or `/var/log/apache2/error.log`
- Other: See your proxy's documentation

### Update Application

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

### Database Refresh

The app refreshes the NTRIP station database via the `/refresh` endpoint. Rate limiting prevents excessive downloads:

```bash
# Manual refresh via curl
curl -X POST https://example.com/refresh

# Check current station count
# This is visible in the web UI
```

## Troubleshooting

### App won't start
```bash
# Check service logs
sudo journalctl -u ntrip-app -n 20 --no-pager

# Check if port 8000 is already in use
sudo lsof -i :8000

# Verify permissions on app directory
ls -la /opt/ntrip-stations
```

### Rate limiting not working correctly
- Verify `X-Forwarded-For` header is passed: `sudo tail -f /var/log/nginx/ntrip-stations-access.log`
- Check `TRUSTED_HOSTS` in `.env` includes nginx server IP
- Restart app: `sudo systemctl restart ntrip-app`

### Reverse proxy returns error (502, 504, etc.)
- Check if Uvicorn is running: `sudo systemctl status ntrip-app`
- Verify Uvicorn binds to `127.0.0.1:8000`: `sudo lsof -i :8000`
- Test connection directly: `curl http://127.0.0.1:8000/`
- Check reverse proxy configuration points to `127.0.0.1:8000`
- Verify firewall allows proxy → `127.0.0.1:8000` connection

## Security Best Practices

### Enable Firewall (UFW)

```bash
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw default deny incoming
sudo ufw enable
```

### Keep System Updated

```bash
# Enable automatic security updates
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure unattended-upgrades
```

### Restrict Database Access

```bash
# Ensure database directory only readable by ntrip-app user
sudo chmod 700 /opt/ntrip-stations
sudo chown ntrip-app:ntrip-app /opt/ntrip-stations/rtk2go.db
```

### Monitor Services

```bash
# Install monitoring tools
sudo apt install htop iotop -y

# Check resource usage
htop
```

## Production Checklist

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

## Performance Tuning

### Uvicorn Workers (if needed for high traffic)

For higher concurrency, increase workers in systemd service:

```ini
ExecStart=/opt/ntrip-stations/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 --workers 4
```

### nginx Caching (optional)

Add to nginx config for static content:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_cache_valid 200 10m;
    proxy_cache_bypass $http_pragma $http_authorization;
    add_header X-Cache-Status $upstream_cache_status;
}
```

## Support & Debugging

For issues:
1. Check systemd logs: `journalctl -u ntrip-app -n 50`
2. Check nginx logs: `/var/log/nginx/ntrip-stations-*.log`
3. Verify network connectivity: `curl http://127.0.0.1:8000/`
4. Test rate limiting manually with repeated requests
5. Check database exists: `ls -la /opt/ntrip-stations/rtk2go.db`
