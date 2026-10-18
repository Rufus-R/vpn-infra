# Чекпоинт 17.10.2026 (вечер) — платёжная схема: ЮKassa + чеки «Мой налог»

Самодостаточная запись: свежая сессия может продолжить с неё без переписки. Предыдущий чекпоинт
(синхронизация документации) выполнен: `checkpoint-2026-10-17-docs-sync.md`, раздел 9.

## 1. Решения оператора

- Платежи — только ЮKassa. Platega и другие провайдеры не рассматриваются; разделение приёма
  платежей на «официальный» и «неофициальный» не делаем (ассистент в этом не помогает: доход
  остаётся доходом владельца сервиса независимо от вывески).
- Чеки — через API «Мой налог» с подтверждением админа: оплата ЮKassa → вебхук → бот перепроверяет
  платёж запросом к API ЮKassa → бот формирует черновик чека и отправляет админу → админ нажимает
  «Отправить в налоговую» → бот вызывает API, получает ссылку на чек и отправляет её пользователю.
- Оператор сообщил, что в приложении «Мой налог» можно создать «ключ доступа». Что это за функция и
  подходит ли она для API — НЕ подтверждено: поиск 17.10 нашёл только неофициальные клиенты
  `lknpd.nalog.ru` (вход по ИНН и паролю либо по телефону/SMS, refresh-токен), официального ключа
  не найдено. Уточнить у оператора название экрана. Секрет в чат не вставлять.

## 2. Факты о коде (проверено 17.10.2026)

- `servers/panel/bot/app/`: `config.py` (69 строк), `db/models.py` (117), `db/base.py` (30,
  `create_all`), `handlers/tariffs.py` (207), `handlers/support.py` (206), `keyboards.py` (63),
  `main.py` (28), `panel_api.py` (133), `requirements.txt` (7 строк: есть `aiohttp-socks`).
- Хендлеры `admin:confirm:` (tariffs.py:95) и `admin:reject:` (tariffs.py:177) недостижимы, кнопки
  в `keyboards.py:52-53`; остались от отключённой fallback-оплаты.
- `payments`: id, user_id, subscription_id, amount (копейки), provider VARCHAR(16),
  provider_payment_id, status VARCHAR(16), created_at. Полей чека нет. `Plan.price` — в копейках
  (`seed.py`: `price_rub * 100`). В чек идут рубли.
- Имена настроек в `config.py`: ADMIN_IDS, BOT_TOKEN, DB_PATH, PANEL_API_BASE, PANEL_API_TOKEN,
  PANEL_API_TOKEN_FILE, PANEL_API_VERIFY_TLS, PAYMENT_REQUISITES_TEXT (мёртвая), REALITY_INBOUND_ID,
  SUB_BASE_URL, TG_PROXY_URL.
- Запись в `bot.db` на новом Panel подтверждена 17.10 (тест «Поддержка», `support_messages` = 10,
  `journal_mode = delete`).

## 3. Проект (не реализовано)

- Отдельная таблица `receipts`: `payment_id` (UNIQUE), `status`, `amount` (копейки), `service_name`,
  `receipt_uuid`, `receipt_url`, `error`, `created_at`, `sent_at`.
- Статусы: `pending_review`, `sending`, `sent`, `failed`, `unknown`, `rejected`, `cancelled`.
- Интерфейс `ReceiptProvider`: реализация `LknpdReceipt` (API) и всегда доступный запасной путь —
  админ вставляет ссылку на чек вручную.
- Идемпотентность: один платёж — один чек; перед вызовом API статус атомарно переводится в `sending`.
- Неопределённый результат (таймаут после отправки) — автоматически не повторять: статус `unknown`,
  админ сверяет в «Мой налог».
- Отмена чека по кнопке админа (возвраты); не проверено на практике.
- Секреты «Мой налог» и ЮKassa — в `.env` на Panel (права 600), не в git, не в логах; при протухшем
  токене — уведомление админу, платёж и подписка от чека не зависят.
- Кнопки: `receipt:send:{id}`, `receipt:reject:{id}`, отдельно от старых `admin:*`.

## 4. План

0. Бэкап `bot.db` (на Panel). Перед правками сверить `WorkingDirectory` юнита и `DB_PATH`
   (правило `next-session-todo.md`, раздел 6). Alembic: базовая ревизия на текущую схему.
1. Миграция `receipts`; новые настройки (ЮKassa, «Мой налог»).
2. ЮKassa: `create_payment` с ключом идемпотентности; вебхук (aiohttp, секретный путь в nginx,
   порт-кандидат 8711 — проверить свободен ли); перепроверка платежа запросом к API ЮKassa; продление
   через `bulkAdjust` (`update/{email}` — full-replace).
3. Уведомление админу с черновиком чека и кнопками; ручной ввод ссылки.
4. Клиент «Мой налог» (после уточнения способа входа); тест на минимальной сумме; тестовый магазин
   ЮKassa.
5. Оферта п.4.4 (`/root/commercial-legal/` на S1, вне git); срок выдачи чека — проверить у бухгалтера
   или в «Мой налог» и настроить напоминание; обновить `bot.md`, `next-session-todo.md` (2.1).

## 5. Открыто

- Что такое «ключ доступа» в «Мой налог» (раздел 1).
- Срок выдачи чека самозанятым для платежей онлайн.
- Тестовый магазин ЮKassa: данные у оператора.
- Оферта п.4.4 — формулировка про чеки.
- Остальное по срокам: `next-session-todo.md` (отказ от старого Panel до 25.10, DNSSEC).

## 6. Первые команды новой сессии (только чтение)

```bash
cd /root/vpn-infra && cat docs/checkpoint-2026-10-17-payments.md && cd servers/panel/bot \
 && cat app/db/models.py app/db/base.py app/main.py requirements.txt
ssh -n root@31.77.78.144 "systemctl cat netru-bot | grep -E 'WorkingDirectory|ExecStart'; \
 grep DB_PATH /opt/netru-bot/src/.env; /opt/netru-bot/venv/bin/pip list 2>/dev/null | grep -i -E 'alembic|aiogram|aiohttp|sqlalchemy'"
```

## 7. Уточнение (17.10.2026, позже): способ входа в «Мой налог»

Заменяет формулировки о «ключе доступа» в разделах 1 и 5.

- Оператор входит в «Мой налог» по номеру телефона и SMS. Экран «Внешний доступ (Ключ доступа)» в
  приложении выдаёт контрагенту доступ только на чтение данных в ПП НПД (со сроком действия и
  возможностью аннулировать), создавать чеки он не позволяет — для интеграции не используется и пока
  не создаётся.
- Остаётся неофициальный API `lknpd.nalog.ru` с входом по телефону: двухшаговый (запрос SMS-кода,
  затем ввод кода) с выдачей refresh-токена; срок действия токена на практике не проверен.
- Решение по проекту: вход делается одноразовым скриптом на Panel по SSH (код вводится в терминале,
  не в Telegram), токен хранится в файле с правами 600 вне git; бот токен только читает. При
  истёкшем токене бот пишет админу «нужен повторный вход».
- Порядок проверок API: сначала только чтение (профиль или сводка доходов), без создания чека; затем
  чек на минимальную сумму и сразу аннулирование.

## 8. Ход выполнения (17–18.10.2026): шаг 0 — Alembic подготовлен, НЕ развёрнут

Сделано и закоммичено (в бой не выкатывалось, бот на Panel работает на прежнем коде):
- `servers/panel/bot/alembic.ini`, `migrations/env.py` (sync `sqlite:///{DB_PATH}`, `render_as_batch`),
  `migrations/script.py.mako`, ревизия `0001` (baseline, сгенерирована из моделей) и `0002`
  (таблица `receipts`); модель `Receipt` в `app/db/models.py`.
- Проверено на копии боевой БД (Panel, `/tmp`): `stamp 0001` → `upgrade head` → `alembic check`
  без расхождений; счётчики строк до/после совпали; `downgrade -1` и повторный `upgrade` прошли;
  на пустой БД миграции с нуля и `check` тоже чистые.
- Бэкап боевой БД до миграций: `/opt/netru-bot/bot.db.bak-20261017-pre-alembic` (права 600,
  `integrity_check` = ok) — перед деплоем снять свежий.

Окружение на Panel: код в `/opt/netru-bot/src` (= `WorkingDirectory`), `DB_PATH=/opt/netru-bot/bot.db`,
venv `/opt/netru-bot/venv` с alembic 1.13.3, SQLAlchemy 2.0.35, httpx 0.27.2, aiohttp 3.10.11,
aiogram 3.13.1. Сухой `rsync` репозиторий→Panel показал единственное расхождение: на Panel лишний файл
`.env.bak-before-http-fix` (копия `.env`, секреты) — удалить по согласованию оператора.

Мусор на Panel после проверок (удалить): `/tmp/bot-gen/`, `/tmp/bot-alembic-check.db`,
`/tmp/bot-alembic-run.db`.

Порядок деплоя (следующая сессия), потому что текущий `init_db()` через `create_all` создал бы
`receipts` в обход Alembic и `upgrade head` упал бы:
1. Остановить `netru-bot`; свежий бэкап `bot.db` (SQLite backup API).
2. Заменить в `app/db/base.py` `create_all` и `_add_missing_columns` запуском миграций
   (`alembic upgrade head`: через `command.upgrade` в `asyncio.to_thread` либо `ExecStartPre`).
3. `rsync` кода на Panel БЕЗ `--delete` (исключить `.env*`, `venv`, `__pycache__`).
4. Один раз вручную `alembic stamp 0001` на боевой БД, затем `alembic upgrade head`.
5. Запустить бота; проверить «Поддержку» и «Мои подписки»; `systemctl status netru-bot`.
6. Тестовые строки в боевой БД (`payments.id=1`, подписка в `pending_payment`) — чистить по todo 1.2.

Дальше по плану раздела 4: ЮKassa (create_payment, вебхук), уведомление админу и кнопки, скрипт входа в
«Мой налог», клиент API, оферта п.4.4.

## 9. Ход выполнения (18.10.2026): Alembic развёрнут на Panel

Заменяет формулировку «НЕ развёрнут» и порядок деплоя из раздела 8.
- Код (коммит `03e9dcd`): `init_db()` (`app/db/base.py`) выполняет `alembic upgrade head` через `asyncio.to_thread`; `create_all` и `_add_missing_columns` удалены; в `main.py` изменён комментарий. Выбран запуск из `init_db()`, а не `ExecStartPre`: юнит systemd не менялся, миграции применяются при любом способе старта, при сбое миграции бот не стартует.
- Проверка до боя на копии боевой БД (Panel, боевой venv): копия без `stamp` падает с `OperationalError`; после `stamp 0001` — `init_db()` OK, `alembic current` = `0002 (head)`, `alembic check` чистый, счётчики строк и `integrity_check` без изменений, повторный `init_db()` идемпотентен.
- Деплой (около 02:44–02:47 MSK): бот остановлен; бэкап `/opt/netru-bot/bot.db.bak-20261018-pre-alembic-deploy` (600, `integrity_check` ok) и архив прежнего кода `/root/netru-bot-src-pre-alembic-20261018.tgz` (без `.env`); `rsync` без `--delete`; на боевой БД `stamp 0001` → `upgrade head`; счётчики до/после совпали (users 7, plans 7, subscriptions 6, payments 1, referral_bonuses 0, support_messages 10); бот запущен, `Start polling` без ошибок.
- Живой тест: «Мои подписки» и «Поддержка» (сообщение дошло админу, ответ доставлен пользователю); `support_messages` 12, `alembic_version` = `0002`, `receipts` пуста.
- Уборка: удалены `.env.bak-before-http-fix` на Panel (копия `.env` с секретами) и временные файлы в `/tmp`.
- Не сделано: чистка бэкапов деплоя и тестовых строк `payments.id=1`, `subscriptions.id=4` — `next-session-todo.md`, 1.2 (наличие тестовых строк в этой сессии не проверялось).
- Дальше по плану раздела 4, шаги 2–5: ЮKassa (`create_payment`, вебхук), уведомление админу с черновиком чека и кнопками, одноразовый скрипт входа в «Мой налог» (раздел 7), клиент API, оферта п.4.4.
