# Маршрутизация и policy routing (S1)

## Файлы

```
/etc/iproute2/rt_tables             # Таблицы маршрутизации
/etc/openvpn/client/route-up.sh     # Скрипт настройки (запускается OpenVPN)
/etc/sysctl.conf                    # ip_forward, rp_filter
```

## Sysctl

Файл: `/etc/sysctl.conf`
```
net.ipv4.ip_forward=1
net.ipv4.conf.all.rp_filter=2
```

**`rp_filter=2` (loose mode) — критически важен** для policy routing.
Без него ядро отбрасывает пакеты, пришедшие "не с того" интерфейса.

## Таблицы маршрутизации

Файл: `/etc/iproute2/rt_tables`
```
255  local
254  main
253  default
0    unspec
120  vpn       # ← добавлено вручную
```

## ip rules (live)

```
0:   from all lookup local
109: from all fwmark 0x64 lookup 100
110: from all to 10.9.0.0/24 lookup main
111: from 10.9.0.0/24 to 192.168.0.0/24 lookup main
120: from 10.9.0.0/24 lookup vpn
32766: from all lookup main
32767: from all lookup default
```

### Объяснение правил:

| Приоритет | Правило | Назначение |
|-----------|---------|-----------|
| 109 | `fwmark 0x64 → table 100` | MTProxy TCP/443 → через S2 |
| 110 | `to 10.9.0.0/24 → main` | Трафик К клиентам идёт через main (tun1) |
| 111 | `from 10.9.0.0/24 to 192.168.0.0/24 → main` | Клиенты → LAN через main |
| 120 | `from 10.9.0.0/24 → vpn` | Весь остальной трафик клиентов → через S2 |

## Таблица vpn (120) — live

```
default via 10.8.0.1 dev tun0
```

Назначение: весь трафик клиентов (src 10.9.0.0/24) уходит через tun0 → S2 → интернет.

## Таблица 100 (MTProxy) — live

```
default via 10.8.0.1 dev tun0 src 10.8.0.2
```

Назначение: маркированный трафик (fwmark 100) от mtg уходит через tun0.

## Таблица main — live (актуальные маршруты)

```
default via 194.55.236.1 dev ens3 onlink
10.8.0.0/24 dev tun0 proto kernel scope link src 10.8.0.2
10.9.0.0/24 dev tun1 proto kernel scope link src 10.9.0.1
172.17.0.0/16 dev docker0 (linkdown)
192.168.0.0/24 via 10.9.0.2 dev tun1
194.55.236.0/24 dev ens3 proto kernel scope link src 194.55.236.229
```

⚠️ **Замечание**: `192.168.0.0/24 via 10.9.0.2` — маршрут к LAN указывает
на `10.9.0.2` (Petr), а не на `10.9.0.5` (OPNsense). OpenVPN использует
iroute для внутренней маршрутизации, поэтому это может быть нормальным,
но требует проверки после рестарта сервера.

## Проверка маршрутизации

```bash
ip rule list
ip route show
ip route show table vpn
ip route show table 100
ip route get 8.8.8.8 from 10.9.0.10    # как клиент Mars видит интернет
ip route get 192.168.0.1 from 10.9.0.10 # как клиент Mars видит LAN
```
