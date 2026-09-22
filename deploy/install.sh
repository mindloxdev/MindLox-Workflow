#!/usr/bin/env bash
#
# Put Dispatch on a Linux server on your own network, with nothing hosted.
#
# Run it on the server, as a user who can sudo:
#
#     sudo bash deploy/install.sh
#
# What it leaves behind:
#   /opt/bd-dispatch            the app
#   postgresql                  the database, on this machine, listening to nobody else
#   systemd unit bd-dispatch    starts on boot, restarts if it dies
#   nginx on port 80            so the link you hand out has no port number in it
#
# Safe to run twice. It rebuilds and restarts; it does not touch the database
# once that exists, and it never overwrites a .env it did not just create.

set -euo pipefail

# --------------------------------------------------------------------------- #
# Settings. Override any of them on the command line:
#     sudo APP_DIR=/srv/dispatch HTTP_PORT=8080 bash deploy/install.sh
# --------------------------------------------------------------------------- #
APP_DIR="${APP_DIR:-/opt/bd-dispatch}"
APP_USER="${APP_USER:-dispatch}"
DB_NAME="${DB_NAME:-dispatch}"
DB_USER="${DB_USER:-dispatch}"
PG_VERSION="${PG_VERSION:-17}"
API_PORT="${API_PORT:-8000}"     # localhost only; nginx is what the network sees
HTTP_PORT="${HTTP_PORT:-80}"     # what you hand out
WORKERS="${WORKERS:-2}"
HOSTNAME_LOCAL="${HOSTNAME_LOCAL:-dispatch}"   # -> http://dispatch.local
NODE_MAJOR="${NODE_MAJOR:-20}"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mx  %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this with sudo."
command -v apt-get >/dev/null || die "This installer is written for Debian and Ubuntu."

# --------------------------------------------------------------------------- #
# 1. Packages
# --------------------------------------------------------------------------- #
say "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates gnupg lsb-release rsync \
                       python3 python3-venv python3-dev build-essential \
                       nginx ufw avahi-daemon >/dev/null

# PostgreSQL from the PGDG repo rather than the distro. The version matters:
# pg_dump can read a server older than itself but never a newer one, and Neon
# runs a recent major. Pinning to $PG_VERSION here keeps the migration working.
if ! command -v psql >/dev/null || ! psql --version | grep -q " ${PG_VERSION}\."; then
  say "Installing PostgreSQL $PG_VERSION"
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
  apt-get update -qq
  apt-get install -y -qq "postgresql-${PG_VERSION}" "postgresql-client-${PG_VERSION}" >/dev/null
fi
systemctl enable --now "postgresql@${PG_VERSION}-main" >/dev/null 2>&1 || systemctl enable --now postgresql

# Node is needed only to build the browser app. It is not needed to run it.
if ! command -v node >/dev/null || [ "$(node -v | sed 's/v\([0-9]*\).*/\1/')" -lt 18 ]; then
  say "Installing Node $NODE_MAJOR"
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - >/dev/null
  apt-get install -y -qq nodejs >/dev/null
fi

# --------------------------------------------------------------------------- #
# 2. The account the app runs as
# --------------------------------------------------------------------------- #
if ! id "$APP_USER" >/dev/null 2>&1; then
  say "Creating the $APP_USER account"
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

# --------------------------------------------------------------------------- #
# 3. The code
# --------------------------------------------------------------------------- #
say "Copying the app to $APP_DIR"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude 'node_modules' \
  --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude 'backend/.env' --exclude 'backend/dispatch.db' \
  --exclude 'frontend/dist' --exclude '.db-password' \
  "$SRC_DIR/" "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# --------------------------------------------------------------------------- #
# 4. The database, on this machine only
# --------------------------------------------------------------------------- #
say "Setting up PostgreSQL"
DB_PASS_FILE="$APP_DIR/.db-password"
if [ -f "$DB_PASS_FILE" ]; then
  DB_PASS="$(cat "$DB_PASS_FILE")"
else
  DB_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  printf '%s' "$DB_PASS" > "$DB_PASS_FILE"
  chmod 600 "$DB_PASS_FILE"
  chown "$APP_USER:$APP_USER" "$DB_PASS_FILE"
fi

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'" | grep -q 1; then
  sudo -u postgres psql -q -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS'"
fi
sudo -u postgres psql -q -c "ALTER ROLE $DB_USER PASSWORD '$DB_PASS'"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
  sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
fi

DATABASE_URL="postgresql+psycopg2://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME"

# --------------------------------------------------------------------------- #
# 5. backend/.env
# --------------------------------------------------------------------------- #
ENV_FILE="$APP_DIR/backend/.env"
if [ -f "$ENV_FILE" ]; then
  say "Keeping the existing backend/.env"
  warn "Delete it and re-run if you want a fresh one."
else
  say "Writing backend/.env"
  JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cat > "$ENV_FILE" <<ENVFILE
# Written by deploy/install.sh. Everything here stays on this machine.

# PostgreSQL on this server, reachable from this server only.
DATABASE_URL=$DATABASE_URL

# Signs the sign-in tokens. Changing it signs everybody out; it does not
# touch anybody's password.
JWT_SECRET=$JWT_SECRET
JWT_HOURS=12

# One process serves both the browser app and the API, so there is no other
# origin to allow and CORS never enters into it.
CORS_ORIGINS=

# How often the rebuild timer looks for a cycle that is due. 0 turns it off.
AUTO_BUILD_TICK_SECONDS=60
ENVFILE
fi
chmod 600 "$ENV_FILE"
chown "$APP_USER:$APP_USER" "$ENV_FILE"

# --------------------------------------------------------------------------- #
# 6. Python
# --------------------------------------------------------------------------- #
say "Installing Python dependencies"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/backend/.venv"
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install -q --upgrade pip wheel
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"

# --------------------------------------------------------------------------- #
# 7. Build the browser app
# --------------------------------------------------------------------------- #
say "Building the browser app"
sudo -u "$APP_USER" env HOME="$APP_DIR" sh -c "cd \"$APP_DIR/frontend\" && npm ci --no-audit --no-fund && npm run build"
[ -f "$APP_DIR/frontend/dist/index.html" ] || die "The frontend build produced no dist/index.html."

# --------------------------------------------------------------------------- #
# 8. Create the tables before anything serves traffic
#
# Importing app.main runs create_all and the schema upgrades. Doing it once
# here, single file, means the two workers started next do not race each other
# over the same CREATE TABLE.
# --------------------------------------------------------------------------- #
say "Preparing the database schema"
sudo -u "$APP_USER" sh -c "cd \"$APP_DIR/backend\" && .venv/bin/python -c 'import app.main'"

# --------------------------------------------------------------------------- #
# 9. systemd
# --------------------------------------------------------------------------- #
say "Installing the systemd service"
sed -e "s|@APP_DIR@|$APP_DIR|g" \
    -e "s|@APP_USER@|$APP_USER|g" \
    -e "s|@API_PORT@|$API_PORT|g" \
    -e "s|@WORKERS@|$WORKERS|g" \
    "$APP_DIR/deploy/bd-dispatch.service" > /etc/systemd/system/bd-dispatch.service
systemctl daemon-reload
systemctl enable bd-dispatch >/dev/null
systemctl restart bd-dispatch

# --------------------------------------------------------------------------- #
# 10. nginx, so the link has no port number in it
# --------------------------------------------------------------------------- #
say "Putting nginx in front"
sed -e "s|@API_PORT@|$API_PORT|g" -e "s|@HTTP_PORT@|$HTTP_PORT|g" \
    "$APP_DIR/deploy/nginx-bd-dispatch.conf" > /etc/nginx/sites-available/bd-dispatch
ln -sf /etc/nginx/sites-available/bd-dispatch /etc/nginx/sites-enabled/bd-dispatch
rm -f /etc/nginx/sites-enabled/default
nginx -t >/dev/null
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx

# --------------------------------------------------------------------------- #
# 11. Firewall, and a name on the network
# --------------------------------------------------------------------------- #
if ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow "$HTTP_PORT/tcp" >/dev/null || true
fi
hostnamectl set-hostname "$HOSTNAME_LOCAL" >/dev/null 2>&1 || true
systemctl enable --now avahi-daemon >/dev/null 2>&1 || true

# --------------------------------------------------------------------------- #
# Done
# --------------------------------------------------------------------------- #
IP="$(hostname -I | awk '{print $1}')"
SUFFIX=""
[ "$HTTP_PORT" = "80" ] || SUFFIX=":$HTTP_PORT"

sleep 3
if curl -fsS "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then
  HEALTH="answering"
else
  HEALTH="NOT answering -- run: journalctl -u bd-dispatch -n 50"
fi

cat <<DONE

  ------------------------------------------------------------------
  Dispatch is installed. The API is $HEALTH.

  Give your BDs this link:

      http://$IP$SUFFIX
      http://$HOSTNAME_LOCAL.local$SUFFIX   (same thing, easier to type)

  Nothing leaves this machine. There is no account anywhere else.

  Next, one of these:

    Bring your Neon data over
        sudo bash $APP_DIR/deploy/migrate-from-neon.sh "postgresql://...neon..."

    Or start empty, with one manager account
        sudo bash $APP_DIR/deploy/create-manager.sh you@yourcompany.com

  Day to day:
        systemctl status bd-dispatch          is it running
        journalctl -u bd-dispatch -f          watch the log
        sudo bash $APP_DIR/deploy/update.sh   after you change the code
        sudo bash $APP_DIR/deploy/backup.sh   a copy of the database
  ------------------------------------------------------------------

DONE
