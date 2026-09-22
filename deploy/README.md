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
  24.04. A mini-PC, an old desktop or a VM all work — this is a small app for a
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

## 4. Bring your data over from Neon

Your current `backend/.env` on Windows points at Neon. The connection string in
it is what this needs — quote it, because it contains characters the shell
would otherwise eat:

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

```bash
sudo systemctl stop bd-dispatch
sudo -u postgres pg_restore --clean --if-exists -d dispatch /var/backups/bd-dispatch/dispatch-YYYYMMDD-HHMMSS.dump
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
| `migrate-from-neon.sh` | Copies Neon into the local database and checks the counts. |
| `create-manager.sh` | The first manager account, when starting empty. |
| `update.sh` | Ship a code change. Backs up first, refuses to break the running app. |
| `backup.sh` | One dump. Run by the nightly timer, or by hand. |
| `bd-dispatch.service` | The systemd unit. Restarts on crash, starts on boot. |
| `nginx-bd-dispatch.conf` | Port 80, upload size, timeouts, asset caching. |
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
`/etc/nginx/sites-available/bd-dispatch` and `sudo systemctl reload nginx`.

---

## A word on HTTPS

This runs over plain HTTP. On a network you control, between machines you own,
that is a reasonable place to stop — and it is why the app is not exposed to
the internet.

It is worth knowing what you are accepting: sign-in tokens are in
`sessionStorage` and travel in the clear, so anyone who can watch traffic on
your LAN can take one. On an office network with a password on the wifi, that
is a small risk. On shared or public wifi it is not.

If you want it closed anyway, the two ways that work on a local network are a
certificate from your own internal CA, or a real domain with a DNS-01
Let's Encrypt certificate pointed at the private IP. Both are an afternoon's
work and neither requires exposing the server. Ask when you want to do it.

**Do not port-forward this to the internet.** If people need it from outside
the office, put them on a VPN (WireGuard or Tailscale) — the server stays
exactly as it is, and the link keeps working unchanged.
