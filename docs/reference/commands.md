# Полезные команды для диагностики

## S1 (194.55.236.229)

### Статус сервисов
```bash
systemctl status openvpn-client@s2-client
systemctl status openvpn-server@server
systemctl status vpn-admin
systemctl status mtg@443
```

### OpenVPN
```bash
# Статус клиентов (live)
cat /var/log/openvpn-status-tun1.log

# Логи
journalctl -u openvpn-server@server --no-pager -n 30
journalctl -u openvpn-client@s2-client --no-pager -n 30

# Перезапуск (все клиенты переподключатся)
systemctl restart openvpn-server@server
systemctl restart openvpn-client@s2-client
```

### Сеть
```bash
ip a
ip rule list
ip route show
ip route show table vpn
ip route show table 100
ip route get 8.8.8.8 from 10.9.0.10     # как клиент видит интернет
ip route get 192.168.0.1 from 10.9.0.10 # как клиент видит LAN
```

### iptables
```bash
iptables -vnL FORWARD --line-numbers
iptables -vnL INPUT --line-numbers
iptables -vnL VPN_LAN --line-numbers
iptables -t nat -vnL POSTROUTING --line-numbers
iptables -t mangle -vnL OUTPUT --line-numbers
```

### CCD файлы
```bash
for f in /etc/openvpn/ccd/*; do echo "=== $f ==="; cat "$f"; done
```

### vpn-admin
```bash
journalctl -u vpn-admin --no-pager -n 20
ss -tlnup | grep 8080
```

### MTG
```bash
journalctl -u mtg@443 --no-pager -n 20
mtg access /etc/mtg/443.toml
```

### PKI
```bash
cat /etc/openvpn/server-easy-rsa/pki/index.txt
```

### Диагностика трафика
```bash
# Пакеты в сторону LAN
tcpdump -ni tun1 host 192.168.0.1
# Пакеты в туннель S2
tcpdump -ni tun0 icmp
# Пакеты от конкретного клиента
tcpdump -ni tun1 src 10.9.0.10
```

### Ресурсы
```bash
df -h
free -h
uptime
ss -tlnup
```

---

## S2 (77.105.161.151)

### Статус сервисов
```bash
systemctl status openvpn-server@server
pihole status
systemctl status pihole-FTL
```

### OpenVPN
```bash
cat /var/log/openvpn-status.log
journalctl -u openvpn-server@server --no-pager -n 20
```

### Pi-hole
```bash
curl -I http://10.8.0.1/admin/login
ss -tlnup | grep pihole
```

### iptables
```bash
iptables -vnL INPUT --line-numbers
iptables -vnL FORWARD --line-numbers
iptables -t nat -vnL --line-numbers
```

### Сеть
```bash
ip a show tun0
ip route show
```

---

## OPNsense (shell — пункт 8 в консоли или SSH)

```sh
# Найти VPN-интерфейс
ifconfig | grep -B2 '10.9.0.5'

# Трафик на VPN-интерфейсе
tcpdump -ni ovpnc1 icmp

# Трафик на LAN
tcpdump -ni <LAN_IF> icmp

# Маршруты
netstat -rn4 | egrep '10\.9\.0|192\.168\.0'

# Правила pf
pfctl -sr | egrep -n '10\.9\.0\.0/24|reply-to'
pfctl -sr | head -50
```
