# Версии ПО и ресурсы серверов

## Серверы

| Параметр | S1 | S2 |
|---------|-----|-----|
| **IP** | `194.55.236.229` | `77.105.161.151` |
| **Hostname** | `maximum.ru.net` | `211547.landvps.online` |
| **ОС** | Ubuntu 24.04 | Ubuntu 24.04 |
| **Ядро** | `6.8.0-136-generic` | `6.8.0-136-generic` |
| **RAM** | 961 MiB (378 used) | 709 MiB (265 used) |
| **Диск** | 9.8 GB (60% used) | 9.8 GB (58% used) |
| **Swap** | 511 MiB (28 used) | 511 MiB (55 used) |
| **Аптайм** | 12+ дней | 12+ дней |

## Версии ПО

| Компонент | S1 | S2 |
|-----------|-----|-----|
| OpenVPN | 2.6.19 | 2.6.19 |
| Easy-RSA | 3.1.7-2 | 3.1.7-2 |
| Docker | 29.6.0 | 29.6.0 |
| Docker Compose | v5.1.4 | v5.1.4 |
| Python | 3.12.3 | 3.12.3 |
| Gunicorn | 26.0.0 | — |
| Flask | установлен в venv | — |
| Certbot | 2.9.0 | — |
| certbot-dns-cloudflare | 2.0.0 | — |
| Pi-hole | — | pihole-meta 0.7 |
| iptables | 1.8.10 | 1.8.10 |
| iptables-persistent | 1.0.20 | 1.0.20 |

## Пути к исполняемым файлам

| Бинарник | Путь |
|---------|------|
| openvpn | `/usr/sbin/openvpn` |
| easyrsa (S1) | `/etc/openvpn/server-easy-rsa/easyrsa` → `/usr/share/easy-rsa/easyrsa` |
| easyrsa (S2) | `/etc/openvpn/easy-rsa/easyrsa` → `/usr/share/easy-rsa/easyrsa` |
| gunicorn | `/opt/vpn-admin/venv/bin/gunicorn` |
| certbot | `/usr/bin/certbot` |
| docker | `/usr/bin/docker` |
