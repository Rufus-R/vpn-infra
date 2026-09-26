# Диагностические команды

Все команды ТОЛЬКО ЧИТАЮЩИЕ — ничего не меняют в системе.
Для каждого сервера: команды + ожидаемый результат.

---

## S1 (194.55.236.229, maximum.ru.net) — домашний хаб

### Статус ключевых сервисов

```bash
systemctl is-active openvpn-server@server openvpn-client@s2-client vpn-admin
```

**Ожидается:** все три сервиса в статусе `active`.

### Подключённые клиенты OpenVPN

```bash
grep CLIENT_LIST /var/log/openvpn-status-tun1.log | awk -F',' '{print $2, $4}'
```

**Ожидается:** статические IP `10.9.0.2`–`10.9.0.27`, плюс `10.9.0.5` для OPNsense01.

### Туннель к S2

```bash
ping -c 2 -W 2 10.8.0.1
```

**Ожидается:** пинг без потерь (2 received, 0% packet loss).

### Маршрутизация

```bash
ip route show table vpn
ip rule list
```

**Ожидается:** маршрут `10.9.0.0/24` через `10.8.0.1`.

### Фаервол (ключевые цепочки)

```bash
iptables -vnL FORWARD --line-numbers | head -10
iptables -t nat -vnL POSTROUTING --line-numbers | head -10
```

---

## S2 (77.105.161.151) — выходной шлюз + релея

### Системные сервисы

```bash
systemctl is-active openvpn-server@server pihole-FTL
```

**Ожидается:** оба сервиса `active`.

### Docker-контейнеры

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

**Ожидается:** `relay-node` в статусе `Up`.

### Ключевые порты

```bash
ss -tlnp | grep -E ':(8443|443|1194|53)\s'
```

**Ожидается:** слушают порты 8443 (релея), 53 (Pi-hole), 1194 (OpenVPN).

### Фаервол: порт 8443

```bash
iptables -vnL INPUT --line-numbers | grep 8443
```

**Ожидается:** правило для порта 8443 только с источником `31.77.169.67` (S_RU).

### Логи релея-контейнера

```bash
docker logs relay-node --tail 20 2>&1
```

**Ожидается:** записи о принятых подключениях (если был трафик).

### Pi-hole доступен через туннель

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1/admin/login
```

**Ожидается:** `200` или `301`/`302` (редирект).

---

## S_RU (31.77.169.67) — коммерческий проект

### Контейнеры Marzban

```bash
cd /opt/marzban && docker compose ps
```

**Ожидается:** контейнер marzban в статусе `Up`.

### Конфиг Xray (ключевые секции)

```bash
docker exec marzban-marzban-1 cat /var/lib/marzban/xray_config.json \
  | jq '{outbounds: [.outbounds[].tag], routing: .routing.rules | length, dns: .dns.servers}'
```

**Ожидается:** три исходящих тега (прямой, блокировка, на ЕС), несколько правил маршрутизации.

### Фаервол UFW

```bash
ufw status numbered
```

**Ожидается:** открыты порты 22 и 443.

### Исходящий доступ

```bash
curl -s --max-time 5 https://ifconfig.me; echo
```

**Ожидается:** IP `31.77.169.67`.

### Актуальность гео-баз

```bash
ls -lh /opt/marzban/xray-assets/geoip.dat /opt/marzban/xray-assets/geosite.dat
```

**Ожидается:** дата свежая (обновляется cron каждое воскресенье).

---

## Сквозная проверка коммерческого канала (с клиента)

Подключить клиент с дефолтными настройками и открыть:

| Сайт | Ожидаемый результат |
|------|---------------------|
| yandex.ru | IP `31.77.169.67` (прямой выход) |
| google.com | Открывается |
| ifconfig.me | IP `77.105.161.151` (через ЕС-релея) |
| wikipedia.org | Открывается (через ЕС-релея) |
