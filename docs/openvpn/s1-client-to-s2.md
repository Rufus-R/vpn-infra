# OpenVPN: S1 как клиент к S2

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
ip route add default via 10.8.0.1 dev tun0 table vpn 2>/dev/null || true

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
default via 10.8.0.1 dev tun0
```

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
