#!/usr/bin/env bash
#
# Copy everything out of Neon and into the PostgreSQL on this machine.
#
#     sudo bash deploy/migrate-from-neon.sh "postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require"
#
# The connection string is the one in your old backend/.env on Windows. Quote
# it -- it contains characters the shell would otherwise eat.
#
# Nothing is written to Neon. This only reads. If it goes wrong you still have
# the hosted copy exactly as it was, and you can run this again.
#
# What it does:
#   1. dumps schema and data from Neon to a file on this machine
#   2. keeps a dump of the local database first, if it has anything in it
#   3. drops and recreates the local schema, then restores the Neon dump into it
#   4. counts the rows on both sides and tells you whether they agree

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/bd-dispatch}"
APP_USER="${APP_USER:-dispatch}"
DB_NAME="${DB_NAME:-dispatch}"
DB_USER="${DB_USER:-dispatch}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/bd-dispatch}"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mx  %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this with sudo."

SOURCE_URL="${1:-}"
if [ -z "$SOURCE_URL" ]; then
  cat >&2 <<USAGE

  Give it the Neon connection string, in quotes:

      sudo bash $0 "postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require"

  It is the DATABASE_URL line in your old backend/.env.

USAGE
  exit 1
fi

# The app's own URL form is postgresql+psycopg2://, which is SQLAlchemy's
# spelling and not something libpq understands. Strip it if it is there.
SOURCE_URL="${SOURCE_URL/postgresql+psycopg2:\/\//postgresql://}"
SOURCE_URL="${SOURCE_URL/postgres:\/\//postgresql://}"

command -v pg_dump >/dev/null || die "pg_dump is not installed. Run deploy/install.sh first."

# --------------------------------------------------------------------------- #
# Can we reach Neon at all, and is our pg_dump new enough to read it?
# --------------------------------------------------------------------------- #
say "Checking the connection to Neon"
REMOTE_VERSION="$(psql "$SOURCE_URL" -tAc "SHOW server_version_num" 2>/dev/null)" \
  || die "Could not connect. Check the string, and that this server has internet access right now."
REMOTE_MAJOR=$(( REMOTE_VERSION / 10000 ))
LOCAL_MAJOR="$(pg_dump --version | sed 's/.* \([0-9]*\)\..*/\1/')"
echo "    Neon is PostgreSQL $REMOTE_MAJOR; pg_dump here is $LOCAL_MAJOR."
if [ "$LOCAL_MAJOR" -lt "$REMOTE_MAJOR" ]; then
  die "pg_dump $LOCAL_MAJOR cannot read a PostgreSQL $REMOTE_MAJOR server.
   Install the matching client and run this again:
       sudo apt-get install -y postgresql-client-$REMOTE_MAJOR"
fi

# --------------------------------------------------------------------------- #
# Keep a copy of whatever is here now, before touching it
# --------------------------------------------------------------------------- #
STAMP="$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$BACKUP_DIR"

PRE_DUMP=""
LOCAL_TABLES="$(sudo -u postgres psql -tAd "$DB_NAME" -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
if [ "${LOCAL_TABLES:-0}" -gt 0 ]; then
  say "Saving what is already in the local database"
  PRE_DUMP="$BACKUP_DIR/before-neon-import-$STAMP.dump"
  sudo -u postgres pg_dump -Fc "$DB_NAME" > "$PRE_DUMP"
  echo "    $PRE_DUMP"
fi

# --------------------------------------------------------------------------- #
# Pull it down
# --------------------------------------------------------------------------- #
DUMP="$BACKUP_DIR/neon-$STAMP.sql"
say "Dumping Neon (this is the slow part)"
# --no-owner and --no-privileges: Neon's role names do not exist here, and
# without these every GRANT and ALTER OWNER in the dump fails on restore.
pg_dump "$SOURCE_URL" \
  --no-owner --no-privileges --no-acl \
  --schema=public \
  --file="$DUMP"
echo "    $(du -h "$DUMP" | cut -f1) written to $DUMP"

# --------------------------------------------------------------------------- #
# Restore
# --------------------------------------------------------------------------- #
say "Stopping the app while the database is swapped"
systemctl stop bd-dispatch 2>/dev/null || true

# Whatever happens from here -- a failed restore, a Ctrl-C, a dropped SSH
# session -- the app comes back up. Leaving the team staring at a dead link
# because a migration went sideways is the one outcome worth ruling out.
restart_app() {
  systemctl start bd-dispatch 2>/dev/null || true
}
trap restart_app EXIT

say "Restoring into the local database"
sudo -u postgres psql -q -d "$DB_NAME" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
sudo -u postgres psql -q -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER; GRANT ALL ON SCHEMA public TO postgres;"

RESTORE_LOG="$BACKUP_DIR/restore-$STAMP.log"
if sudo -u postgres psql -v ON_ERROR_STOP=1 -q -d "$DB_NAME" -f "$DUMP" > "$RESTORE_LOG" 2>&1; then
  echo "    restored cleanly"
else
  warn "The restore reported errors. The log is at $RESTORE_LOG"
  tail -20 "$RESTORE_LOG" >&2
  echo >&2
  echo "  Your Neon database is untouched -- this only ever read from it." >&2
  if [ -n "$PRE_DUMP" ]; then
    echo "  The local database was emptied to make room. Put back what was here:" >&2
    echo "      sudo systemctl stop bd-dispatch" >&2
    echo "      sudo -u postgres pg_restore --clean --if-exists -d $DB_NAME $PRE_DUMP" >&2
    echo "      sudo systemctl start bd-dispatch" >&2
  fi
  die "Stopped without importing anything."
fi

# Everything arrived owned by postgres. Hand it to the account the app uses.
say "Handing the tables to $DB_USER"
sudo -u postgres psql -q -d "$DB_NAME" <<SQL
DO \$\$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO $DB_USER', r.tablename);
  END LOOP;
  FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER SEQUENCE public.%I OWNER TO $DB_USER', r.sequencename);
  END LOOP;
END \$\$;
SQL

# --------------------------------------------------------------------------- #
# Did it all arrive?
# --------------------------------------------------------------------------- #
say "Counting both sides"
printf '    %-22s %10s %10s\n' "table" "Neon" "here"
DISAGREE=0
# Ask the source which tables exist rather than naming them here. A hard-coded
# list goes stale the moment a table is added, and quietly stops checking it.
TABLES="$(psql "$SOURCE_URL" -tAc \
  "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")"
for TABLE in $TABLES; do
  REMOTE=$(psql "$SOURCE_URL" -tAc "SELECT count(*) FROM public.\"$TABLE\"" 2>/dev/null || echo "?")
  LOCAL=$(sudo -u postgres psql -tAd "$DB_NAME" -c "SELECT count(*) FROM public.\"$TABLE\"" 2>/dev/null || echo "?")
  MARK=""
  if [ "$REMOTE" != "$LOCAL" ]; then MARK="  <-- differs"; DISAGREE=1; fi
  printf '    %-22s %10s %10s%s\n' "$TABLE" "$REMOTE" "$LOCAL" "$MARK"
done

# --------------------------------------------------------------------------- #
# Let the app add anything the running code expects and the dump did not have
# --------------------------------------------------------------------------- #
say "Applying any schema upgrades the current code expects"
sudo -u "$APP_USER" sh -c "cd \"$APP_DIR/backend\" && .venv/bin/python -c 'import app.main'"

say "Starting the app"
trap - EXIT
systemctl start bd-dispatch
sleep 3
curl -fsS "http://127.0.0.1:${API_PORT:-8000}/api/health" >/dev/null 2>&1 \
  && echo "    the API is answering" \
  || warn "the API is not answering -- journalctl -u bd-dispatch -n 50"

IP="$(hostname -I | awk '{print $1}')"
cat <<DONE

  ------------------------------------------------------------------
  $( [ "$DISAGREE" -eq 0 ] && echo "Every table matches. The data is here." \
                           || echo "Some counts differ -- read the table above before you trust this." )

  Sign in at http://$IP with the same email and password you used before.
  Passwords came across with everything else; nobody needs a new one.

  Neon still has its copy. Leave it a week, check the app does what you
  expect, and only then delete it.

  The dump is kept at $DUMP
  ------------------------------------------------------------------

DONE
