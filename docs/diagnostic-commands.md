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

**Ожидается:** пинг без потерь. ⚠️ После 29.09.2026 (S2 переключён на
default DROP) этот тест может не работать, если ICMP-правило на S2 не
сохранено персистентно — см. `shared/reference/ports.md`. Альтернатива:
`dig @10.8.0.1 google.com` с S1 (проверяет TCP/UDP-доступность реально).

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

## S2 (77.105.161.151) — выходной шлюз домашнего сегмента + 3x-ui нода

⚠️ Docker полностью демонтирован (28.09.2026). Firewall переведён на
default policy DROP (29.09.2026) — единообразно с S_RU/Panel.

### Системные сервисы

```bash
systemctl is-active openvpn-server@server pihole-FTL x-ui
```

**Ожидается:** все три сервиса `active`.

### Default policy firewall

```bash
iptables -L INPUT -n | head -1
```

**Ожидается:** `policy DROP`.

### Ключевые порты (коммерческий проект — 3x-ui нода)

```bash
ss -tlnp | grep -E ':(10001|25307)\s'
```

**Ожидается:** `10001` (xray relay inbound), `25307` (x-ui управление нодой).

### Фаервол: relay и управление нодой

```bash
iptables -vnL INPUT --line-numbers | grep -E 'dpt:(10001|25307)\b'
```

**Ожидается:** ACCEPT только для конкретных IP (S1, Panel, S_RU для
10001; S1, Panel, домашний LAN для 25307), DROP-catchall в конце
каждой группы.

### Relay-канал: сквозной TCP-тест с S_RU

```bash
ssh root@31.77.169.67 "timeout 3 bash -c 'cat < /dev/null > /dev/tcp/77.105.161.151/10001' && echo OK || echo FAIL"
```

**Ожидается:** `OK` — TCP-уровень доступен (⚠️ не гарантирует, что
протокол Reality/VLESS реально доставляет данные — см.
`migration-3xui.md`, открытая проблема relay-канала).

### Pi-hole доступен через туннель

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1/admin/login
```

**Ожидается:** `200` или `301`/`302`.

---

## S_RU (31.77.169.67) — коммерческий проект, entry-нода

⚠️ Marzban полностью демонтирован 28.09.2026. Сервис — systemd, НЕ Docker.

### Сервисы

```bash
systemctl is-active x-ui
ss -tlnp | grep -E ':(443|24167)\s'
```

**Ожидается:** `x-ui` active, `443` (xray VLESS+Reality entry), `24167`
(x-ui панель, HTTPS).

### Фаервол (ufw)

```bash
ufw status numbered
```

**Ожидается:** default deny, `22`/`443`/`80` открыты всем, `24167`
ограничен списком доверенных IP.

### Исходящий доступ

```bash
curl -s --max-time 5 https://ifconfig.me; echo
```

**Ожидается:** IP `31.77.169.67`.

### Настройки 3x-ui панели

```bash
x-ui settings
```

⚠️ Подписка (порт `2096`) на этой ноде сознательно **отключена**
29.09.2026 — единственный источник подписки для клиентов теперь Panel
(см. ниже).

---

## Panel (31.77.173.218, netru.ru.net) — master-панель 3x-ui

### Сервисы

```bash
systemctl is-active x-ui
ss -tlnp | grep -E ':(25305|2096)\s'
```

**Ожидается:** `25305` (master-панель), `2096` (subscription для клиентов).

### Фаервол (ufw)

```bash
ufw status numbered
```

**Ожидается:** default deny, `22`/`80` открыты всем (80 — certbot
HTTP-01), `25305` — открыт всем + explicit-правила для доверенных IP
(⚠️ правило `Anywhere` для 25305 пока не удалено, см. `system-state.md`).

### Subscription доступен клиентам

```bash
curl -kI --max-time 5 https://netru.ru.net:2096/
```

**Ожидается:** `404 Not Found` (корень пустой — подписки живут на
конкретных `subPath`, это нормально; главное, что порт отвечает, а не
таймаутит).

### TLS-сертификат домена

```bash
certbot certificates
```

**Ожидается:** валидный сертификат для `netru.ru.net`.

---

## Сквозная проверка коммерческого канала (с клиента)

⚠️ **АКТУАЛЬНО НЕ РАБОТАЕТ** (обнаружено 29.09.2026) — v2rayNG и
Hiddify оба не могут получить интернет через `S_RU→S2` relay при
подтверждённо корректных Reality-ключах и работающем TCP/TLS-уровне.
Диагностика в процессе, см. `commercial/migration-3xui.md`.

Старая таблица ниже описывала Marzban-эпоху (geo-split RU/EU) —
неактуальна для текущего стека 3x-ui, где geo-split пока не реализован.
Актуальный ожидаемый путь (после починки): `клиент → S_RU:443 →
S2:10001 → интернет`, без разделения по гео.
