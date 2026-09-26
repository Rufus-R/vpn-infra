# S_RU working configuration — snapshot before reinstall (2026-09-25)

This is a snapshot of the S_RU (31.77.169.67) setup as of 2026-09-25, taken
before the planned reinstall/migration to a multi-node 3x-ui architecture.
Keep this alongside `commercial/deployment.md` and `commercial/known-issues.md`.

## Reality inbound (VLESS)

- Port: 443/tcp
- `dest`: `www.cloudflare.com:443` (changed from `ozon.ru:443` on 2026-09-25 —
  Megafon was blocking the TLS handshake by SNI for `ozon.ru` and `vk.com`;
  `www.cloudflare.com`, `www.microsoft.com`, `yandex.ru`, `example.com` were
  not blocked at the time of testing)
- `serverNames`: `["www.cloudflare.com"]`
- `publicKey` (pbk): `3i_6GTcRKvpAKjgvLHI7jUUlEqnOpCT1iPElZe1U6zU`
- `shortId` (sid): `9cde9e28846816db`
- `fingerprint`: `chrome`
- Test client UUID: `c57c081e-a689-47a2-bd28-9f68af09d81e`

**Decision (2026-09-25):** generate a fresh Reality key pair on the new
3x-ui panel rather than carrying over the old private key. The subscription
domain is moving to the new panel server anyway, so the client link changes
regardless — there's no benefit to preserving the old key pair, and it
avoids handling a private key in transit during the migration.

## AmneziaWG

- Installed via the Amnezia desktop/mobile app (self-hosted target), using a
  temporary SSH key that was added to and later removed from
  `/root/.ssh/authorized_keys`.
- Runs as Docker container `amnezia-awg2`, UDP 443 (`0.0.0.0:443->443/udp`).
- Confirmed working over Megafon; exit IP was S_RU's own IP
  (31.77.169.67) — no EU/geo-split egress, since AmneziaWG's traffic
  doesn't pass through the Xray `to-eu` outbound.
- Treated as a backup channel, not a replacement for Reality.

## Marzban panel + subscription (external HTTPS access)

- Domain: `netru.ru.net`, registered separately from `maximum.ru.net`
  (deliberately kept unlinked from the personal domain / S1 infrastructure).
- DNS: A record at the registrar → `31.77.169.67` (not moved to Cloudflare).
- TLS cert: Let's Encrypt via `certbot certonly --standalone -d netru.ru.net
  --register-unsafely-without-email` (HTTP-01 challenge, port 80).
  Auto-renewal via `certbot.timer`.
- `/opt/marzban/.env`:
  - `UVICORN_HOST = "0.0.0.0"`
  - `UVICORN_PORT = 2096`
  - `UVICORN_SSL_CERTFILE = "/etc/letsencrypt/live/netru.ru.net/fullchain.pem"`
  - `UVICORN_SSL_KEYFILE = "/etc/letsencrypt/live/netru.ru.net/privkey.pem"`
- `/opt/marzban/docker-compose.yml`: added
  `- /etc/letsencrypt:/etc/letsencrypt:ro` under `volumes:`.
- **Important finding:** Marzban forces `UVICORN_HOST` back to `127.0.0.1`
  in code unless a *publicly-trusted* SSL cert is configured — a self-signed
  cert is explicitly rejected too. External access is not possible without a
  real domain + Let's Encrypt (or another public CA) cert.
- **Important finding:** after editing `.env` or `docker-compose.yml`,
  `docker compose restart marzban` is NOT enough — env vars are only
  re-read on container recreation. Use `docker compose up -d marzban`.
- Confirmed working: valid TLS, dashboard reachable externally, and
  client-side subscription auto-update confirmed working (Hiddify).
- Port 2096 chosen arbitrarily (mobile-operator-friendly guess, unverified
  as a rule); ufw rule `2096/tcp` added.

## Cleanup done on S_RU

- Removed orphaned `xray-test` container (created 2026-09-18, `host`
  network mode, was likely holding `1080/udp`).
- SSH password auth confirmed disabled (key-only).

## Known open issues (unresolved as of this snapshot)

- **v2rayNG**: still doesn't reliably work for browsing (google.com,
  ozon.ru) even with the current `www.cloudflare.com` Reality config,
  despite Hiddify working fine with the same server/config over both
  MTS and Megafon. Debug logs during actual browse attempts showed proxy
  dial entries but no explicit handshake failure — root cause not found.
  Xray-core version mismatch (client 26.6.27 vs. server 24.12.31,
  including newer PQ key-exchange behavior in Reality) is an untested
  hypothesis.
- **fail2ban**: `fail2ban-client status` returned a socket error
  ("Is fail2ban running?") — likely not running, despite being expected
  active per earlier docs. Not yet investigated.

## New commercial architecture — Panel server (2026-09-25)

A separate, dedicated VPS was ordered for the panel role:

- Domain: `netru.ru.net` — to be repointed here from S_RU (was
  `31.77.169.67`, now `31.77.173.218`)
- IP: `31.77.173.218`
- OS: Ubuntu 24.04
- Spec: 1 vCPU (Intel E5), 768 MiB RAM, 10 GiB SSD, 5120 GiB traffic —
  94.50 RUB/month. Chosen deliberately minimal: the panel does not proxy
  client VPN traffic itself, only serves the web UI, subscriptions, and
  manages remote nodes.
- Role: 3x-ui panel — hosts the user database, subscription server, and
  the Telegram bot (management/notifications).
- S_RU (31.77.169.67) is planned to become a **pure entry node**, managed
  from this panel via 3x-ui's multi-node feature, once migrated off
  Marzban. See "Decision (2026-09-25)" above re: fresh Reality keys for
  this migration rather than reusing the old key pair.

**To do on this new server:** repeat the certbot HTTP-01 flow for
`netru.ru.net` → `31.77.173.218` (the existing cert is bound to the old
IP and won't validate here), update the DNS A record at the registrar,
install 3x-ui, and set up the Telegram bot integration.


- Decided to evaluate migrating from Marzban to **3x-ui** (`MHSanaei/3x-ui`,
  the mainline project — not an unverified fork) for unified Reality +
  built-in AmneziaWG management under one panel/user base, with native
  multi-node support (a central panel managing separate remote entry/exit
  nodes).
- Plan: a separate, deliberately cheap VPS to run the 3x-ui **panel only**
  (no proxy traffic through it); S_RU (or its replacement) becomes a
  **pure entry node** managed from that panel.
- 3x-ui's own README/disclaimer states the project is intended for
  "personal learning" and explicitly says not to use it in production —
  worth weighing before committing it to commercial use.
