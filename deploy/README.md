# Running Dispatch on your own Linux server

No hosting, no Neon, no account anywhere. One machine on your network holds the
app and the database, and your BDs open a link to it in a browser.

What each person ends up doing:

```
BD opens  http://dispatch.local   ->   your server, in your office
```

That is the whole shape of it. There is no install on their side, no VPN, and
nothing to keep signed in to.

---

## What you need

- A Linux machine on the same network as your team. Debian 12 or Ubuntu 22.04 /
  24.04 / 26.04. A mini-PC, an old desktop or a VM all work — this is a small app for a
  team of 10–15, not a busy website. 2 GB of RAM is enough; 4 GB is comfortable.
- That machine left switched on. When it sleeps, the app is gone and so are the
  rebuild timers.
- A wired connection, or at least a stable one. Everyone's browser talks to it.
- Sudo on it, and about twenty minutes.

If the machine is a VM, give it **bridged** networking, not NAT. On NAT it has
no address anyone else on the network can reach.

---

## 1. Give the server a fixed address

Do this first. Everything below hands out a link, and a link is no good if the
address moves the next time the router hands out leases.

Either reserve its IP in your router (look for "DHCP reservation" or "static
lease" next to the machine's MAC address), or set a static address on the
machine itself. Either is fine; the router is usually easier.

Find the current address with:

```bash
hostname -I
```

## 2. Get the code onto the server

```bash
git clone <your repo url> ~/bd-dispatch
cd ~/bd-dispatch
```

Or copy the folder over with `scp`/a USB stick — it does not need to be a git
checkout. If you copy it from Windows, run this once so the scripts do not
trip over Windows line endings:

```bash
sed -i 's/\r$//' deploy/*.sh
```

## 3. Install

```bash
sudo bash deploy/install.sh
```

Twenty minutes, mostly downloads. It installs PostgreSQL, Python, Node and
nginx; creates a `dispatch` account for the app to run as; generates its own
database password and `JWT_SECRET`; builds the browser app; and sets the whole
thing up as a systemd service that starts on boot and restarts if it crashes.

It prints the link to hand out when it finishes.

Run it again any time — it will not overwrite a `backend/.env` that already
exists, and it will not touch the database.

To put it somewhere else, or on a different port:

```bash
sudo APP_DIR=/srv/dispatch HTTP_PORT=8080 bash deploy/install.sh
```

It leaves the machine's name alone, so the friendly link is
`http://<its current name>.local`. To rename it to `dispatch` on the way
through, and get `http://dispatch.local`:

```bash
sudo HOSTNAME_LOCAL=dispatch bash deploy/install.sh
```

A PostgreSQL that is already installed, 17 or newer, is used as it is rather
than having a second one installed beside it.

Likewise Node: one already in the checkout owner's `~/.nvm`, or on the PATH,
22 or newer, builds the browser app. The build runs as that owner (a home
directory is closed to the `dispatch` account) into a scratch folder, and is
only swapped into `/opt` once it has succeeded.

The production `backend/.env` is written from `deploy/.env.production.example`
with a generated database password and `JWT_SECRET`. Read that file for what
each setting does.

## 4. Bring your data over from Neon

Put the old `.env` that points at Neon somewhere on the server (the repo root
is fine -- `*.env` is git-ignored and never copied into `/opt`), and hand it
to the migration. Only its `DATABASE_URL` line is read:

```bash
sudo bash deploy/migrate-from-neon.sh MindLox-Ai.env
```

Or give the connection string itself, quoted, since it contains characters the
shell would otherwise eat:

```bash
sudo bash deploy/migrate-from-neon.sh "postgresql://user:pass@ep-xxxx-pooler.region.aws.neon.tech/neondb?sslmode=require"
```

It only ever reads from Neon. It dumps everything, saves a copy of whatever is
already in the local database, restores, then counts the rows on both sides and
shows you the two columns so you can see for yourself that it all arrived.

Everyone's password comes across with everything else. Nobody needs a new one.

> Leave the Neon database alone for a week. Use the local one, confirm it does
> what you expect, and delete the hosted copy only then.

**Starting fresh instead?** Skip the migration and create the first manager:

```bash
sudo bash deploy/create-manager.sh you@yourcompany.com
```

## 5. Turn on nightly backups

Nothing is hosted now, so nobody else is keeping a copy of this for you.

```bash
sudo cp deploy/bd-dispatch-backup.service deploy/bd-dispatch-backup.timer /etc/systemd/system/
sudo systemctl enable --now bd-dispatch-backup.timer
```

A dump lands in `/var/backups/bd-dispatch` every night at 02:00 and the last 30
days are kept. **Copy them off this machine** — another PC, a NAS, a USB drive.
A backup on the same disk survives a bad import; it does not survive the disk.

## 6. Hand out the link

```
http://192.168.1.50          the address, whatever yours turns out to be
http://dispatch.local        the same thing, easier to remember
```

`dispatch.local` works on Macs, iPhones and current Windows 10/11 out of the
box. If a particular machine cannot resolve it, give that person the IP — it
always works — or add a line to your router's local DNS.

Bookmark it on each BD's machine and you are done.

---

## Living with it

```bash
systemctl status bd-dispatch       is it running
journalctl -u bd-dispatch -f       watch the log as people use it
systemctl restart bd-dispatch      turn it off and on again
sudo bash deploy/update.sh         after you change the code
sudo bash deploy/backup.sh         a dump, right now
```

`update.sh` takes a backup, copies the new code, rebuilds, applies schema
changes and restarts. It never touches `backend/.env` or the database, and it
refuses to restart if the frontend build failed — so a broken build leaves the
old version running rather than taking the team down.

### Restoring a backup

The backup folder is readable by root only, so the file is read with `sudo cat`
and piped in -- `postgres` cannot open a path in there itself.

```bash
sudo systemctl stop bd-dispatch
sudo cat /var/backups/bd-dispatch/dispatch-YYYYMMDD-HHMMSS.dump | sudo -u postgres pg_restore --clean --if-exists -d dispatch
sudo systemctl start bd-dispatch
```

---

## How it is put together

```
  browser on the LAN
        |
        |  http, port 80
        v
  nginx  ------------------------------- 127.0.0.1:8000
        (uploads up to 20 MB, 5 min timeouts,       |
         streams the workbook exports)              |
                                                    v
                                       uvicorn, 2 workers
                                       app/main.py serves BOTH:
                                         /api/*   the API
                                         /*       the built React app
                                                    |
                                                    v
                                       PostgreSQL on 127.0.0.1
```

The single-process trick is already in the code — `main.py:4250` mounts the
built frontend when `WEB_ROOT` is set. That is why there is one origin, one
port and no CORS to configure: the browser only ever talks to one thing.

The app listens on localhost only. nginx is the one thing the network can
reach, and the firewall opens one port. PostgreSQL accepts nothing from off the
machine at all.

| File | What it is |
|---|---|
| `install.sh` | The whole first-time setup. Re-runnable. |
| `lib.sh` | What install and update share: what not to copy, and the frontend build. |
| `.env.production.example` | The production settings, with what each one does. |
| `migrate-from-neon.sh` | Copies Neon into the local database and checks the counts. |
| `create-manager.sh` | The first manager account, when starting empty. |
| `enable-https.sh` | The Let's Encrypt certificate, and https at your domain. |
| `update.sh` | Ship a code change. Backs up first, refuses to break the running app. |
| `backup.sh` | One dump. Run by the nightly timer, or by hand. |
| `bd-dispatch.service` | The systemd unit. Restarts on crash, starts on boot. |
| `nginx-bd-dispatch.conf` | The plain-http site, while there is no domain. |
| `nginx-bd-dispatch-ssl.conf` | The https site: redirect on 80, TLS on 443. |
| `nginx-bd-dispatch-app.conf` | What both do with a request: upload size, timeouts, sign-in limit, caching. |
| `bd-dispatch-backup.{service,timer}` | The nightly dump. |

---

## When something is wrong

**Nobody can reach the link.** Check it works on the server itself first:

```bash
curl -I http://127.0.0.1
```

If that answers and the network does not, it is the firewall or the address:

```bash
sudo ufw status              # port 80 should be allowed
hostname -I                  # is this the address you handed out?
```

**The app will not start.**

```bash
journalctl -u bd-dispatch -n 50
```

Nearly always the database: `systemctl status postgresql`, or a `DATABASE_URL`
in `backend/.env` that no longer matches the password in `/opt/bd-dispatch/.db-password`.

**An upload is rejected at about 15 MB.** That is the app's own cap
(`MAX_UPLOAD_BYTES` in `main.py`), not nginx — nginx is set to allow 20 MB so
that the app gets to give the clearer message.

**Building a cycle times out in the browser.** nginx waits 5 minutes. If you
have genuinely outgrown that, raise `proxy_read_timeout` in
`deploy/nginx-bd-dispatch-app.conf` and run `sudo bash deploy/update.sh`.

---

## HTTPS at a real domain

Needed as soon as anyone reaches this from outside the office. It is also
worth having inside: without it, sign-in tokens cross the network in the clear.

**Before you start** -- two things only you can do:

1. **DNS.** An `A` record for the name (say `server.mindlox.io`) pointing at
   your office's public IP. `curl -4 ifconfig.me` on the server shows it.
2. **The router.** Forward TCP **80** and **443** to this server's LAN address
   (step 1 above). Let's Encrypt proves you own the domain by fetching a file
   over port 80 *from the internet*, at issue and at every renewal, so 80 has
   to stay forwarded for good -- not just the first time.

   If your router's own admin page answers on the public IP, that is what
   these forwards replace. Check that it is not also exposed some other way.

**Then:**

```bash
sudo bash deploy/update.sh                      # puts the https templates in /opt
sudo bash deploy/enable-https.sh server.mindlox.io you@yourcompany.com
```

It installs certbot, rehearses against Let's Encrypt's staging server (so a
port that is not forwarded yet does not use up the real one's 5-failures-an-hour
limit), gets the certificate, and switches nginx over. The email is optional;
Let's Encrypt uses it only to warn you if a certificate is about to expire.

What changes:

- `https://server.mindlox.io` is the link, in the office and out. `http://`,
  the LAN IP and `server.local` all redirect to it, so nobody gets a
  certificate warning for using the "wrong" address.
- `DOMAIN` and `CERTBOT_EMAIL` are written to `backend/.env`. `install.sh` and
  `update.sh` read `DOMAIN` from there and keep https on when re-run -- nothing
  edits the live nginx config by hand, certbot included.
- Sign-in is rate-limited by nginx: a burst of 5, then 10 a minute per
  address, and `429` past that. The app itself does not limit attempts.

**Renewal** is automatic. The certbot package's `certbot.timer` runs twice a
day, renews within 30 days of expiry, and reloads nginx afterwards.

```bash
systemctl list-timers certbot.timer      # when it next runs
sudo certbot certificates                # what is issued, and until when
sudo certbot renew --dry-run             # rehearse a renewal now
```

**Inside the office, the link does not load but works from a phone on
mobile data.** Your router does not do "NAT loopback" (sending the office's
own traffic for its public IP back inside). Point the name at the LAN address
in the router's local DNS -- `server.mindlox.io -> 192.168.1.99` -- or ask
whoever runs your network to.

**Going back to LAN-only:** delete the `DOMAIN=` line from `backend/.env`,
run `sudo bash deploy/update.sh`, and remove the router's port forwards.
