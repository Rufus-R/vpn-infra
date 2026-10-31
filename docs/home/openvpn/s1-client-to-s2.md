# OpenVPN: S1 как клиент к S2 — ❌ ИСТОРИЧЕСКОЕ, S2 ВЫВЕДЕН 31.10.2026

> **Документ устарел.** S2 (`77.105.161.151`) заблокирован РКН, смена IP на
> `77.105.161.66` не помогла; сервер выведен из эксплуатации навсегда.
> Актуальная схема домашнего egress: **S1 — сервер** (`openvpn-server@home-s3`,
> 8443/TCP, `tun3` 10.10.0.1), **S3 — клиент** (`openvpn-client@home-client`,
> `tun4` 10.10.0.2). См. `../architecture/overview.md`,
> `checkpoint-2026-10-31-s1-lost-during-s3-switch.md`.
> Ниже — исходная настройка клиента S2, сохранена для истории.
>
> Правки 31.10.2026: `default` таблицы `vpn` больше не задаётся скриптом
> `s2-client` (был `via 10.8.0.1 dev tun0`) — теперь его ставит `route-up` сервера
> `home-s3` (`dev tun3`).

## Файлы конфигурации (S1: 194.55.236.229)

```
/etc/openvpn/client/s2-client.conf
/etc/openvpn/client/ca.crt
/etc/openvpn/client/s1-client.crt
/etc/openvpn/client/s1-client.key
/etc/openvpn/client/ta.key
/etc/openvpn/client/route-up.sh
/etc/iproute2/rt_tables
```

## Сертификаты

Скопированы с S2 в `/etc/openvpn/client/`:
- `ca.crt` — CA сертификат S2
- `s1-client.crt` — клиентский сертификат
- `s1-client.key` — клиентский ключ
- `ta.key` — TLS-Auth ключ

Копии также хранятся в:
- `/root/s1-keys/` (на S1)
- `/root/s1-keys/` (на S2, резервная копия)

## Конфигурация клиента

Файл: `/etc/openvpn/client/s2-client.conf`

```conf
client
dev tun0
proto udp
remote 77.105.161.151 1194
resolv-retry infinite
nobind
user nobody
group nogroup
persist-key
persist-tun

ca /etc/openvpn/client/ca.crt
cert /etc/openvpn/client/s1-client.crt
key /etc/openvpn/client/s1-client.key
tls-auth /etc/openvpn/client/ta.key 1

remote-cert-tls server
verb 3

script-security 2
route-up /etc/openvpn/client/route-up.sh
```

## Скрипт policy routing

Файл: `/etc/openvpn/client/route-up.sh`

```bash
#!/bin/bash
# Маршруты для клиентов
ip rule add to 10.9.0.0/24 table main pref 110 2>/dev/null || true
ip rule add from 10.9.0.0/24 to 192.168.0.0/24 table main pref 111 2>/dev/null || true
ip rule add from 10.9.0.0/24 table vpn pref 120 2>/dev/null || true
# default таблицы vpn теперь задаёт /etc/openvpn/server/route-up-home-s3.sh (dev tun3)

```

```bash
chmod +x /etc/openvpn/client/route-up.sh
```

## Таблицы маршрутизации

Файл: `/etc/iproute2/rt_tables` — добавить строку:
```
120 vpn
```

### Актуальные ip rules (live):
```
0:   from all lookup local
110: from all to 10.9.0.0/24 lookup main      # трафик К клиентам
111: from 10.9.0.0/24 to 192.168.0.0/24 lookup main  # клиенты → LAN
120: from 10.9.0.0/24 lookup vpn              # клиенты → интернет
32766: from all lookup main
32767: from all lookup default
```

### Таблица vpn (120):
```
default dev tun3        # выход через S3 (home-s3, с 31.10.2026)
```
Раньше здесь был `default via 10.8.0.1 dev tun0` (выход через S2). S2 с 29.10.2026
заблокирован провайдером, поэтому выход переведён на S3: маршрут ставит
`route-up` сервера `home-s3` (`servers/s1/openvpn/route-up-home-s3.sh`).
Скрипт `s2-client` теперь добавляет только `ip rule`, без маршрута в таблицу `vpn`.

## Запуск

```bash
systemctl enable --now openvpn-client@s2-client
systemctl status openvpn-client@s2-client
```

## Статус

**✅ Работает стабильно.**

Известные ошибки в логах (не критично):
```
AEAD Decrypt error: bad packet ID (may be a replay)
```
Причина: переупорядочивание UDP пакетов. Не влияет на работу.
Если участятся — добавить в конфиг: `replay-window 256 60`
