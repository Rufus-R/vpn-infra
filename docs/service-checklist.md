# Чек-лист сервисов для диагностики

Один проход = ответ на вопрос «что именно сломано». Все команды **read-only**.
Подробные команды с обоснованием ожиданий — в `diagnostic-commands.md`;
здесь — порядок проверки, пороги и признаки деградации.

## 0. Как пользоваться

1. **Быстрый проход** (≈5 минут): раздел 1 «Критичное» — сверху вниз по цепочке.
   Проверять нужно **по направлению трафика**, а не по алфавиту серверов: если сломан
   S3, то проверять Panel и бота бессмысленно.
2. **Полный проход**: разделы 4–8 по серверам.
3. **Автоматизация**: `scripts/healthcheck.sh` — read-only сборщик того же набора
   проверок; запускается на самом сервере либо по SSH:
   ```bash
   ssh -n root@<сервер> 'bash -s' < scripts/healthcheck.sh
   ```
4. **Правило инцидента**: сначала фиксируем *время начала* сбоя по журналу
   (`journalctl … | grep <шаблон> | head`), потом ищем причину. Время начала почти
   всегда указывает на событие (переезд, блокировка, деплой).

## 1. Критичное (влияет на клиентов или деньги)

| # | Компонент | Где проверять | Команда | Ожидается |
|---|-----------|---------------|---------|-----------|
| 1 | Приём платежей | Panel | `ss -tlnp \| grep 8711` | `127.0.0.1:8711` слушает (вебхук ЮKassa) |
| 2 | Вебхук отвечает | Panel | `curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8711/yookassa-webhook/<path>/` | любой HTTP-код, кроме таймаута (`000`) |
| 3 | Бот живёт | Panel | `systemctl is-active netru-bot` | `active` |
| 3a | Legacy-бот x-ui (админ-бот панели) | Panel | `journalctl -u x-ui --since -10min \| grep -c 'Retrying getting updates'` | `0` (сейчас не `0` — см. §8, аварии не составляет) |
| 4 | Бот говорит с Telegram | Panel | `journalctl -u netru-bot --since -10min \| grep -c 'Failed to fetch updates'` | `0` (единичные — норма) |
| 5 | Вход для клиентов | S_RU | `ss -tlnp \| grep ':443'` | `xray` на `*:443` |
| 6 | Exit-нода | S3 | `systemctl is-active x-ui` + `ss -tlnp \| grep 10001` | `active`, `*:10001` (порт 10001 держит **x-ui**, `xray-relay` с 30.10.2026 остановлен) |
| 7 | Канал S_RU→S3 | S_RU | `timeout 4 bash -c 'cat < /dev/null > /dev/tcp/10.11.0.2/10001'` | код `0` — проверять **через tun0** (`10.11.0.2`), т.к. relay-аутбаунд смотрит туда (проверено 31.10: OPEN, TLS OK, выход `195.242.118.2`) |
| 8 | Подписки клиентам | Panel | `curl -k -s -o /dev/null -w '%{http_code}' --max-time 5 https://netru.ru.net:2096/` | `404` (порт отвечает), не `000` |
| 9 | Домашний шлюз | S1 | `ping -c 2 -W 2 10.8.0.1` | 0% потерь |
| 10 | Домашний DHCP/DNS | S2 | `systemctl is-active pihole-FTL` | `active` |

## 2. Матрица зависимостей

Ломается верхний узел — ниже по стрелке всё красное, и это **не** отдельные аварии.

```
клиент ──► S_RU:443 ──► S3:10001 ──► интернет          (коммерческий трафик)
                    └──► S2:10001 (hot-standby, блокирован)

Panel: bot ──► TG_PROXY_URL (socks5) ──► api.telegram.org   (поллинг команд)
Panel: 8711 (вебхук) ◄── ЮKassa                              (оплата)
Panel: cron/nalog ──► lknpd.nalog.ru                         (чеки НПД)

S1 ──► S2:1194 (tun0)  ──► Pi-hole / LAN                     (домашний контур)
S1 ──► S3:8443 (tun2)  ──► backup-туннель (не работает, §9)
```

| Зависимость | Ломается молча | Проверка-индикатор |
|-------------|----------------|--------------------|
| Бот → `TG_PROXY_URL` | да: бот жив, платежи идут, но команды не обрабатываются | счётчик `tryings =` растёт, апдейтов нет |
| S_RU → S3 | да: клиент «подключён», трафика нет | TCP до `S3:10001`, затем клиентский `2ip.io` |
| Panel → Panel-BD | нет: падает всё сразу | `sqlite3 /opt/netru-bot/bot.db 'pragma integrity_check;'` |
| S1 → S2 `tun0` | нет: видно по ping | `ping 10.8.0.1`, `ip route show table vpn` |

## 3. Признаки деградации (grep-шаблоны)

| Шаблон в журнале | Что значит | Где |
|------------------|-----------|-----|
| `Failed to fetch updates … retry in` | бот не достаёт Telegram (прокси/сеть) | Panel `netru-bot` |
| `tryings = <N>` растёт монотонно | устойчивый сбой, а не разовый | Panel `netru-bot` |
| `HTTP Client says - Request timeout error` | прокси недоступен (не 401/403 — именно сеть) | Panel `netru-bot` |
| `Bad encapsulated packet length from peer (16705)` | сдвиг потока в OpenVPN `8443/tcp` | S3 `openvpn-server@home-backup` |
| `Connection reset, restarting [0]` | клиент OpenVPN оборван | S3 `openvpn-server@home-backup` |
| `TLS handshake error … i/o timeout` | внешние сканеры на 2096, не наша авария | Panel `x-ui` |
| `getUpdates: … fasthttp: tls handshake timed out` + `Retrying getting updates in 8s` | **legacy-бот внутри x-ui** не достаёт Telegram: `tgBotProxy` пуст, ходит напрямую, а часть TG DC режется. Не влияет на клиентов и платежи (`netru-bot` — отдельный процесс с другим токеном) | Panel `x-ui` |
| `PanelApiError … record not found` | клиента удалили на Panel вручную | Panel `netru-bot` |
| `HTTP/1.1 4xx` на `lknpd.nalog.ru` | протух токен «Мой налог» | Panel `netru-bot` |

## 4. S1 (194.55.236.229) — домашний хаб

Firewall — `iptables` (ufw на S1 нет).

| Сервис / порт | Команда | Ожидается |
|---------------|---------|-----------|
| `openvpn-server@server` (1194/udp, tun1) | `systemctl is-active openvpn-server@server` | `active` |
| `openvpn-client@s2-client` (tun0) | `systemctl is-active openvpn-client@s2-client` | `active` |
| `openvpn@s3-backup` (8443/tcp, tun2) | `systemctl is-active openvpn@s3-backup` | `active` (данные не ходят — §9) |
| `vpn-admin` (8080, `10.9.0.1`) | `systemctl is-active vpn-admin` | `active` |
| Клиенты в статусе | `grep CLIENT_LIST /var/log/openvpn-status-tun1.log` | 4+ строк, адреса `10.9.0.x` |
| Маршрут домашнего контура | `ip route show table vpn` | `default via 10.8.0.1 dev tun0` |
| Туннель к S2 | `ping -c 2 -W 2 10.8.0.1` | 0% потерь, ~20 ms |
| NAT/форвардинг | `iptables -t nat -vnL POSTROUTING \| head` | `MASQUERADE` для `10.9.0.0/24` |

## 5. S2 (77.105.161.151) — ❌ ВЫВЕДЕН ИЗ ЭКСПЛУАТАЦИИ 31.10.2026

IP заблокирован РКН (подтверждено провайдером), смена на `77.105.161.66` не помогла.
Проверки ниже оставлены как исторический контекст, к живому S2 не применять.
Актуальный домашний шлюз — **S3** (`195.242.118.2`).

⚠️ С 29.10.2026 входящий трафик снаружи режется провайдером. Проверки «снаружи»
(с S1, S_RU, Panel) ожидаемо **проваливаются** — это не поломка сервера. Проверять
изнутри (`ssh` через туннель S1↔S2 или консоль провайдера).

| Сервис / порт | Команда | Ожидается |
|---------------|---------|-----------|
| `openvpn-server@server` | `systemctl is-active openvpn-server@server` | `active` |
| `pihole-FTL` (53, 8080) | `systemctl is-active pihole-FTL` | `active` |
| `x-ui` | `systemctl is-active x-ui` | `active` |
| Порт relay | `ss -tlnp \| grep ':10001'` | слушает (снаружи недоступен) |
| Порт `tg-proxy` | `ss -tlnp \| grep ':38417'` | слушает; **выведен из эксплуатации 30.10.2026** |
| Firewall | `ufw status verbose \| head -4` | `active`, default deny |
| NAT | `iptables -t nat -S POSTROUTING` | по одной `MASQUERADE` на подсеть |

## 6. S3 (195.242.118.2) — коммерческий exit + backup-туннель

| Сервис / порт | Команда | Ожидается |
|---------------|---------|-----------|
| `x-ui` (10001) | `systemctl is-active x-ui` | `active` — с 30.10.2026 порт 10001 держит x-ui; `xray-relay` остановлен/disabled |
| `x-ui` legacy-бот (встроен) | `systemctl is-active x-ui` + `journalctl -u x-ui --since -10min \| grep -icE 'getUpdates\|tls handshake'` | на **ноде** бот не настроен (`tgBotEnable` нет) — счётчик `0`; проверять только на мастере (§8) |
| `openvpn-server@home-backup` (8443/tcp) | `systemctl is-active openvpn-server@home-backup` | `active` |
| Порт relay | `ss -tlnp \| grep ':10001'` | `*:10001` |
| Порт `tg-proxy` (socks5) | `ss -tlnp \| grep ':38417'` | слушает (с 30.10.2026) |
| Firewall | `ufw status \| head -12` | `active`, default deny, `10001` только S_RU/S1 |
| Сертификат relay | `openssl x509 -enddate -noout -in /etc/xray/certs/server.crt` | self-signed, ~10 лет; при перевыпуске — обновить pin на S_RU |
| Выход в интернет | `curl -4 -s -o /dev/null -w '%{http_code}' https://api.telegram.org/` | `302` |
| OpenVPN-статус | `tail -5 /var/log/openvpn/status-home.log` | `ROUTING_TABLE,…,s1,…` |

## 7. S_RU (31.77.169.67) — entry-нода

| Сервис / порт | Команда | Ожидается |
|---------------|---------|-----------|
| `x-ui` | `systemctl is-active x-ui` | `active` |
| Порт входа | `ss -tlnp \| grep ':443'` | `xray` на `*:443` |
| Порт панели ноды | `ss -tlnp \| grep ':24167'` | `x-ui`, доступ ограничен ufw |
| Конфиг Xray | `/usr/local/x-ui/bin/xray-linux-amd64 run -test -c /usr/local/x-ui/bin/config.json` | `Configuration OK` |
| Порядок outbound | `python3 -c "…outbounds…"` (см. `diagnostic-commands.md`) | `to-s3-relay` первым (адрес **`10.11.0.2:10001`**, т.е. через tun0), `to-s2-relay` вторым |
| Туннель S_RU↔S3 `tun0` | `ip -4 addr show tun0` + `systemctl is-active openvpn-server@sru-transport` | `10.11.0.1/24`, `active`, `mtu 1300` |
| Связность через туннель | `ping -c 3 -W 2 10.11.0.2` | 0% потерь, ~42 ms (проверено 31.10) |
| Relay-путь живой | `timeout 8 bash -c 'cat < /dev/null > /dev/tcp/10.11.0.2/10001'` + `openssl s_client -connect 10.11.0.2:10001` | TCP OPEN, `CN=195.242.118.2`, verify code `18` (self-signed — ожидаемо, пин в конфиге) |
| Сквозной выход через relay | временный xray-конфиг socks→`to-s3-relay`, `curl --socks5-hostname … ifconfig.me` | `195.242.118.2` (проверено 31.10) |
| geo-split | тот же скрипт по `routing.rules` | `geosite:category-ru` → `direct`, `geoip:ru` → `direct` |
| Сертификат IP | `acme.sh --list` / `openssl x509 -enddate -noout -in /root/cert/ip/fullchain.pem` | renew ≤ 3 суток до истечения (короткоживущие LE) |
| Выход в интернет | `curl -s --max-time 5 https://ifconfig.me` | `31.77.169.67` |

## 8. Panel (31.77.78.144, netru.ru.net)

| Сервис / порт | Команда | Ожидается |
|---------------|---------|-----------|
| `x-ui` | `systemctl is-active x-ui` | `active` |
| `nginx` | `systemctl is-active nginx` | `active` |
| `netru-bot` | `systemctl is-active netru-bot` + `NRestarts` | `active`, `0` |
| Вебхук ЮKassa | `ss -tlnp \| grep 8711` | `127.0.0.1:8711` |
| Панель мастера | `ss -tlnp \| grep ':25305'` | `*:25305`, доступ по ufw |
| Подписки | `curl -k -s -o /dev/null -w '%{http_code}' https://netru.ru.net:2096/` | `404` (порт отвечает) |
| Серт домена | `openssl x509 -enddate -noout -in /etc/letsencrypt/live/netru.ru.net/fullchain.pem` | до 14.01.2027 (продлевается `certbot.timer`) |
| БД бота целая | `sqlite3 /opt/netru-bot/bot.db 'pragma integrity_check;'` | `ok` |
| Схема БД | `sqlite3 /opt/netru-bot/bot.db 'select version_num from alembic_version;'` | `0007` (текущая `head`) |
| Путь к БД | `grep DB_PATH /opt/netru-bot/src/.env` | `/opt/netru-bot/bot.db` (≠ каталог `WorkingDirectory`) |
| Токен «Мой налог» | `journalctl -u netru-bot --since -24h \| grep 'проверка токена' \| tail -1` | `ok` (проверка 09:00 МСК) |
| Диск / память | `df -h / \| tail -1`, `free -m` | диск < 80%, available > 150 МиБ |

### 8.1 Мониторинг входа S_RU с мастера (МСК) — Reality probe

Держать вход под наблюдением, потому что Reality-рукопожатие может умереть при живом
TCP: снаружи видно `TCP OPEN`, а TLS висит. Проверка двухступенчатая — TCP отдельно
от полезной нагрузки:

```bash
# 1) TCP (быстро, ловит сетевой блок)
timeout 6 bash -c 'cat < /dev/null > /dev/tcp/31.77.169.67/443'   # EXPECT rc=0

# 2) Реальное Reality-рукопожатие клиентом (ловит поломку xray/target)
python3 servers/sru/scripts/probe_reality.py sru --xray          # EXPECT rc=0, exit 31.77.169.67
python3 servers/sru/scripts/probe_reality.py s3 --xray           # контроль, EXPECT rc=0
```

Запускать с мастера (МСК): `ssh root@31.77.78.144 'python3 probe_reality.py sru --xray'`.

**Обязательно с `--xray`.** Без флага скрипт делает только `openssl s_client`, а он
в этот инцидент проходит (fallback отдаёт серт Cloudflare) и даёт **ложный OK**:
Reality ломается на аутентифицированном пути, а не на приёме ClientHello.
Проверено 31.10.2026: `probe_reality.py sru` → rc=0 «handshake OK»,
`probe_reality.py sru --xray` → rc=1 TIMEOUT. Параметры (UUID, `pbk`, `sid`, `sni`)
скрипт читает из мастера через API, в код их не хардкодить.

Пороги для алертов:

| Условие | Значение |
|---------|----------|
| TCP rc≠0 подряд 2 раза | алерт «вход S_RU недоступен по сети» |
| TCP OK, но Reality TIMEOUT подряд 3 раза (за 3 мин) | алерт «Reality-рукопожатие не отвечает» + прогон §8.2 |
| `ifconfig.me` вернул не `31.77.169.67` | алерт «выход сменился, проверить outbounds» |

Опрашивать с мастера **и** с домашнего ISP (S1 при провайдере AS216334 даёт
ложно-отрицательный результат: у него нет внешнего фильтра).

### 8.2 Диагностика «TCP OPEN, TLS висит» — порядок проверок

Проверено 31.10.2026 на S_RU; порядок отсекает ложные гипотезы за 5 шагов.

| Шаг | Проверка | Что отсекает |
|-----|----------|--------------|
| 1 | `openssl s_client -connect 127.0.0.1:443 -servername <sni>` **на самом S_RU** | если висит и на loopback — проблема серверная, не сеть. ⚠️ Прохождение этой проверки НЕ означает, что вход работает: fallback отдаёт серт цели, а Reality-путь может быть мёртв |
| 2a | `probe_reality.py sru --xray` (аутентифицированный клиент) | именно это показывает поломку: TCP OK + TLS OK + payload TIMEOUT |
| 2b | Свободный инстанс xray на `127.0.0.1:18443` со своими ключами и тем же `target` | конфиг/ключи/боевой процесс |
| 3 | Тот же инстанс с `target` = не-Cloudflare (`www.microsoft.com:443`) | привязка к конкретной цели |
| 4 | `openssl s_client` к `target` напрямую, 5 попыток | сетевая доступность цели (было 5/5 OK) |
| 5 | Обратный fallback: `openssl s_client` на 18443 с `-servername <target>` | должен вернуть серт цели — подтверждает, что «ключ+shortId» путь отдельный от fallback |

Ключевой признак в трассе: клиент отдаёт ClientHello (≈1893 B, видно SNI), сервер его
ACK-ает и **молчит**; при этом сервер сам открывает соединение к `target` и получает
SYN-ACK — значит зависает внутренний TLS к цели, а не приём.

## 9. Известные устойчивые отклонения (не считать аварией)

| Отклонение | Причина | Где |
|-----------|---------|-----|
| `ping 10.10.0.1` — 100% loss, tun2 почти без трафика | баг/сдвиг потока в OpenVPN `8443/tcp` (гипотеза 29.10, репродукция на loopback — открытая задача) | S1↔S3 |
| S2 не отвечает снаружи на любые порты | блокировка провайдера (тикет отправлен 29.10) | S2 |
| `S_RU → S2:10001` FAIL | следствие блокировки S2; рабочий выход — S3 | S_RU |
| `S_RU:443` — TCP OPEN, обычный TLS проходит, Reality-клиент висит (любая сеть, вкл. loopback и NL) | Reality с `target` = мёртвой цели не завершает внутренний TLS: сервер дёргает target, тот отвечает SYN-ACK и молчит. Было с `www.cloudflare.com` (31.10.2026) — привязка «IP 31.77.169.67 ↔ Cloudflare»; на S3 та же цель работала. **Исправлено 31.10.2026 сменой на `www.bing.com`.** Обычный TLS идёт через fallback — не путать с рабочим входом | S_RU |
| `list/paged` отдаёт пустой массив | особенность установки 3x-ui; читать через `get_client` | Panel |
| `TLS handshake error` на 2096 | внешние сканеры, ~56/сутки | Panel |

## 10. Периодические проверки (не чаще раза в неделю)

| Что | Команда/где | Порог |
|-----|-------------|-------|
| Сертификаты | S_RU `acme.sh --list`, Panel `certbot certificates` | продление за ≥3 суток до истечения |
| Диски | `df -h /` на всех четырёх | < 80% |
| БД и бэкапы | `sqlite3 … integrity_check`, `ls -la /opt/netru-bot/*.bak-*` | `ok`; бэкап не старше недели |
| Напоминания/рассылки | `select count(*) from reminder_deliveries where sent_at > …` | растёт при наступлении сроков |
| Последняя отправка в TG | `journalctl -u netru-bot \| grep 'Update id=' \| tail -1` | не старше суток |
| Xray-версии | `xray-linux-amd64 version` на S_RU/Panel/S3 | согласованы; S_RU фиксируется в `reference/versions.md` |
