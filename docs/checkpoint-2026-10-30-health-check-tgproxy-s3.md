# Чекпоинт 30.10.2026 — проверка проекта, чек-лист сервисов, перенос `tg-proxy` на S3

Сессия: плановая проверка проекта после инцидента S2 (29.10). Итог: инфраструктура
жива, найден и устранён **незафиксированный ранее инцидент — Telegram-бот 17 часов
не получал апдейты**.

## 1. Что проверено (read-only)

| Область | Результат |
|---------|-----------|
| Репозиторий OpenHands-клона | `main` = `origin/main`, чисто |
| `ruff check` (только `F`/`E9`) | 2 замечания: `F541` `app/handlers/support.py:128` (лишний `f`), `F841` `app/main.py:54` (`resume_task` не используется) — не исправлялись, поведение не затрагивают |
| Битые относительные ссылки `docs/` | 0 в живых документах, 15 в `archive/` (исторические) |
| `secrets/` | git-crypt активен на всех файлах, содержимое не читалось |
| S1 | все юниты `active` (`openvpn-server@server`, `openvpn-client@s2-client`, `openvpn@s3-backup`, `vpn-admin`); `tun0` → `10.8.0.1` 0% потерь; 4 клиента в `status-tun1.log`; ufw нет (iptables) |
| S2 | снаружи недоступен (ожидаемо — блокировка провайдера); изнутри не проверялся |
| S3 | `xray-relay` active (10001), `openvpn-server@home-backup` active, handshake от S1 есть, трафик через туннель не идёт |
| S_RU | `x-ui` active, `Configuration OK`, outbound order `to-s3-relay`→`to-s2-relay`, IP-серт до 04.11.2026 |
| Panel | `x-ui`/`nginx`/`netru-bot` active, `NRestarts=0`, БД `integrity_check ok`, alembic `0007`, серт до 14.01.2027, диск 54% |

## 2. Инцидент: бот не получал апдейты Telegram (29–30.10)

**Симптом.** 604 ошибки `Failed to fetch updates — TelegramNetworkError: HTTP Client
says - Request timeout error` подряд, ~56/час, начиная с 29.10 ~18:00 МСК. Последний
обработанный апдейт — `Update id=889734813`, 29.10 01:15 МСК. При этом вебхук ЮKassa
(`127.0.0.1:8711`) и чеки «Мой налог` работали: сбой был только в канале к
`api.telegram.org`.

**Причина.** `TG_PROXY_URL` в `/opt/netru-bot/src/.env` указывал на socks5 `tg-proxy`
на **S2** (`77.105.161.151:38417`). S2 заблокирован провайдером с 29.10, TCP до 38417
с Panel — fail. В сессии 29.10 exit-роль перенесли на S3, а прокси бота, живущий
на том же S2, остался забыт.

**Проверка альтернатив (все read-only):**
- Panel → `api.telegram.org` напрямую: DC `149.154.167.220:443` — `302`, `getMe` — `200`;
  DC `149.154.166.110:443` — таймаут. Прямой режим частично работает, но нестабилен.
- S3 → `api.telegram.org` — `302`, оба DC доступны.
- На Panel своего socks/mtproto-прокси нет (`ss -tlnp` — только 22/80/443/2096/25305).

**Решение (принято оператором): socks5 на S3.**

1. `/etc/xray/config.json` на S3 — добавлен inbound `in-38417-socks`
   (`protocol: socks`, `auth: password`, `udp: false`, `ip: 127.0.0.1`,
   listen `0.0.0.0:38417`), правило `in-38417-socks → direct` перед правилом relay.
   Бэкап: `/root/xray-config.json.bak-20261030-pre-tgproxy`. `xray run -test` —
   `Configuration OK`, `systemctl restart xray-relay` — `active`, `*:38417` слушается.
2. `ufw allow from 31.77.78.144 to any port 38417 proto tcp comment 'tg-proxy from Panel'`.
3. Panel: `TG_PROXY_URL=socks5://<user>:<pass>@195.242.118.2:38417`, бэкап `.env` —
   `/root/netru-bot.env.bak-20261030-pre-tgproxy`, `systemctl restart netru-bot`.

**Проверка после правки:**
- локально на S3: `curl --socks5-hostname` → `302`; неверные учётные данные → `000`
  (аутентификация включена);
- с Panel: `curl --socks5-hostname` → `302`; `getMe` → `{"ok":true,…}`;
- бот 11:32 МСК: `Start polling`, `Failed to fetch updates` — **0** за 20+ минут,
  `tryings =` — 0, проверка токена «Мой налог» — `ok`;
- вебхук ЮKassa слушает (`127.0.0.1:8711`).

⚠️ Важный вывод: бот и вебхук ЮKassa — **один процесс**. Пока бот не поллит, оплата
принимается, но сообщения клиентам и админам не уходят; падение процесса останавливает
и приём платежей.

## 3. Документация и репозиторий

- `docs/service-checklist.md` — новый чек-лист сервисов (критичное, матрица
  зависимостей, grep-признаки деградации, разделы по 4 серверам, устойчивые
  отклонения, периодические проверки).
- `docs/shared/reference/ports.md` — S2:38417 помечен выведенным из эксплуатации,
  S3:38417 — новый прокси бота + детали реализации inbound.
- `docs/diagnostic-commands.md` — новый раздел S3 (сервисы, ufw, проверка прокси,
  конфиг/серт, OpenVPN), расширен раздел Panel (поллинг бота, вебхук, `NRestarts`),
  правило про `DB_PATH` и пустышку `src/bot.db`.
- `docs/commercial/bot.md` — п. 3 «Открытые вопросы» переписан (прокси на S3),
  п. 4 (тарифы) закрыт: сверка `plans` Panel с `seed.py` 30.10.2026 — совпадают.
- `docs/commercial/tariffs.md` — пометка «устарел» снята, добавлена дата сверки.
- `docs/system-state.md` — S3: добавлена роль `tg-proxy`.
- `servers/s3/relay-node/xray-config-template.json` — добавлен inbound `in-38417-socks`
  (плейсхолдеры учётных данных).
- `servers/s3/bootstrap-s3.sh` — генерирует учётные данные прокси, пишет
  `/run/tgproxy_creds`, добавляет ufw-правило, проверяет порт, печатает `S3_TG_PROXY`.
- `servers/s3/relay-node/runbook-s3.md` — роль `tg-proxy` в разделе «Роли S3».

## 4. Уборка и мелочи

- Удалён пустой артефакт `/opt/netru-bot/src/bot.db` (0 B, 30.10 10:54) — создан
  диагностическим `sqlite3`-запросом к несуществующему файлу в `WorkingDirectory`.
  Правило добавлено в `diagnostic-commands.md`.
- Рабочая копия `/root/vpn-infra` на S1 была позади `origin/main` на 3 коммита —
  синхронизирована `git pull --ff-only`.

## 5. Открыто (перенесено в `next-session-todo.md`)

1. Туннель S1↔S3 `home-backup` (8443/TCP): трафик не проходит, гипотеза сдвига потока
   (раздел 7.1).
2. Ответ провайдера S2, переустановка, возврат relay как hot-standby; затем вернуть
   `TG_PROXY_URL` на S2 (или оставить S3).
3. `ruff`: `F541` `support.py:128`, `F841` `main.py:54`.
4. `family` и напоминания: `end_at=2036` вне горизонта — ок, но формулировка в
   `reminders.py` считать по `status`, а не только по дате (косметика, не срабатывает).
5. Тестов в `servers/panel/bot` нет (долг).

## 6. Откат изменений этой сессии

| Что | Откат |
|-----|-------|
| Прокси бота на S3 | `cp /root/netru-bot.env.bak-20261030-pre-tgproxy /opt/netru-bot/src/.env` + `systemctl restart netru-bot` (вернёт S2-прокси, который сейчас не работает — только если S2 разблокирован) |
| Xray на S3 | `cp /root/xray-config.json.bak-20261030-pre-tgproxy /etc/xray/config.json` + `systemctl restart xray-relay`; `ufw delete allow from 31.77.78.144 to any port 38417 proto tcp` |
