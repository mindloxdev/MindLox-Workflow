#!/usr/bin/env bash
#
# One compressed copy of the database.
#
#     sudo bash deploy/backup.sh
#
# Nothing is hosted any more, which means nobody else is keeping a copy of
# this for you. A dump on the same disk survives a bad import or a wrong
# button; it does not survive the disk. Copy these somewhere else -- another
# machine, a NAS, a USB drive -- or the "totally local" part is also "totally
# gone" the day that drive fails.
#
# Restore one with:
#     systemctl stop bd-dispatch
#     sudo -u postgres pg_restore --clean --if-exists -d dispatch FILE.dump
#     systemctl start bd-dispatch

set -euo pipefail

DB_NAME="${DB_NAME:-dispatch}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/bd-dispatch}"
KEEP_DAYS="${KEEP_DAYS:-30}"

[ "$(id -u)" -eq 0 ] || { echo "Run this with sudo." >&2; exit 1; }

install -d -m 700 "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="$BACKUP_DIR/$DB_NAME-$STAMP.dump"

# -Fc is the custom format: compressed, and pg_restore can pull one table out
# of it without replaying the whole thing.
sudo -u postgres pg_dump -Fc "$DB_NAME" > "$FILE"
chmod 600 "$FILE"

echo "    $(du -h "$FILE" | cut -f1)  $FILE"

# Throw away the ones older than KEEP_DAYS, but never the last one standing.
COUNT="$(find "$BACKUP_DIR" -maxdepth 1 -name "$DB_NAME-*.dump" | wc -l)"
if [ "$COUNT" -gt 1 ]; then
  find "$BACKUP_DIR" -maxdepth 1 -name "$DB_NAME-*.dump" -mtime "+$KEEP_DAYS" -delete
fi
