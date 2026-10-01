# Задачи на следующую сессию

Живой файл: выполненное и записанное в документацию — удалять, файл оставлять.
Загрузить в начале сессии: `system-state.md`, `commercial/migration-3xui.md`, этот файл.
Обновлено 02.10.2026 (конец сессии: geo-split, документация, IP-сертификат S2 — выполнены).

---

## B. Технические задачи

### B7. Контроль продления IP-сертификатов (по датам)
**S_RU — после 03.10.2026 17:22 UTC** (`Le_NextRenewTimeStr` = 2026-10-03T17:03:21Z, cron `22 1,7,13,19 * * *`):
- `acme.sh --list` (новые даты), `openssl x509 -enddate -in /root/cert/ip/fullchain.pem`, `systemctl is-active x-ui`, 443 слушается, в `config.json` 5 правил routing, лог без ошибок.
- Текущий сертификат до 07.10.2026 01:23 GMT.

**S2 — после 05.10.2026 05:20 UTC** (продление ≈05:03 UTC, cron `42 1,7,13,19 * * *`):
- `acme.sh --list`, `enddate` для `/root/cert/ip/fullchain.pem`, 25307 отдаёт новый сертификат, 10001 жив (`sha256sum /etc/x-ui/certs/server.crt` начинается с `6b0e75c3`), нода S2 online на мастере.
- Текущий сертификат до 08.10.2026 12:20 GMT.

**Затем:** выключить «TLS skip verify» для ноды S2 на мастере (netru.ru.net:25305), подождать, убедиться что нода online; при проблеме — включить обратно. Для ноды S_RU (24167, тоже IP-сертификат LE) — аналогично после проверки (гипотеза, не проверена).

### B4. Тест `testS2` (клиент → S2 → интернет)
- Инбаунд `testS2` (порт 57651, reality) на S2; `decryption` был `mlkem768x25519plus` — для теста поставить `none` (в мастер-панели).
- Порт открывать на время: `ufw allow 57651/tcp comment 'testS2 (temporary test)'`, после теста `ufw delete allow 57651/tcp`.
- По итогам: оставить или удалить инбаунд.

### B5. Консоль провайдера S2
Поле `login:` не принимает ввод (getty активен, попыток login в журнале нет). Обратиться в поддержку провайдера; аварийный путь сейчас — только rescue-режим.

### B6. Прочее
- Panel: правило `25305/tcp Anywhere` — решение оператора (explicit-правила для доверенных IP уже есть).
- Panel↔ноды: периодический `TLS handshake error … i/o timeout` (Panel→S_RU:24167, Panel→S2:25307) без рестартов — не расследовано. Рестарты x-ui на нодах дают ожидаемые `fetch failed` на Panel.
- Причина прежнего сбоя relay на `yandex.com` не найдена (сайт теперь direct) — при случае проверить другие зарубежные сайты.
- Косметика: `comment` к правилу ufw 80/tcp на S_RU; удалить неиспользуемые `geo*_RU.dat`/`geo*_IR.dat` (~116 МБ) на S_RU; отключить NTP (123/udp) в Pi-hole.
- Долгосрочное (см. `system-state.md`): Telegram-бот под API 3x-ui, резервный канал S_RU↔S2, iOS-клиенты, скрипты развёртывания, бэкап домашней инфраструктуры.

---

## C. Предупреждения

- Не нажимать «Update Xray» на S_RU (вернёт v26.9.9 и баг Reality). S2 остаётся на Xray v26.9.9 намеренно.
- Изменения firewall на S2 — только через `ufw` (NAT в `/etc/ufw/before.rules`). Не использовать `iptables -I/-A` и без нужды `ufw reload` (возможен дубль NAT; после reload проверить `iptables -t nat -S POSTROUTING`: по одной строке на подсеть). Бэкап S2: `/root/fw-backup-20261001-143917/` (откат: `ufw --force disable`, `iptables-restore < iptables-live-final.v4`, без персистентности).
- Не трогать `/etc/x-ui/certs/server.crt` на S2 (relay 10001, pin на S_RU). Продление IP-сертификатов рестартит x-ui (Xray на секунды).
- Откат `x-ui.db` на S_RU — только через `/root/restore-xui-db.sh <бэкап>`: `/root/x-ui.db.backup-20261001-215924` (ДО geo-split), `/root/x-ui.db.good-geosplit-20261001-231259` (рабочее). На S2 бэкап перед сменой путей панели: `/root/x-ui.db.backup-s2-20261002-002336`.
- Тег RU-доменов — `geosite:category-ru` (не `geosite:ru`); правки geo-баз сразу проверять `xray run -test`.
- Не использовать `git add -A` (артефакт `secrets/.gitkeep`).
