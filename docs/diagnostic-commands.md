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

**Ожидается:** пинг без потерь (ufw на S2 пропускает ICMP штатно, проверено 01.10.2026).
Дополнительно: `dig @10.8.0.1 google.com` с S1 проверяет TCP/UDP-доступность реально.

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

## S2 (77.105.161.151) — ❌ выведен из эксплуатации 31.10.2026 (не опрашивать)

Блокировка РКН, смена IP не помогла. Команды ниже — исторические. Живой домашний
шлюз — S3 (`195.242.118.2`, туннель `10.10.0.0/24`).

⚠️ Docker удалён (контейнеры 28.09.2026, пакеты 01.10.2026). Firewall — `ufw`
(default deny, с 01.10.2026; до этого iptables DROP с 29.09.2026) — единообразно с S_RU/Panel.

### Системные сервисы

```bash
systemctl is-active openvpn-server@server pihole-FTL x-ui
```

**Ожидается:** все три сервиса `active`.

### Firewall (ufw)

```bash
ufw status verbose | head -4
```

**Ожидается:** `Status: active`, `Default: deny (incoming), allow (outgoing), deny (routed)`.

### Ключевые порты (коммерческий проект — 3x-ui нода)

```bash
ss -tlnp | grep -E ':(10001|25307)\s'
```

**Ожидается:** `10001` (xray relay inbound), `25307` (x-ui управление нодой).

### Фаервол: relay и управление нодой

```bash
ufw status numbered | grep -E '10001|25307'
```

**Ожидается:** ALLOW IN только для конкретных IP (S1, Panel, S_RU для 10001;
S1, Panel, `46.32.82.242`, `10.8.0.0/24` для 25307); всё остальное закрыто default deny.

### Relay-канал: сквозной TCP-тест с S_RU

```bash
ssh root@31.77.169.67 "timeout 3 bash -c 'cat < /dev/null > /dev/tcp/77.105.161.151/10001' && echo OK || echo FAIL"
```

**Ожидается:** `OK` — TCP-уровень доступен (⚠️ не гарантирует, что
протокол Reality/VLESS реально доставляет данные — см.
`operations-log.md`; проблема relay-канала решена 30.09.2026).

### Pi-hole доступен через туннель

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1:8080/admin/login
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

### Версия Xray и geo-split

```bash
/usr/local/x-ui/bin/xray-linux-amd64 version | head -1
python3 -c "import json;r=json.load(open('/usr/local/x-ui/bin/config.json'))['routing'];print(r['domainStrategy']);[print(x) for x in r['rules']]"
```

**Ожидается:** `Xray 26.10.10` (проверено 17.10.2026, работает на всех панелях; прежняя пометка «не обновлять» относилась к регрессии v26.9.9, на версиях ≥26.9.30 она не воспроизводится); `IPIfNonMatch` и 5 правил, в т.ч. `geosite:category-ru` → direct и `geoip:ru` → direct.

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

## S3 (195.242.118.2) — relay/exit + socks5 `tg-proxy`

### Сервисы и порты

```bash
systemctl is-active xray-relay openvpn-server@home-backup
ss -tlnp | grep -E ':(10001|38417)\s'
```

**Ожидается:** оба юнита `active`; `*:10001` (relay, VLESS+TLS) и `*:38417`
(socks5 `tg-proxy` для бота Panel).

### Фаервол

```bash
ufw status | grep -E '10001|38417|8443'
```

**Ожидается:** `10001` — только `31.77.169.67` и `194.55.236.229`; `38417` —
только `31.77.78.144`; `8443` — только `194.55.236.229`.

### Прокси Telegram-бота (главный индикатор живучести бота)

```bash
# локально на S3, с учётными данными из /run/tgproxy_creds
read -r U P < /run/tgproxy_creds
curl -s --socks5-hostname "$U:$P@127.0.0.1:38417" -o /dev/null \
     -w 'tg=%{http_code}\n' https://api.telegram.org/
```

**Ожидается:** `302` (корень Telegram API). `000` — прокси не работает.

С Panel (боевая проверка):

```bash
curl -s --socks5-hostname <user>:<pass>@195.242.118.2:38417 \
     "https://api.telegram.org/bot<TOKEN>/getMe" | head -c 120
```

**Ожидается:** `{"ok":true,...}`. Проверка без верных учётных данных должна
давать `000` — так подтверждается, что аутентификация socks5 включена.

### Конфиг и сертификат

```bash
/usr/local/xray/xray run -test -c /etc/xray/config.json
openssl x509 -in /etc/xray/certs/server.crt -noout -enddate -fingerprint -sha256
```

**Ожидается:** `Configuration OK`; self-signed до 2036. При перевыпуске
сертификата обновить `pinnedPeerCertSha256` в outbound `to-s3-relay` на S_RU.

### OpenVPN `home-backup` (известная проблема, §«Известные отклонения»)

```bash
tail -5 /var/log/openvpn/status-home.log
grep -c 'Bad encapsulated packet length' /var/log/openvpn/*.log 2>/dev/null
```

**Ожидается:** `active`, в `status-home.log` есть `ROUTING_TABLE,…,s1,…`.
Трафик через туннель **не идёт** — открытая задача, см.
`docs/checkpoint-2026-10-29-tunnel-s3-probes.md`.

---

## Panel (31.77.78.144, netru.ru.net) — master-панель 3x-ui

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
HTTP-01), `25305` — только для доверенных IP (S1, S2, S_RU, `46.32.82.242`);
правил `Anywhere` для 25305 быть не должно. Новый Panel (с 17.10.2026): `22`/`80`/`443`/`2096` — всем (v4 и v6), `25305` — S1, S2, S_RU, `46.32.82.242`.

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

### Бот, лендинг и продление сертификата

```bash
systemctl is-active x-ui nginx netru-bot certbot.timer
systemctl show -p NRestarts --value netru-bot
```

**Ожидается:** все четыре `active`, `NRestarts=0`.

### Telegram-бот: поллинг через socks5 на S3

```bash
journalctl -u netru-bot --since -10min --no-pager | grep -c 'Failed to fetch updates'
journalctl -u netru-bot --since -24h --no-pager | grep 'Update id=' | tail -1
grep -E '^TG_PROXY_URL' /opt/netru-bot/src/.env | sed -E 's|//[^@]*@|//***@|'
```

**Ожидается:** ошибок `0` (единичные допустимы); последний обработанный апдейт
не старше суток; `TG_PROXY_URL` указывает на **S3** (`195.242.118.2:38417`).

⚠️ Признак инцидента 29–30.10.2026: счётчик ошибок растёт монотонно (~56/час),
в сообщении `retry in … tryings = N` и `Request timeout error`, апдейты не
обрабатываются. При этом вебхук ЮKassa (`127.0.0.1:8711`) и чеки «Мой налог»
продолжают работать — сбой только в канале к `api.telegram.org`.

### Вебхук ЮKassa (приём платежей)

```bash
ss -tlnp | grep 8711
curl -s -o /dev/null -w 'hook=%{http_code}\n' -X POST \
  http://127.0.0.1:8711/yookassa-webhook/<path>/
```

**Ожидается:** слушает `127.0.0.1:8711`; HTTP-код любой, кроме `000`
(таймаут = процесс мёртв). ⚠️ Бот и вебхук — **один процесс**: падение
`netru-bot` останавливает приём оплаты.

---

## Сквозная проверка коммерческого канала (с клиента)

✅ Работает (подтверждено 30.09 и 01.10.2026). Проверка с телефона через VPN (Happ/v2rayNG, fingerprint firefox, mux):

| Сайт | Ожидаемый результат |
|------|---------------------|
| `https://2ip.io/ru/` | IP `195.242.118.2` (S3, exit с 29.10.2026; до инцидента был S2 `77.105.161.151`) |
| `https://yandex.ru/internet`, `https://yandex.com/internet` | IP `31.77.169.67` (S_RU, direct по geo-split) |
| YouTube, банки, Госуслуги | открываются |

Путь: клиент → S_RU:443 → (RU direct | S3:10001 → интернет; S2 — hot-standby). Если RU-сайты показывают IP S2/S3 — проверить routing S_RU (раздел «Версия Xray и geo-split» выше).

Резервный вход AmneziaWG (S_RU:443/udp, зафиксирован 20.10.2026): ожидаемые результаты те же. Проверено оператором 20.10.2026 через приложение AmneziaWG: 2ip.io — `77.105.161.151`, yandex.ru/internet — `31.77.169.67`. Ссылку подписки приложение не принимает, нужна конфигурация. Состояние (только чтение): на S_RU `ss -lunp | grep -E ':443\b'` — ожидается `x-ui` на 443/udp, `ufw status numbered | grep 443` — правила 443/udp (v4 и v6); на Panel `sqlite3 -header /etc/x-ui/x-ui.db 'SELECT id,remark,port,protocol,node_id,exclude_from_sub FROM inbounds;'` — инбаунд `AmneziaWG` (id 7, `amneziawg`, 443, `node_id` как у `reality-entry`).

## Panel: чтение `bot.db` — `sqlite3` CLI и запасной путь через python3

⚠️ **Правило (после инцидента 10.10.2026):** перед любой операцией с `bot.db` —
`grep DB_PATH /opt/netru-bot/src/.env`. Настоящая БД — `/opt/netru-bot/bot.db`
(`DB_PATH`), а не `bot.db` в рабочем каталоге процесса (`WorkingDirectory`).
Пустышка `src/bot.db` возникала дважды (09.10 и 30.10 — во второй раз её создал
агент одним тестовым `sqlite3`-запросом к несуществующему файлу; удалена).

На новом Panel `31.77.78.144` CLI `sqlite3` есть (проверено 20.10.2026: `sqlite3 /opt/netru-bot/bot.db 'SELECT version_num FROM alembic_version;'` вернул `0003`). Запасной способ ниже описан по прежнему Panel, где пакета не было.

Обнаружено 11.10.2026: на Panel (на старом `31.77.173.218`, удалён 20.10.2026) не было системного пакета `sqlite3`
(CLI-клиент), хотя Python-драйвер `sqlite3` (стандартная библиотека) доступен.
Команда `sqlite3 <файл> '<SQL>'` вернёт `bash: sqlite3: command not found`.

Рабочая замена для read-only диагностики `bot.db` (и, возможно, `x-ui.db` на этом же
сервере — не проверялось явно):

```bash
python3 -c "import sqlite3; c=sqlite3.connect('/opt/netru-bot/bot.db'); \
print(c.execute(\"SELECT sql FROM sqlite_master WHERE name='<таблица>'\").fetchone())"
```

Для произвольного SELECT с несколькими строками:

```bash
python3 -c "
import sqlite3
c = sqlite3.connect('/opt/netru-bot/bot.db')
for row in c.execute('SELECT * FROM support_messages LIMIT 10'):
    print(row)
"
```

Не устанавливать `sqlite3` через `apt` без необходимости — ресурсы Panel ограничены
(на новом Panel 961 МиБ всего, доступно ~395 МиБ на 17.10.2026), а read-only диагностика через `python3`
полностью покрывает потребность.
