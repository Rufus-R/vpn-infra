# iptables на S2

## Файлы

```
/etc/iptables/rules.v4              # Сохранённые правила (06.06.2026)
```

## Актуальное состояние (live, 03.08.2026)

### INPUT chain

```
1   ACCEPT  in:tun0  tcp/80          # Pi-hole web
2   ACCEPT  in:tun0  udp/53          # Pi-hole DNS
3   ACCEPT  in:tun0  tcp/53          # Pi-hole DNS
4   DROP    !tun0    tcp/80
5   DROP    !tun0    udp/53
6   DROP    !tun0    tcp/53
7-15 ... (дублированные правила ACCEPT/DROP)
16  ACCEPT  *        udp/1194        # OpenVPN
17  DROP    *        udp/53
18  DROP    *        tcp/53
19-22 ... (дублированные DROP)
```

⚠️ **ПРОБЛЕМА: множество дублированных правил**
В INPUT накопилось 22 правила, хотя достаточно 7.
Рекомендуется почистить.

### FORWARD chain

```
1  DOCKER-USER    (Docker)
2  DOCKER-FORWARD (Docker)
3  ACCEPT  in:ens3  out:tun0  state RELATED,ESTABLISHED
4  ACCEPT  in:tun0  out:ens3  (все)
```

### NAT POSTROUTING

```
1  MASQUERADE  !docker0  172.17.0.0/16      # Docker
2  MASQUERADE  ens3      10.8.0.0/24        # S1 клиент → интернет
3  MASQUERADE  ens3      10.8.0.0/24        # ДУБЛЬ
4  MASQUERADE  ens3      10.9.0.0/24        # VPN-клиенты → интернет
```

## Чистые правила (рекомендуемые)

```bash
# Очистка
iptables -F INPUT
iptables -F FORWARD
iptables -t nat -F POSTROUTING

ETH=ens3

# INPUT
iptables -A INPUT -i tun0 -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -i tun0 -p udp --dport 53 -j ACCEPT
iptables -A INPUT -i tun0 -p tcp --dport 53 -j ACCEPT
iptables -A INPUT -p udp --dport 1194 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j DROP
iptables -A INPUT -p udp --dport 53 -j DROP
iptables -A INPUT -p tcp --dport 53 -j DROP
# TODO: добавить блокировку 443 и 123
iptables -A INPUT -p tcp --dport 443 -j DROP
iptables -A INPUT -p udp --dport 123 -j DROP

# FORWARD
iptables -A FORWARD -i $ETH -o tun0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i tun0 -o $ETH -j ACCEPT

# NAT
iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o $ETH -j MASQUERADE
iptables -t nat -A POSTROUTING -s 10.9.0.0/24 -o $ETH -j MASQUERADE

netfilter-persistent save
```

## Известные проблемы

1. **Дублированные правила** — 15+ дублей, сохранены в `rules.v4`
2. **Дублированный MASQUERADE** для `10.8.0.0/24` в NAT
3. **Порт 443/tcp НЕ заблокирован** — Pi-hole HTTPS доступен снаружи (если кто-то знает IP)
4. **Порт 123/udp НЕ заблокирован** — Pi-hole NTP доступен снаружи
5. **`rules.v4` устарел** — последнее сохранение 06.06.2026
