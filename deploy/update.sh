#!/usr/bin/env bash
#
# Push a code change to the running server.
#
# From a checkout on the server:      sudo bash deploy/update.sh
# From a checkout somewhere else:     sudo SRC_DIR=/path/to/checkout bash deploy/update.sh
#
# It backs the database up first, copies the code, reinstalls anything new,
# rebuilds the browser app, and restarts. backend/.env and the database are
# never touched.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/bd-dispatch}"
APP_USER="${APP_USER:-dispatch}"
API_PORT="${API_PORT:-8000}"
HTTP_PORT="${HTTP_PORT:-80}"
SRC_DIR="${SRC_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mx  %s\033[0m\n' "$*" >&2; exit 1; }

NODE_MAJOR="${NODE_MAJOR:-22}"
# shellcheck source=deploy/lib.sh
. "$SRC_DIR/deploy/lib.sh"

[ "$(id -u)" -eq 0 ] || die "Run this with sudo."
[ -d "$APP_DIR" ] || die "$APP_DIR is not there. Run deploy/install.sh first."

say "Backing the database up first"
bash "$APP_DIR/deploy/backup.sh"

say "Copying the code"
rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$SRC_DIR/" "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/backend/.env" "$APP_DIR/.db-password" 2>/dev/null || true

say "Updating Python dependencies"
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"

say "Rebuilding the browser app"
build_frontend

say "Applying schema changes"
sudo -u "$APP_USER" sh -c "cd \"$APP_DIR/backend\" && .venv/bin/python -c 'import app.main'"

say "Refreshing the nginx config"
# From the templates just copied, https or not as backend/.env says.
render_nginx

say "Restarting"
systemctl restart bd-dispatch
sleep 3
if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then
  echo "    the API is answering. Tell everyone to reload the page."
else
  die "the API is not answering. journalctl -u bd-dispatch -n 50"
fi
