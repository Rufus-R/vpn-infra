# Известные проблемы и замечания

## 🔴 Критические

### 1. crl-verify (РЕШЕНО 19.09.2026)
Конфиг содержит crl-verify, файл crl.pem загружается OpenVPN. Отозванные сертификаты блокируются.
Отозванные клиенты (friend1, SET, Nikita) могут подключиться,
если у них остались .ovpn файлы.

**Исправление**:
```bash
echo "crl-verify /etc/openvpn/server-easy-rsa/pki/crl.pem" \
  >> /etc/openvpn/server/server.conf
systemctl restart openvpn-server@server
```

### 2. Family → LAN не работает
Подробности: [lan-access.md](lan-access.md)

---

## 🟡 Важные

### 3. S2: дублированные правила iptables
В INPUT ~22 правила вместо 7, в NAT дубль MASQUERADE.
Не влияет на работу, но затрудняет диагностику.

**Исправление**: применить чистые правила из
[../networking/iptables-s2.md](../networking/iptables-s2.md)

### 4. S2: порты 443/tcp и 123/udp не заблокированы
Pi-hole слушает на всех интерфейсах. iptables не блокирует
443 (HTTPS Pi-hole) и 123 (NTP) снаружи.

**Исправление**:
```bash
# На S2
iptables -A INPUT -i tun0 -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j DROP
iptables -A INPUT -p udp --dport 123 -j DROP
netfilter-persistent save
```

### 5. S1: неизвестное правило tcp/10443
В INPUT есть `ACCEPT tcp/10443` — неизвестное назначение.
Вероятно тестовый порт MTG, забыт.

**Проверить и удалить**:
```bash
iptables -vnL INPUT --line-numbers | grep 10443
# Найти номер строки и удалить
iptables -D INPUT <номер>
netfilter-persistent save
```

### 6. S1: открытые порты 8443/9443 без работающего сервиса
MTG на 8443/9443 не запущен, но iptables разрешает входящие.

**Исправить когда решится судьба MTG**:
```bash
# Убрать 8443,9443 из правила, оставить только 443
iptables -D INPUT -p tcp -m multiport --dports 443,8443,9443 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
netfilter-persistent save
```

### 7. S1: маршрут 192.168.0.0/24 via 10.9.0.2
Маршрут к LAN указывает на `10.9.0.2` (Petr), а не на `10.9.0.5` (OPNsense).
Вероятно устарел и исправится после рестарта openvpn-server@server.

### 8. S1: Бэкап PKI (РЕШЕНО 19.09.2026)
Актуальный снимок /etc/openvpn/server-easy-rsa/pki сохранён в /root/vpn-infra-backup/s1/pki_20260920.
**Обновить**:
```bash
cp -r /etc/openvpn/server-easy-rsa/pki \
  /root/vpn-infra-backup/s1/pki_$(date +%Y%m%d)
```

---

## 🟢 Некритичные

### 9. vpn-admin без аутентификации
Любой VPN-клиент может управлять всеми клиентами.
Запланировано: Basic Auth. Пока не реализовано.

### 10. CCD Anna и SET01 без метки # group: family
Определяются как family через `push "route ..."`,
но не через метку `# group: family`.
Непоследовательность с Mars. Не влияет на работу.

**При желании исправить**:
```bash
sed -i '1s/^/# group: family\n/' /etc/openvpn/ccd/Anna
sed -i '1s/^/# group: family\n/' /etc/openvpn/ccd/SET01
```

### 11. Orphan CCD файл family-user1
Файл `/etc/openvpn/ccd/family-user1` существует,
но сертификата `family-user1.crt` в PKI нет.

**Удалить**:
```bash
rm /etc/openvpn/ccd/family-user1
```

### 12. S2: дубль net.ipv4.ip_forward в sysctl.conf
```
net.ipv4.ip_forward=1
net.ipv4.ip_forward=1   # дубль
```
Не влияет на работу.

### 13. Certbot timer активен но сертификата нет
`certbot.timer` работает на S1, но сертификат не получен
(ждёт решения проблемы с Cloudflare API token).
Подробности: [../docker/migration.md](../docker/migration.md)
