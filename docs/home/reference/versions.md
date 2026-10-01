# Версии ПО и ресурсы серверов

## Серверы

Ядро проверено 01.10.2026; RAM, диск, swap и аптайм — на момент создания файла, не обновлялись.

| Параметр | S1 | S2 |
|---------|-----|-----|
| **IP** | `194.55.236.229` | `77.105.161.151` |
| **Hostname** | `maximum.ru.net` | `211547.landvps.online` |
| **ОС** | Ubuntu 24.04 | Ubuntu 24.04 |
| **Ядро** | `6.8.0-139-generic` | `6.8.0-142-generic` |
| **RAM** | 961 MiB (378 used) | 709 MiB (265 used) |
| **Диск** | 9.8 GB (60% used) | 9.8 GB (58% used) |
| **Swap** | 511 MiB (28 used) | 511 MiB (55 used) |
| **Аптайм** | 12+ дней | 12+ дней |

## Версии ПО

| Компонент | S1 | S2 |
|-----------|-----|-----|
| OpenVPN | 2.6.19 | 2.6.19 |
| Easy-RSA | 3.1.7-2 | 3.1.7-2 |
| Docker | 29.6.0 | — (удалён 01.10.2026) |
| Docker Compose | v5.1.4 | — (удалён 01.10.2026) |
| Python | 3.12.3 | 3.12.3 |
| Gunicorn | 26.0.0 | — |
| Flask | установлен в venv | — |
| Certbot | 2.9.0 | — |
| certbot-dns-cloudflare | 2.0.0 | — |
| Pi-hole | — | pihole-meta 0.7 |
| iptables | 1.8.10 | 1.8.10 |
| iptables-persistent | 1.0.20 | — (удалён 01.10.2026) |
| ufw | — (не обнаружен) | 0.36.2 |

## Пути к исполняемым файлам

| Бинарник | Путь |
|---------|------|
| openvpn | `/usr/sbin/openvpn` |
| easyrsa (S1) | `/etc/openvpn/server-easy-rsa/easyrsa` → `/usr/share/easy-rsa/easyrsa` |
| easyrsa (S2) | `/etc/openvpn/easy-rsa/easyrsa` → `/usr/share/easy-rsa/easyrsa` |
| gunicorn | `/opt/vpn-admin/venv/bin/gunicorn` |
| certbot | `/usr/bin/certbot` |
| docker | `/usr/bin/docker` |
