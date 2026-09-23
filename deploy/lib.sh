# Shared by install.sh and update.sh. Sourced, not run.
#
# Expects SRC_DIR, APP_DIR, APP_USER, NODE_MAJOR, and say/warn/die to be set.

# Everything that must never be copied from the checkout into $APP_DIR.
# '*.env' matters: a connection string saved as MindLox-Ai.env or similar in the
# checkout would otherwise land in /opt, readable by every account here.
# Excluded paths are also protected from --delete, which is what keeps the
# server's own backend/.env alive across updates.
RSYNC_EXCLUDES=(
  --exclude '.git' --exclude '.venv' --exclude 'node_modules'
  --exclude '__pycache__' --exclude '.pytest_cache'
  --exclude '.env' --exclude '*.env' --exclude 'backend/dispatch.db'
  --exclude 'frontend/dist' --exclude '.db-password'
)

# Node is needed only to build the browser app; it never runs in production.
#
# The build runs as whoever owns the checkout, not as $APP_USER, because the
# Node most people already have lives in their own ~/.nvm, and a home directory
# is closed to other accounts. Prints the directory holding the node binary.
BUILD_USER="$(stat -c %U "$SRC_DIR")"
BUILD_HOME="$(getent passwd "$BUILD_USER" | cut -d: -f6)"

node_major_of() { "$1" -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/'; }

find_node_dir() {
  local candidate
  # nvm first, newest version first: it is what the owner actually builds with.
  for candidate in $(ls -d "$BUILD_HOME"/.nvm/versions/node/v*/bin 2>/dev/null | sort -rV) \
                   "$(dirname "$(command -v node 2>/dev/null || echo /nonexistent/node)")"; do
    if [ -x "$candidate/node" ] && [ -x "$candidate/npm" ] \
       && [ "$(node_major_of "$candidate/node")" -ge "$NODE_MAJOR" ] 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

# Builds into a scratch directory and only then swaps it into $APP_DIR, so a
# failed build leaves the app that is running now exactly as it was.
build_frontend() {
  local node_dir out
  node_dir="$(find_node_dir)" || die "No Node $NODE_MAJOR+ found, in $BUILD_HOME/.nvm or on the PATH."
  echo "    building as $BUILD_USER with $("$node_dir/node" -v) ($node_dir)"

  out="$(mktemp -d)"
  chown "$BUILD_USER" "$out"
  sudo -u "$BUILD_USER" env PATH="$node_dir:/usr/bin:/bin" HOME="$BUILD_HOME" \
    sh -c "cd \"$SRC_DIR/frontend\" && npm ci --no-audit --no-fund && npx vite build --outDir \"$out\" --emptyOutDir" \
    || { rm -rf "$out"; die "The frontend build failed. Nothing was changed."; }
  [ -f "$out/index.html" ] || { rm -rf "$out"; die "The frontend build produced no index.html. Nothing was changed."; }

  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR/frontend/dist"
  rsync -a --delete "$out/" "$APP_DIR/frontend/dist/"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR/frontend/dist"
  rm -rf "$out"
}

# The value of KEY in an env file, without quotes or a Windows line ending.
env_value() {
  [ -f "$2" ] || return 0
  tr -d '\r' < "$2" \
    | sed -nE "s/^[[:space:]]*(export[[:space:]]+)?$1[[:space:]]*=[[:space:]]*//p" | tail -1 \
    | sed -E "s/^['\"]//; s/['\"][[:space:]]*$//"
}

# Sets KEY=VALUE in an env file: replaces the line if there is one, appends it
# if not. Leaves every other line, and the file's owner and mode, alone.
set_env_value() {
  local key="$1" value="$2" file="$3"
  if grep -qE "^[[:space:]]*#?[[:space:]]*$key=" "$file"; then
    sed -i -E "0,/^[[:space:]]*#?[[:space:]]*$key=.*/s||$key=$value|" "$file"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$file"
  fi
}

# Writes the nginx site from the templates and reloads nginx.
#
# https when backend/.env has a DOMAIN and a certificate for it exists, plain
# http otherwise. Deciding from .env every time is what lets install.sh be
# re-run without quietly dropping https: nothing edits the live config by hand,
# certbot included.
render_nginx() {
  local domain env_file="$APP_DIR/backend/.env"
  domain="$(env_value DOMAIN "$env_file")"

  # Kept so a config nginx refuses can be put back. A rejected file left in
  # place would not break the running nginx, but it would stop the next boot.
  local site=/etc/nginx/sites-available/bd-dispatch snip=/etc/nginx/snippets/bd-dispatch-app.conf
  local backup out
  backup="$(mktemp -d)"
  cp -a "$site" "$snip" "$backup/" 2>/dev/null || true

  install -d /var/www/letsencrypt
  sed -e "s|@API_PORT@|$API_PORT|g" \
      "$APP_DIR/deploy/nginx-bd-dispatch-app.conf" > /etc/nginx/snippets/bd-dispatch-app.conf

  if [ -n "$domain" ] && [ -f "/etc/letsencrypt/live/$domain/fullchain.pem" ]; then
    echo "    https for $domain"
    sed -e "s|@DOMAIN@|$domain|g" \
        "$APP_DIR/deploy/nginx-bd-dispatch-ssl.conf" > /etc/nginx/sites-available/bd-dispatch
  else
    if [ -n "$domain" ]; then
      warn "DOMAIN=$domain is set but there is no certificate for it yet. Serving plain http."
      warn "Run: sudo bash $APP_DIR/deploy/enable-https.sh"
    fi
    sed -e "s|@HTTP_PORT@|$HTTP_PORT|g" \
        "$APP_DIR/deploy/nginx-bd-dispatch.conf" > /etc/nginx/sites-available/bd-dispatch
  fi

  ln -sf /etc/nginx/sites-available/bd-dispatch /etc/nginx/sites-enabled/bd-dispatch
  rm -f /etc/nginx/sites-enabled/default
  if ! out="$(nginx -t 2>&1)"; then
    echo "$out" >&2
    rm -f "$site" "$snip"
    [ -f "$backup/bd-dispatch" ] && cp -a "$backup/bd-dispatch" "$site"
    [ -f "$backup/bd-dispatch-app.conf" ] && cp -a "$backup/bd-dispatch-app.conf" "$snip"
    rm -rf "$backup"
    die "nginx rejected the new config. The previous one is back in place and still running."
  fi
  rm -rf "$backup"
  systemctl enable nginx >/dev/null 2>&1 || true
  systemctl reload nginx
}
