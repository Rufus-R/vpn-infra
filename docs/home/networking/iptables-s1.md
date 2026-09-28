# iptables на S1

## Файлы

```
/etc/iptables/rules.v4              # Сохранённые правила (26.09.2026)
```

Сохранение: `netfilter-persistent save`

## Актуальное состояние (live, 26.09.2026, после демонтажа MTProxy)

### INPUT chain

```
1  ACCEPT  src 10.8.0.0/24  tcp/8080    # vpn-admin из сети S2
2  ACCEPT  src 10.9.0.0/24  tcp/8080    # vpn-admin из клиентской сети
3  ACCEPT  *                udp/1194    # OpenVPN сервер
4  DROP    *                tcp/8080    # блок остальных на vpn-admin
```

⚠️ 26.09.2026: правила для портов `10443` и `443,8443,9443` (MTG) удалены
при демонтаже MTProxy. Подробности: `services/archive/mtg-deprecated-20260926.md`.

### FORWARD chain

```
1  DOCKER-USER    (Docker)
2  DOCKER-FORWARD (Docker)
3  VPN_LAN    in:tun1  dst:192.168.0.0/24
4  ACCEPT     in:tun0  out:tun1  state RELATED,ESTABLISHED
5  ACCEPT     in:tun1  out:tun0  (все)
6  ACCEPT     out:tun1 (все)
7  ACCEPT     in:tun1  (все)
```

### VPN_LAN chain

```
1  ACCEPT  src 10.9.0.5/32   dst 192.168.0.0/24   # OPNsense
2  ACCEPT  src 10.9.0.10/32  dst 192.168.0.0/24   # Mars (family)
3  ACCEPT  src 10.9.0.11/32  dst 192.168.0.0/24   # резерв
4  DROP    *                 *                     # все остальные
```

⚠️ Список резидентов и счётчики требуют актуализации после смены схемы
адресации клиентов (18.08.2026, статические 10.9.0.22–27) — не проверено
на момент этой правки, см. `openvpn/clients.md`.

### NAT POSTROUTING

```
1  MASQUERADE  !docker0  172.17.0.0/16       # Docker
2  MASQUERADE  tun0      10.9.0.0/24         # Клиенты → S2
```

⚠️ 26.09.2026: правило `MASQUERADE tun0 owner UID 999` (MTProxy) удалено.

## Настройка (с нуля)

```bash
# Sysctl
sysctl -w net.ipv4.ip_forward=1

# NAT для клиентов
iptables -t nat -A POSTROUTING -s 10.9.0.0/24 -o tun0 -j MASQUERADE

# FORWARD: между туннелями
iptables -I FORWARD -i tun0 -o tun1 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -I FORWARD -i tun1 -o tun0 -j ACCEPT

# Цепочка контроля доступа к LAN
iptables -N VPN_LAN
iptables -A VPN_LAN -s 10.9.0.5  -d 192.168.0.0/24 -j ACCEPT   # OPNsense
iptables -A VPN_LAN -s 10.9.0.10 -d 192.168.0.0/24 -j ACCEPT   # Mars
iptables -A VPN_LAN -s 10.9.0.11 -d 192.168.0.0/24 -j ACCEPT   # резерв
iptables -A VPN_LAN -j DROP
iptables -I FORWARD -i tun1 -d 192.168.0.0/24 -j VPN_LAN

# vpn-admin
iptables -I INPUT -s 10.9.0.0/24 -p tcp --dport 8080 -j ACCEPT
iptables -I INPUT -s 10.8.0.0/24 -p tcp --dport 8080 -j ACCEPT
iptables -A INPUT -p tcp --dport 8080 -j DROP

# OpenVPN
iptables -A INPUT -p udp --dport 1194 -j ACCEPT

netfilter-persistent save
```

## Известные проблемы

1. **`rules.v4` устарел** — требуется актуальное сохранение:
   `netfilter-persistent save` (выполнено 26.09.2026 при демонтаже MTProxy)
2. **VPN_LAN список резидентов и счётчики** не проверены после смены
   схемы адресации клиентов — требуется live-проверка
