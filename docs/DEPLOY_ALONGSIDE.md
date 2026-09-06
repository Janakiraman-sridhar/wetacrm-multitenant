# Deploying WeTa CRM next to an existing app on the same VPS

This guide deploys WeTa CRM on a server that **already** runs another application
behind a dockerized nginx on ports 80/443 (e.g. the Contabo VPS serving
`https://wetano-chatbot.wetano.com/chatbot/admin`) — **without touching the
existing app**.

How it works:

```
Internet ──► existing nginx container (still owns ports 80/443)
               ├── wetano-chatbot.wetano.com  → existing app   (unchanged)
               └── crm.wetano.com             → weta-crm-gateway (CRM, internal only)
```

The CRM stack publishes **no host ports**. Its internal gateway container
(`weta-crm-gateway`) serves the frontend and routes `/api` + `/ws`; the existing
nginx reaches it by container name over a shared Docker network.

---

## 1. DNS

Add an **A record** in the `wetano.com` zone:

```
crm.wetano.com  →  <your VPS IP>
```

## 2. Clone and configure

```bash
git clone https://github.com/Janakiraman-sridhar/WeTa-CRM.git /opt/weta-crm
cd /opt/weta-crm
cp docker/.env.example .env
nano .env
```

In `.env`, change **every** `change-me` value and set:

```
CORS_ORIGINS=https://crm.wetano.com
```

## 3. Start the CRM stack

```bash
cd /opt/weta-crm
docker compose -f docker-compose.contabo.yml up -d --build
```

Nothing binds host ports, so the existing app is unaffected. Check:

```bash
docker compose -f docker-compose.contabo.yml ps
```

> **Small VPS?** `meilisearch`, `minio`, `worker` and `beat` are optional. Delete
> those services from the compose file (and the `MEILI_*` / `MINIO_*` env lines
> on `backend`) — the CRM falls back to SQL search, local-disk uploads and
> inline background jobs.

## 4. Let the existing nginx reach the CRM

The CRM's network is named `weta-crm` and is attachable.

**Quick way** (must be repeated if the nginx container is ever *recreated*):

```bash
docker network connect weta-crm <existing-nginx-container-name>
```

**Durable way (recommended)** — in the *existing project's* `docker-compose.yml`,
add the network to its nginx service:

```yaml
services:
  nginx:                      # ← whatever the existing nginx service is called
    networks:
      - default
      - weta-crm

networks:
  weta-crm:
    external: true
```

then `docker compose up -d nginx` in that project (recreates only its nginx).

Sanity check — this must print `{"status":"ok","app":"WeTa CRM"}`:

```bash
docker exec <existing-nginx-container-name> curl -s http://weta-crm-gateway/health
```

## 5. Add the server block to the existing nginx

Create a new conf file in the existing nginx's config directory (wherever its
other server blocks live, e.g. `conf.d/crm.wetano.com.conf`):

```nginx
# --- HTTP: ACME challenges + redirect to HTTPS ---
server {
    listen 80;
    server_name crm.wetano.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;          # match the existing certbot webroot
    }
    location / {
        return 301 https://$host$request_uri;
    }
}

# --- HTTPS: proxy everything to the CRM gateway ---
server {
    listen 443 ssl http2;
    server_name crm.wetano.com;

    ssl_certificate     /etc/letsencrypt/live/crm.wetano.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crm.wetano.com/privkey.pem;

    client_max_body_size 30m;

    # Socket.IO needs the websocket upgrade headers
    location /ws/ {
        proxy_pass http://weta-crm-gateway;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    location / {
        proxy_pass http://weta-crm-gateway;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 6. Issue the TLS certificate

Use the **same certbot flow the existing app uses**. With the common
webroot setup that is:

```bash
# reload nginx first so the port-80 server block (ACME location) is live —
# comment out the 443 server block until the cert exists, or use this order:
docker exec <existing-nginx-container-name> nginx -s reload

docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d crm.wetano.com
# (run from the EXISTING project's directory, using its certbot service)

docker exec <existing-nginx-container-name> nginx -s reload
```

The existing cert-renewal cron/loop will renew `crm.wetano.com` along with the
other certificates since it lives in the same `/etc/letsencrypt` volume.

## 7. First login

Open `https://crm.wetano.com` and sign in with the seeded Super Admin
(`ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`). **Change the password
immediately** in Settings → Users.

## Verify nothing was disturbed

```bash
curl -sI https://wetano-chatbot.wetano.com/chatbot/admin | head -1   # existing app still up
curl -sI https://crm.wetano.com | head -1                            # CRM up
```

In the CRM, the bell icon connecting without console errors confirms the
websocket (`/ws`) proxying works.

## Updating the CRM later

```bash
cd /opt/weta-crm
git pull
docker compose -f docker-compose.contabo.yml up -d --build
```

## Removing the CRM (existing app untouched)

```bash
cd /opt/weta-crm
docker compose -f docker-compose.contabo.yml down        # stop containers
docker compose -f docker-compose.contabo.yml down -v     # ALSO delete CRM data
```

Then delete the `crm.wetano.com` server block and reload the existing nginx.

## Resource footprint

The full stack uses roughly **1–1.5 GB RAM** (Postgres ~150–300 MB,
Meilisearch ~150 MB, MinIO ~100 MB, API + worker + beat ~400 MB, the rest
small). Trim optional services (step 3 note) if the VPS is tight.
