# iptables на S1

## Файлы

```
/etc/iptables/rules.v4              # Сохранённые правила (22.06.2026)
```

Сохранение: `netfilter-persistent save`

## Актуальное состояние (live, 03.08.2026)

### INPUT chain

```
1  ACCEPT  src 10.8.0.0/24  tcp/8080    # vpn-admin из сети S2
2  ACCEPT  src 10.9.0.0/24  tcp/8080    # vpn-admin из клиентской сети
3  ACCEPT  *                tcp/10443   # ⚠️ неизвестный порт (тест MTG?)
4  ACCEPT  *                tcp 443,8443,9443  # MTG порты (MTG отложен)
5  ACCEPT  *                udp/1194    # OpenVPN сервер
6  DROP    *                tcp/8080    # блок остальных на vpn-admin
```

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

⚠️ **Счётчики VPN_LAN = 0** — ни одного пакета к LAN не прошло.
Это подтверждает проблему из [../problems/lan-access.md](../problems/lan-access.md).

### NAT POSTROUTING

```
1  MASQUERADE  !docker0  172.17.0.0/16       # Docker
2  MASQUERADE  tun0      10.9.0.0/24         # Клиенты → S2
3  MASQUERADE  tun0      owner UID 999       # MTProxy → S2
```

### MANGLE OUTPUT

```
1  RETURN  owner UID 999  udp/53    # MTProxy DNS — не маркировать
2  RETURN  owner UID 999  tcp/53    # MTProxy DNS — не маркировать
3  MARK    owner UID 999  tcp/443   → 0x64   # MTProxy → mark 100
```

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

# MTG
iptables -A INPUT -p tcp -m multiport --dports 443,8443,9443 -j ACCEPT

# MTProxy изоляция (mangle)
iptables -t mangle -I OUTPUT 1 -m owner --uid-owner 999 -p udp --dport 53 -j RETURN
iptables -t mangle -I OUTPUT 2 -m owner --uid-owner 999 -p tcp --dport 53 -j RETURN
iptables -t mangle -I OUTPUT 3 -m owner --uid-owner 999 -p tcp --dport 443 -j MARK --set-mark 100
iptables -t nat -A POSTROUTING -m owner --uid-owner 999 -o tun0 -j MASQUERADE

netfilter-persistent save
```

## Известные проблемы

1. **Правило tcp/10443** — неизвестное назначение, возможно тестовый порт MTG
2. **Порты 8443/9443 открыты** хотя MTG на них не запущен
3. **`rules.v4` устарел** — последнее сохранение 22.06.2026,
   live-конфиг отличается (Docker добавил свои цепочки)
   Обновить: `netfilter-persistent save`
