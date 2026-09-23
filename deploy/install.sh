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
# Renaming the machine is opt-in: it is somebody's server before it is ours.
#     sudo HOSTNAME_LOCAL=dispatch bash deploy/install.sh   -> http://dispatch.local
HOSTNAME_LOCAL="${HOSTNAME_LOCAL:-}"
NODE_MAJOR="${NODE_MAJOR:-22}"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mx  %s\033[0m\n' "$*" >&2; exit 1; }

# shellcheck source=deploy/lib.sh
. "$SRC_DIR/deploy/lib.sh"

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

# The version matters: pg_dump can read a server older than itself but never a
# newer one, and Neon runs a recent major. So a server that is already here and
# at least $PG_VERSION is used as it is -- installing a second major beside it
# would start a second cluster on 5433 while the app points at 5432. Only when
# there is none, or it is too old, does PGDG get involved.
INSTALLED_PG="$(pg_lsclusters -h 2>/dev/null | awk '$2 == "main" {print $1}' | sort -n | tail -1)"
if [ -n "$INSTALLED_PG" ] && [ "$INSTALLED_PG" -ge "$PG_VERSION" ]; then
  PG_VERSION="$INSTALLED_PG"
  say "Using the PostgreSQL $PG_VERSION already on this machine"
else
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

# Node builds the browser app and is not needed to run it. One the owner of
# this checkout already has -- in their ~/.nvm or on the PATH -- is used as it
# is (see lib.sh). Only when there is none is the distro's installed.
if ! find_node_dir >/dev/null; then
  DISTRO_NODE="$(apt-cache policy nodejs 2>/dev/null | awk '/Candidate:/ {print $2}' | sed 's/^[0-9]*://; s/\..*//')"
  if [ -n "$DISTRO_NODE" ] && [ "$DISTRO_NODE" -ge "$NODE_MAJOR" ] 2>/dev/null; then
    say "Installing Node $DISTRO_NODE from the distro"
    apt-get install -y -qq nodejs npm >/dev/null
  else
    say "Installing Node $NODE_MAJOR from NodeSource"
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - >/dev/null
    apt-get install -y -qq nodejs >/dev/null
  fi
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
rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$SRC_DIR/" "$APP_DIR/"
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
  # Both values are URL-safe base64, so neither can contain the | delimiter.
  sed -e "s|^DATABASE_URL=.*|DATABASE_URL=$DATABASE_URL|" \
      -e "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" \
      "$SRC_DIR/deploy/.env.production.example" > "$ENV_FILE"
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
build_frontend

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
render_nginx

# --------------------------------------------------------------------------- #
# 11. Firewall, and a name on the network
# --------------------------------------------------------------------------- #
if ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow "$HTTP_PORT/tcp" >/dev/null || true
fi
if [ -n "$HOSTNAME_LOCAL" ]; then
  hostnamectl set-hostname "$HOSTNAME_LOCAL" >/dev/null 2>&1 || true
fi
HOSTNAME_LOCAL="$(hostname -s)"
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
        sudo bash $APP_DIR/deploy/migrate-from-neon.sh /path/to/old.env

    Or start empty, with one manager account
        sudo bash $APP_DIR/deploy/create-manager.sh you@yourcompany.com

  Day to day:
        systemctl status bd-dispatch          is it running
        journalctl -u bd-dispatch -f          watch the log
        sudo bash $APP_DIR/deploy/update.sh   after you change the code
        sudo bash $APP_DIR/deploy/backup.sh   a copy of the database
  ------------------------------------------------------------------

DONE
