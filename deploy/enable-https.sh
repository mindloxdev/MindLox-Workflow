#!/usr/bin/env bash
#
# Put Dispatch on https at a real domain, with a Let's Encrypt certificate
# that renews itself.
#
#     sudo bash deploy/enable-https.sh server.mindlox.io you@example.com
#
# Both arguments are remembered in backend/.env (DOMAIN, CERTBOT_EMAIL), so
# after the first time a bare re-run is enough:
#
#     sudo bash deploy/enable-https.sh
#
# The email is optional, and only used by Let's Encrypt to warn you if a
# certificate is about to expire without having renewed.
#
# What has to be true first -- this checks, but cannot fix, either:
#   1. The domain's DNS A record points at this network's public IP.
#   2. The router forwards TCP 80 and 443 to this machine. Let's Encrypt proves
#      you own the domain by fetching a file over port 80, from the internet.
#
# Safe to run again. It leaves a valid certificate alone until it is close to
# expiring, and install.sh keeps https on when it is re-run, because both read
# DOMAIN from backend/.env.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/bd-dispatch}"
APP_USER="${APP_USER:-dispatch}"
API_PORT="${API_PORT:-8000}"
HTTP_PORT=80        # certbot's check always arrives on 80
NODE_MAJOR="${NODE_MAJOR:-22}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEBROOT=/var/www/letsencrypt

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mx  %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this with sudo."
# shellcheck source=deploy/lib.sh
. "$SRC_DIR/deploy/lib.sh"

ENV_FILE="$APP_DIR/backend/.env"
[ -f "$ENV_FILE" ] || die "$ENV_FILE is not there. Run deploy/install.sh first."
[ -f "$APP_DIR/deploy/nginx-bd-dispatch-ssl.conf" ] \
  || die "$APP_DIR has no https template yet. Run deploy/update.sh (or install.sh) first."

DOMAIN="${1:-$(env_value DOMAIN "$ENV_FILE")}"
EMAIL="${2:-$(env_value CERTBOT_EMAIL "$ENV_FILE")}"
[ -n "$DOMAIN" ] || die "Which domain?  sudo bash $0 server.example.com you@example.com"
case "$DOMAIN" in
  *[!a-z0-9.-]*|.*|*.|*..*) die "\"$DOMAIN\" does not look like a domain name." ;;
esac

# --------------------------------------------------------------------------- #
# Does the name point here? Only a warning: a split-horizon DNS, or a public
# IP service that is down, can make this look wrong when it is not.
# --------------------------------------------------------------------------- #
say "Checking $DOMAIN"
RESOLVED="$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}')"
PUBLIC="$(curl -fsS4 --max-time 8 https://api.ipify.org 2>/dev/null || true)"
echo "    $DOMAIN resolves to ${RESOLVED:-nothing}; this network's public IP is ${PUBLIC:-unknown}"
[ -n "$RESOLVED" ] || die "$DOMAIN does not resolve. Add an A record for it pointing at ${PUBLIC:-your public IP}."
if [ -n "$PUBLIC" ] && [ "$RESOLVED" != "$PUBLIC" ]; then
  warn "They differ. Unless you know why, fix the A record before going on."
fi

# --------------------------------------------------------------------------- #
# certbot, and a way in for it
# --------------------------------------------------------------------------- #
say "Installing certbot"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq certbot >/dev/null

if ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp  >/dev/null
  ufw allow 443/tcp >/dev/null
fi

# Remember the domain now, so render_nginx serves the challenge folder on 80
# (and, on a re-run with a certificate already here, keeps https on).
set_env_value DOMAIN "$DOMAIN" "$ENV_FILE"
set_env_value CERTBOT_EMAIL "$EMAIL" "$ENV_FILE"
chmod 600 "$ENV_FILE"
chown "$APP_USER:$APP_USER" "$ENV_FILE"

install -d "$WEBROOT/.well-known/acme-challenge"
render_nginx

# The local half of the check: nginx hands out a file from the challenge
# folder. If this fails, nothing Let's Encrypt tries can succeed either.
PROBE="probe-$(date +%s)"
echo "$PROBE" > "$WEBROOT/.well-known/acme-challenge/$PROBE"
GOT="$(curl -fsS --max-time 5 -H "Host: $DOMAIN" "http://127.0.0.1/.well-known/acme-challenge/$PROBE" 2>/dev/null || true)"
rm -f "$WEBROOT/.well-known/acme-challenge/$PROBE"
[ "$GOT" = "$PROBE" ] || die "nginx here is not serving $WEBROOT on port 80. Check: sudo nginx -t"

if [ -n "$EMAIL" ]; then
  CONTACT=(--email "$EMAIL")
else
  warn "No email given. Let's Encrypt will have no way to warn you if renewal ever stops."
  CONTACT=(--register-unsafely-without-email)
fi

CERTBOT=(certbot certonly --webroot -w "$WEBROOT" -d "$DOMAIN"
         --agree-tos --non-interactive "${CONTACT[@]}"
         --keep-until-expiring
         # Stored in the renewal config: every renewal reloads nginx, so the
         # new certificate is picked up without anyone doing anything.
         --deploy-hook "systemctl reload nginx")

# --------------------------------------------------------------------------- #
# A rehearsal against Let's Encrypt's staging server first. The real one
# allows only 5 failed attempts per hour; a port that is not forwarded yet
# would burn through them, and then even the fixed setup has to wait.
# --------------------------------------------------------------------------- #
say "Rehearsing with Let's Encrypt's staging server"
if ! "${CERTBOT[@]}" --dry-run; then
  cat >&2 <<HELP

  Let's Encrypt could not fetch the check file from http://$DOMAIN.
  Nearly always one of:

    - The router does not forward TCP 80 (and 443) to this machine,
      $(hostname -I | awk '{print $1}'). Add both port forwards in the router.
    - The ISP blocks incoming port 80. Some home connections do; ask them.
    - The A record for $DOMAIN is wrong, or has not propagated yet.

  Plain http still works on the LAN as before. Nothing else was changed.
HELP
  exit 1
fi

say "Getting the certificate"
"${CERTBOT[@]}"

say "Switching nginx to https"
render_nginx

# --------------------------------------------------------------------------- #
# Renewal. The certbot package ships a systemd timer that runs twice a day
# and renews anything within 30 days of expiry.
# --------------------------------------------------------------------------- #
say "Checking renewal"
systemctl enable --now certbot.timer >/dev/null 2>&1 || true
systemctl is-active --quiet certbot.timer \
  || die "certbot.timer is not running, so the certificate will not renew. systemctl status certbot.timer"
certbot renew --dry-run --cert-name "$DOMAIN" >/dev/null 2>&1 \
  && echo "    a rehearsed renewal succeeded" \
  || warn "A rehearsed renewal failed. Run: sudo certbot renew --dry-run"
EXPIRES="$(openssl x509 -enddate -noout -in "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" | cut -d= -f2)"

# Ask nginx here, by name, over https -- the same path a browser takes, minus
# the router.
if curl -fsS --max-time 8 --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/api/health" >/dev/null 2>&1; then
  HEALTH="answering over https"
else
  HEALTH="NOT answering over https -- journalctl -u bd-dispatch -n 50"
fi

cat <<DONE

  ------------------------------------------------------------------
  https://$DOMAIN is $HEALTH.

  The certificate expires $EXPIRES.
  certbot.timer renews it about 30 days before that, and reloads nginx.
  Check on it any time with:   systemctl list-timers certbot.timer

  http:// and the LAN address both redirect to https://$DOMAIN now.
  That is the one link to hand out, inside the office and out.
  ------------------------------------------------------------------

DONE
