#!/usr/bin/env bash
set -euo pipefail

# Refresh the station database by calling the app's POST /refresh endpoint.
# The app enforces its own refresh rate limit (REFRESH_DB_RATE_LIMIT).

APP_DIR="${APP_DIR:-/opt/ntrip-stations}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/refresh-db.log}"
API_URL="${API_URL:-http://127.0.0.1:8000/refresh}"

mkdir -p "$LOG_DIR"

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

# Load environment (optional). Supports ADMIN_TOKEN if present.
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

tmp_body="$(mktemp)"
trap 'rm -f "$tmp_body"' EXIT

curl_args=(
  -sS
  -X POST "$API_URL"
  -o "$tmp_body"
  -w '%{http_code}'
  --max-time 120
)

if [[ -n "${ADMIN_TOKEN:-}" ]]; then
  curl_args+=(-H "X-Admin-Token: $ADMIN_TOKEN")
fi

http_code="$(curl "${curl_args[@]}")" || {
  echo "[$(timestamp)] ERROR curl failed" >> "$LOG_FILE"
  exit 1
}

body="$(cat "$tmp_body")"

case "$http_code" in
  200)
    echo "[$(timestamp)] OK refresh succeeded: $body" >> "$LOG_FILE"
    ;;
  429)
    echo "[$(timestamp)] SKIP rate-limited: $body" >> "$LOG_FILE"
    ;;
  401|403)
    echo "[$(timestamp)] ERROR auth/ip denied (HTTP $http_code): $body" >> "$LOG_FILE"
    exit 1
    ;;
  *)
    echo "[$(timestamp)] ERROR unexpected HTTP $http_code: $body" >> "$LOG_FILE"
    exit 1
    ;;
esac

