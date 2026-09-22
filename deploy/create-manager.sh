#!/usr/bin/env bash
#
# Create the first manager account, on a database that has none.
#
#     sudo bash deploy/create-manager.sh you@yourcompany.com
#
# You are asked for a password; it is not echoed and not stored anywhere but
# the database, hashed. Sign in with it and change it from inside the app.
#
# This does nothing if a manager already exists -- it cannot bring back an
# account you deliberately deleted, and it cannot be used to grab an existing
# system. It leans on bootstrap_admin() in app/main.py, which has that rule
# built into it.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/bd-dispatch}"
APP_USER="${APP_USER:-dispatch}"

die() { printf '\n\033[1;31mx  %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this with sudo."

EMAIL="${1:-}"
[ -n "$EMAIL" ] || die "Usage: sudo bash $0 you@yourcompany.com"

printf 'Password for %s (at least 8 characters, not shown): ' "$EMAIL"
read -rs PASSWORD; echo
printf 'Again: '
read -rs PASSWORD2; echo
[ "$PASSWORD" = "$PASSWORD2" ] || die "Those did not match."
[ "${#PASSWORD}" -ge 8 ] || die "That is shorter than 8 characters."

printf 'Their name [Manager]: '
read -r NAME
NAME="${NAME:-Manager}"

sudo -u "$APP_USER" \
  ADMIN_EMAIL="$EMAIL" ADMIN_PASSWORD="$PASSWORD" ADMIN_NAME="$NAME" \
  sh -c "cd \"$APP_DIR/backend\" && .venv/bin/python -c 'import app.main'"

IP="$(hostname -I | awk '{print $1}')"
cat <<DONE

  Done, unless a manager already existed -- in which case nothing changed
  and the line above said nothing about creating one.

  Sign in at http://$IP with $EMAIL

DONE
