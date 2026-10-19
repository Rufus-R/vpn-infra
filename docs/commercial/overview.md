# Коммерческий VPN-проект — Обзор

Актуально на 17.10.2026. Прежняя версия (Marzban, этап планирования, август–сентябрь 2026) —
[archive/overview-marzban-20260925.md](archive/overview-marzban-20260925.md).
Оперативный статус и журналы сессий — [operations-log.md](operations-log.md) и [../system-state.md](../system-state.md).

## Статус

Система работает. Сквозной канал подтверждён реальными клиентами 30.09.2026 (на тот момент —
МТС, МегаФон, Hiddify, v2rayNG), серверный geo-split на S_RU настроен 01.10.2026.
06.10.2026: Hiddify признан неподдерживаемым (см. «Клиенты и настройки» ниже), рекомендован Happ.

Telegram-бот: сценарий триала реализован, задеплоен на Panel (`/opt/netru-bot`, systemd) и
проверен живым тестом 08.10.2026 — см. `commercial/bot.md`. Позже реализованы согласие на обработку ПДн (10.10), «Тарифы» (09.10), «Поддержка» (11–12.10) и
«Мои подписки» (12–13.10); оплата и реферальные бонусы не реализованы (заявка ЮKassa одобрена,
вопрос чеков для самозанятого открыт — `next-session-todo.md`). ✅ 08.10.2026: кастомная страница подписки
«Штиль» реализована и включена (заменяет встроенный список клиентов, убирает несовместимый
Sing-box) — см. `commercial/sub-page-custom.md`. Не сделано: резервный канал S_RU↔S2,
iOS-клиенты из поддерживаемого списка (V2Box, OneXray) — не проверялись вживую,
Shadowrocket/Streisand исключены как несовместимые (sing-box). Тест `testS2` (инбаунд удалён 19.10.2026; клиент → S2
напрямую) пройден 02.10.2026.
16–17.10.2026: Panel переехал на новый сервер `31.77.78.144` (больше памяти); данные, бот, лендинг и
тема подписки «Штиль» перенесены, старый Panel `31.77.173.218` остановлен и будет отключён после 25.10.2026.
Полный список — [../next-session-todo.md](../next-session-todo.md) и раздел «Открытые вопросы» в `system-state.md`.

## Принцип изоляции

Коммерческий проект изолирован от домашней инфраструктуры (S1 — OpenVPN-хаб для family/friends).
На S1 ничего из коммерческого проекта не размещается, домашний OpenVPN не меняется.

Исключение — S2: физически общий хост (домашний Pi-hole + выходная нода коммерческого проекта).
Разделение — процессами и firewall (`ufw`), см. [../shared/networking/iptables-s2.md](../shared/networking/iptables-s2.md).
⚠️ У S2 709 MiB RAM — при росте коммерческого трафика выносить exit на отдельный VPS.

## Серверы

| Роль | Сервер | IP | Что работает |
|------|--------|-----|--------------|
| Мастер-панель | Panel | `31.77.78.144` (`netru.ru.net`) | 3x-ui master (25305), подписки (2096), БД клиентов, nginx (лендинг, `/oferta`, `/privacy`), Telegram-бот `netru-bot`; клиентский трафик не проксирует (старый Panel `31.77.173.218` остановлен, оплачен до 25.10.2026) |
| Entry (RU) | S_RU | `31.77.169.67` | 3x-ui нода (панель 24167), Xray: VLESS+Reality на 443, outbound `to-s2-relay`, geo-routing |
| Exit (EU) | S2 | `77.105.161.151` | 3x-ui нода (панель 25307), Xray: relay-инбаунд `s2-relay-in` на 10001 (VLESS+TLS) → direct |

Порты и доступы по каждому серверу — [../shared/reference/ports.md](../shared/reference/ports.md).

## Схема канала

```
Клиент (Happ / V2Box / v2rayNG — ядро Xray-core)
  │  VLESS + Reality (SNI www.cloudflare.com), :443
  ▼
S_RU (Xray, routing):
  ├─ geosite:category-ru, geoip:ru ───────────► direct (выход с IP S_RU)
  └─ всё остальное ─► to-s2-relay (VLESS+TLS, pin сертификата) ─► S2:10001 ─► direct ─► интернет
```

Подписки клиентам отдаёт только Panel (`https://netru.ru.net:2096/…`, путь подписки секретный и в документации не хранится).

## Geo-split (серверный, с 01.10.2026)

- Шаблон Xray на S_RU: `domainStrategy: IPIfNonMatch`; правила — api → api, `geoip:private` → blocked, bittorrent → blocked, `geosite:category-ru` → direct, `geoip:ru` → direct.
- Тег RU-доменов — `geosite:category-ru`; `geosite:ru` недопустим (категории `RU` в `geosite.dat` нет).
- Компромисс: RU-сервисы видят IP дата-центра S_RU, а не IP клиента (банки и Госуслуги при проверке 01.10 работают). Запасной вариант — клиентский geo-split через JSON-подписку Panel.
- Детали, процедура отката и тесты — [operations-log.md](operations-log.md), «Сессия 01.10.2026».

## Клиенты и настройки

- Поддерживаются только клиенты на ядре **Xray-core** (REALITY на Xray ≥ v26.9.8 требует
  `X25519MLKEM768` key share в ClientHello, которого нет в `sing-box`-based клиентах).
- Рекомендуемые: **Happ** (iOS/Android/macOS/Windows/Linux — основной), V2Box, OneXray (iOS),
  V2ray VPN Client: Xray Vless (Android), v2rayNG (Android, вне маркета, GitHub-релизы).
- НЕ поддерживаются (ядро `sing-box`, несовместимость с REALITY): Hiddify, Shadowrocket,
  Karing. Диагностика и источник — [operations-log.md](operations-log.md), «Сессия 06.10.2026».
- Mux включён на клиенте (TCP+XUDP, concurrency 8).
- TLS fingerprint: `firefox` — обязателен для МегаФона.
- Reality: dest/SNI `www.cloudflare.com` (SNI `ozon.ru`/`vk.com` блокировал МегаФон). Ключи Reality в документации не хранятся.

## Версии Xray (синхронизированы с 03.10.2026)

- S_RU и S2: `v26.9.30` (обновлено автоматически вместе с панелью до v3.9.0, 03.10.2026). Прежняя регрессия Reality-хендшейка (v26.9.9, инцидент 29–30.09.2026) НЕ воспроизвелась: `testS2` (прямое подключение к S2) и реальные клиенты на S_RU:443 работают штатно (проверено 02–04.10.2026).

## Сертификаты и DNS

- Panel: Let's Encrypt для `netru.ru.net` (certbot, `certbot.timer`; действует до 14.01.2027).
- DNS: зона `netru.ru.net` на Cloudflare (режим «DNS only», NS `ali.ns.cloudflare.com`, `dexter.ns.cloudflare.com`) с 12.10.2026; DNSSEC включён в Cloudflare, но DS у регистратора не добавлен (pending) — см. `next-session-todo.md`.
- S_RU: IP-сертификат `31.77.169.67` (`acme.sh`, профиль `shortlived`, ~6 дней, HTTP-01 на 80/tcp). Продление перезапускает `x-ui` (Xray падает на секунды).
- S2 панель ноды (25307): IP-сертификат Let's Encrypt (`acme.sh`, shortlived, с 02.10.2026, `/root/cert/ip/`); продление перезапускает `x-ui` и рвёт relay на секунды.
- S2 relay: самоподписанный `/etc/x-ui/certs/server.crt`, на S_RU стоит pin (`pinnedPeerCertSha256`) — файл не менять.

## Принятые риски

1. 3x-ui официально позиционируется как проект «для личного обучения», не для продакшена (решение принято осознанно, пересмотреть при нестабильности).
2. Единственный канал S_RU→S2: при блокировке нужен резервный (AmneziaWG, OpenVPN/UDP, Shadowsocks-2022 — не реализован; AmneziaWG без доработки не даёт geo-split).
3. Whitelist-блокировка в жёстком варианте (только гос. сервисы) не решается архитектурой.
4. Лимит устройств — soft (по числу выданных конфигов), технически не enforced.
5. Антифрод триала — с 10.10.2026 держится ТОЛЬКО на `tg_id`/`trial_used` (номер телефона исключён из сбора — решение оператора, связка Telegram ID + username признана персональными данными по 152-ФЗ, избегаем сбора дополнительных ПДн). Риск обхода повторного триала ВЫШЕ, чем было при проверке по телефону — принимается для MVP.
6. Причина прежнего сбоя relay на `yandex.com` не найдена; сайт теперь идёт direct, другие зарубежные сайты не проверялись.
7. Платежи: Robokassa отказала самозанятому (15.10); у ЮKassa автоотправка чеков для самозанятых прекращена 29.12.2025 (по данным поиска, не проверено на нашей учётке) — схема чеков не выбрана, приём реальных платежей не включён.
8. DNSSEC для `netru.ru.net` не завершён: DS в зоне `ru.net` отсутствует (проверено 17.10.2026).

## Юридические документы и лендинг: сборка и выкладка

Каталог `/root/commercial-legal/` на S1 — вне git (README внутри ссылается сюда). Лендинг на Panel (`/var/www/netru-landing/`: `index.html`, `oferta.html`, `privacy.html`, значки `favicon.ico`, `favicon.png`, `apple-touch-icon.png`) тоже в git не хранится.

- Источники текстов: `oferta.md`, `privacy-policy.md` (Markdown). `privacy-policy.notes.md` и файлы `*.bak-20261011` на сайт не выкладываются (при выкладке 11.10.2026 проверялось отсутствие утечки примечаний).
- Конвертер: `python3-markdown` (на S1 python-markdown 3.5.2, `markdown_py`), расширение `tables`. Подтверждено 19.10.2026: тело страницы, собранное из `.md`, совпало с телом `landing/oferta.html` и `landing/privacy.html` знак в знак; журнал сессии 11.10 (`commercial/archive/operations-log-sessions-2026-10-08_2026-10-13.md`) называет тот же способ.
- Скрипт сборки: `/root/commercial-legal/build-pages.py` (вне git, создан 19.10.2026; прежний скрипт был восстановлен из `.bash_history` и не сохранён). Запуск: `python3 /root/commercial-legal/build-pages.py`. Шаблон (стили, обёртка `.wrap`, `<footer>`) берёт из `landing/*.html`, тело — из `.md`, перед `</head>` вставляет три тега значков; пишет в `landing-build/`, `landing/` не меняет; `index.html` копирует с тегами (это не конвертация).
- Проверено 19.10.2026: `landing-build/` совпадает с файлами на Panel (`diff` пуст по всем трём страницам). Каталог `landing/` остаётся прежним, без тегов значков; решение, заменять ли его на `landing-build/`, не принято.
- Выкладка на Panel (процедура, не опробована, при необходимости): бэкап трёх файлов на Panel; `scp` из `landing-build/` в `/var/www/netru-landing/`; проверка `curl -s -o /dev/null -w '%{http_code}'` для `/`, `/oferta`, `/privacy`, `/favicon.ico`; перечитать страницы глазами. Права файлов на Panel — 644, владелец root; nginx менять не нужно (`location /oferta` и `/privacy` отдают `oferta.html` и `privacy.html`).
- Оферта п.4.4 (формулировка про чеки) ждёт выбора схемы чеков, см. `../next-session-todo.md`, 2.1. Изменение оферты — правка `oferta.md`, затем сборка и выкладка.

## Связанные документы

- [operations-log.md](operations-log.md) — миграция, журналы сессий, процедуры
- [tariffs.md](tariffs.md) — тарифная сетка, триал, рефералка; ⚠️ устарел (не менялся с 22.09.2026, placeholder-цены), фактический источник — `servers/panel/bot/app/db/seed.py`
- [bot.md](bot.md) — схема БД бота, интеграция с API 3x-ui, сценарии; реализованы триал, тарифы, «Мои подписки», «Поддержка», согласие на ПДн; оплата не реализована
- Архив Marzban-эпохи: [archive/overview-marzban-20260925.md](archive/overview-marzban-20260925.md), [archive/routing-marzban-20260925.md](archive/routing-marzban-20260925.md), [archive/deployment-marzban-20260925.md](archive/deployment-marzban-20260925.md), [archive/known-issues-marzban-20260925.md](archive/known-issues-marzban-20260925.md)
