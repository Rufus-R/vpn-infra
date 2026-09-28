# OPNsense (LAN-роутер)

## Роль

OPNsense — домашний роутер, подключённый к S1 как VPN-клиент.
Даёт возможность family-клиентам получить доступ к LAN `192.168.0.0/24`.

## Параметры подключения к S1

| Параметр | Значение |
|---------|---------|
| Role | Client |
| Protocol | UDP IPv4 |
| Device mode | TUN |
| Server host | `194.55.236.229` |
| Server port | `1194` |
| Topology | subnet |
| VPN IP | `10.9.0.5` (статический, из CCD) |
| Аптайм с | 2026-07-22 01:16:21 |

## Сертификаты

| Файл | Источник |
|------|---------|
| `ca.crt` | от S1 (`/etc/openvpn/server-easy-rsa/pki/ca.crt`) |
| `OPNsense01.crt` | от S1 (`/etc/openvpn/server-easy-rsa/pki/issued/OPNsense01.crt`) |
| `OPNsense01.key` | от S1 (`/etc/openvpn/server-easy-rsa/pki/private/OPNsense01.key`) |
| `ta.key` | от S1 (`/etc/openvpn/server/ta.key`), **key-direction 1** |

Копия на S1: `/root/opnsense01/`

## Custom options

```
remote-cert-tls server;
persist-key;
persist-tun;
verb 3;
```

## Interfaces → Assignments

- Интерфейс `ovpnc1` → назван `VPN_S1`
- **Block private networks**: ВЫКЛЮЧЕНО ← важно!
- **Block bogon networks**: ВЫКЛЮЧЕНО ← важно!

## Firewall Rules на интерфейсе VPN_S1

| Действие | Протокол | Источник | Назначение |
|---------|---------|---------|-----------|
| Pass | IPv4 any | `10.9.0.0/24` | This Firewall |
| Pass | IPv4 any | `10.9.0.0/24` | LAN net |

## Outbound NAT

Режим: Hybrid/Manual

| Правило | Описание |
|---------|---------|
| `lan` | Стандартный NAT для LAN |
| `S1RU` | Translate Source IP для VPN-интерфейса |

⚠️ **Правило `S1RU` обязательно!**
Если отключить — пропадает интернет у LAN-клиентов через VPN.

## Статус

- ✅ Подключается к S1, получает `10.9.0.5`
- ✅ Интернет через VPN работает для LAN-клиентов
- ✅ Доступ family → LAN (192.168.0.0/24)


## Диагностика (shell OPNsense)

```sh
# Найти VPN-интерфейс
ifconfig | grep -B2 '10.9.0.5'

# tcpdump на VPN-интерфейсе
tcpdump -ni ovpnc1 icmp

# tcpdump на LAN-интерфейсе
tcpdump -ni <LAN_IF> icmp

# Таблица маршрутизации
netstat -rn4 | egrep '10\.9\.0|192\.168\.0'

# Правила pf
pfctl -sr | egrep -n '10\.9\.0\.0/24|reply-to'
```
