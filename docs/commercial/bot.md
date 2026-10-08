# Telegram-бот — схема и сценарии (актуализировано под 3x-ui)

Актуально на 04.10.2026. Предыдущая версия (под Marzban API) не сохранена отдельно — архитектура
клиентов в 3x-ui принципиально иная (централизованная модель на мастер-панели), переиспользовать
старую схему 1:1 нельзя.

## Статус

Реализация начата 08.10.2026: сценарий активации триала полностью работает и проверен живым
тестом в Telegram (`@netrurunet_bot`, бот «Штиль VPN») — создание пользователя, FSM-запрос
контакта (антифрод по телефону), создание клиента на S_RU через API мастер-панели, выдача
рабочей ссылки подписки. Бот развёрнут на Panel (`/opt/netru-bot`, systemd-юнит
`netru-bot.service`, enabled+running). Архитектурные решения приняты оператором 03–04.10.2026.
API мастер-панели верифицирован 04.10.2026 реальными вызовами на боевой Panel — все пункты B8
закрыты. Подтверждён критичный факт: `update` выполняет full-replace, не patch (обнуляет
непереданные поля, включая отключение клиента) — см. правило использования в разделе
«Интеграция с API Panel», пункт 5; в коде это учтено (`_normalize_for_update`,
`update_client_safe`). Не реализовано: разделы «Тарифы», «Мои подписки», оплата (ЮKassa и
fallback), реферальные бонусы, admin-уведомления, Alembic-миграции (сейчас
`Base.metadata.create_all()` при старте — временное dev-решение).

## Архитектурные решения (приняты 03–04.10.2026)

1. **Хостинг бота и БД** — на сервере Panel (`31.77.173.218`, `netru.ru.net`). Там же живёт
   мастер-панель 3x-ui, с которой бот будет работать через API.
   - ⚠️ Ресурсы Panel ограничены: 553 MiB RAM, после удаления Docker (03.10.2026) available
     выросла со 157 до 285 MiB. Это определило выбор БД (см. ниже).
2. **БД бота — SQLite** (не Postgres — легче по памяти, вписывается в ресурсы Panel).
   Доступ из Python — через SQLAlchemy 2.0 (async, драйвер `aiosqlite`), миграции — Alembic
   (работает с SQLite так же, как с Postgres).
3. **Создание клиентов — через API мастер-панели (Panel), не напрямую к нодам.**
   Подтверждено практикой оператора и схемой БД `x-ui.db` на Panel (3x-ui v3.9.0): таблицы
   `clients`, `client_inbounds` (many-to-many), `api_tokens` — централизованная модель клиентов,
   отличная от схемы «клиент живёт в JSON каждого inbound» в старых версиях x-ui. Мастер хранит
   клиента один раз и сам раздаёт/синхронизирует его на нужные ноды и инбаунды.
   - ✅ **Верифицировано 04.10.2026 реальными вызовами на боевой Panel** — см. раздел
     «Интеграция с API Panel» ниже. Чеклист из `next-session-todo.md` B8 в основном закрыт,
     остался один критичный пункт (поведение `update`, см. ниже).
4. **Множественные входы на клиента.** Таблица `client_inbounds` на Panel поддерживает
   привязку одного клиента сразу к нескольким inbound (many-to-many, подтверждено практикой —
   тестовый клиент создавался с `inboundIds` в одном вызове). Решение оператора:
   продакшн-клиенты бота должны получать **несколько входов** — основной (`reality-entry` на
   S_RU, geo-split) и **резервный прямой доступ к S2** (и, возможно, к будущим узлам) —
   но НЕ через диагностический `testS2` (там `decryption=none`, ослабленное шифрование).
   Нужен отдельный боевой инбаунд с полным шифрованием — задача `s2-direct-entry`
   (см. `next-session-todo.md`, статус: не начата, отдельная от бота задача).
5. **Лимит устройств — через нативный `limit_ip` 3x-ui** (подтверждено оператором
   04.10.2026 и практикой — поле `limitIp` в API, колонка `limit_ip` в БД), а не через создание
   N отдельных клиентов (как было в старой Marzban-схеме). Тариф "N устройств" = один клиент
   с `limit_ip=N`, привязанный к нужным инбаундам. Упрощает схему БД бота и работу с API.
6. **Оплата.** Приоритет — **ЮKassa** (самозанятость, регистрация завершается оператором).
   Ручное подтверждение (перевод + кнопка «Я оплатил» + подтверждение админом) остаётся как
   fallback на время, пока ЮKassa не подключена, и как резерв на случай сбоя платёжного шлюза.
   План внедрения:
   - Webhook ЮKassa — HTTPS-эндпоинт на домене `netru.ru.net` (сертификат уже есть на Panel),
     отдельный путь с секретным токеном в URL (аналогично скрытым путям подписки/панелей),
     например `/yookassa-webhook/<секрет>/`.
   - Нужно: секретный API-ключ ЮKassa (появится после завершения регистрации), настройка
     вебхука в личном кабинете ЮKassa на этот URL.
   - Создание чека для самозанятых («Мой налог») — уточнить API ЮKassa для автоформирования
     чека или делать это отдельно (ручной ввод в приложение «Мой налог» по данным платежа).
7. **Тарифы и скидки — таблица в БД бота, настраиваемая через админ-интерфейс/БД напрямую**,
   не хардкод в коде. Множители за доп. устройства и скидки на длительные сроки (сейчас не
   зафиксированы, см. `tariffs.md`) задаются в этой таблице и могут меняться без деплоя кода.

## Технологии

- Python 3.12 (уже установлен на Panel), aiogram 3.x
- Режим: long polling через socks5-прокси `tg-via-s2` (см. `system-state.md`, п.17) —
  Telegram заблокирован для исходящих с IP Panel напрямую; бот будет использовать тот же
  прокси-канал, что и встроенный бот панели, либо отдельный outbound с теми же параметрами.
- БД: SQLite + SQLAlchemy 2.0 (async, `aiosqlite`) + Alembic
- HTTP-клиент к API Panel: `httpx` (async)

## Схема данных (обновлена под модель 3x-ui)

⚠️ Таблица `users` в самой БД 3x-ui (`x-ui.db` на Panel) — это **админские аккаунты панели**
(логины в веб-UI), не имеет отношения к пользователям бота ниже. У бота будет собственный
файл SQLite, отдельный от `x-ui.db`, но имена сущностей совпадают — не путать при чтении схем.

```
users
├── id (PK)
├── tg_id (unique)
├── phone_number (nullable, unique когда указан)
├── username
├── referrer_id (FK -> users.id, nullable)
├── trial_used (bool, default false)
├── created_at

plans
├── id (PK)
├── name
├── duration_days
├── device_count              -- используется как limitIp при создании клиента (см. решение 5)
├── price
├── discount_pct (nullable)   -- настраиваемая скидка, не хардкод

subscriptions
├── id (PK)
├── user_id (FK)
├── panel_client_email        -- идентификатор клиента на Panel (поле email таблицы clients)
├── panel_client_uuid         -- uuid клиента (для Reality/VLESS)
├── panel_client_sub_id       -- subId клиента (для ссылки подписки / subLinks)
├── inbound_ids                -- JSON-список id инбаундов, к которым привязан клиент
├── plan_id (FK)
├── start_at
├── end_at
├── status (trial/active/expired)

payments
├── id (PK)
├── user_id (FK)
├── subscription_id (FK)
├── amount
├── provider (manual/yookassa)
├── provider_payment_id (nullable)   -- ID платежа в ЮKassa
├── status (pending/confirmed/rejected)
├── created_at

referral_bonuses
├── id (PK)
├── referrer_id (FK -> users.id)
├── referred_id (FK -> users.id)
├── bonus_days
├── granted_at
```

## Сценарий: /start

1. Если новый пользователь — создать запись в `users`
2. Показать меню: Тарифы / Попробовать бесплатно (триал) / Мои подписки / Реферальная ссылка

## Сценарий: активация триала

1. Проверить `users.trial_used` по `tg_id`
2. Запросить номер телефона (`request_contact`)
3. Проверить `phone_number` на использование триала другим `tg_id`
4. Если всё чисто — создать `subscription` (7 дней, 1 устройство → `limitIp=1`, status=trial)
5. Через API Panel создать клиента (`POST /panel/api/clients/add`), привязать к боевым инбаундам
   (S_RU reality + резервный S2, когда появится `s2-direct-entry`)
6. Выдать клиенту ссылку подписки — её формирует и отдаёт сама Panel
   (`https://netru.ru.net:2096/<токен>/<путь>`, пример структуры подтверждён практикой
   оператора 03.10.2026); либо получить ссылки напрямую через `GET /panel/api/clients/subLinks/{subId}`
7. `users.trial_used = true`

## Сценарий: покупка тарифа

**Основной путь (после подключения ЮKassa):**
1. Клиент выбирает тариф → бот создаёт платёж через API ЮKassa, отправляет ссылку на оплату
2. ЮKassa присылает webhook о статусе платежа на `/yookassa-webhook/<секрет>/`
3. При успешной оплате — `payments.status=confirmed`, автоматически создаётся/продлевается
   подписка (шаги 5–6 из сценария триала; продление — через `POST /panel/api/clients/bulkAdjust`
   с `addDays`, см. раздел API ниже, не через `update`)
4. Если есть `referrer_id` и это первая оплата пользователя → начислить бонус рефереру
   (таблица `tariffs.md`)
5. Чек для самозанятых — через API ЮKassa или вручную (уточнить при реализации)

**Fallback (ручное подтверждение, пока ЮKassa не готова или недоступна):**
1. Клиент выбирает тариф, видит реквизиты
2. Клиент нажимает «Я оплатил» → `payments` (status=pending)
3. Админу — уведомление в Telegram с кнопками Подтвердить/Отклонить
4. Админ подтверждает → `payments.status=confirmed`, дальше как в шаге 3 основного пути

## Сценарий: реферальная ссылка

Формат: `https://t.me/<bot_username>?start=ref_<user_id>`
При `/start` с параметром `ref_XXX` → записать `referrer_id` при создании нового user
(если пользователь уже существует — не перезаписывать `referrer_id`)

## Интеграция с API Panel (3x-ui v3.9.0)

### Статус: исследовано 04.10.2026 внешним агентом (открытые источники GitHub) + **верифицировано в этой же сессии реальными вызовами на боевой Panel** (тестовый токен, тестовый клиент). Часть предположений внешнего агента подтвердилась, часть — опровергнута фактами ниже; используйте этот раздел как актуальный источник, не исходный ответ агента.

### Доступ и аутентификация (подтверждено практикой)

- Аутентификация — Bearer-токен из таблицы `api_tokens` (`Authorization: Bearer <token>`),
  подтверждено рабочим на всех протестированных вызовах.
- ⚠️ **Создание токена через CLI не работает в нашей сборке.** Команда из исходного
  исследования (`x-ui setting -getApiToken -tokenName <name>`) **не существует** — control
  menu `x-ui -h` / `x-ui setting -h` не содержит подкоманды `setting` вообще (обе команды
  проваливаются в одинаковый generic help). **Единственный проверенный способ создать токен —
  через UI**: `Settings → Security → API Token`. Выбора `scope` (admin/monitor/node-sync,
  как предполагал внешний агент) в UI нашей версии **нет** — токен создаётся с одним набором
  прав (в БД записан `scope='admin'`).
- `GET <webBasePath>panel/api/openapi.json` **без авторизации → 404** (подтверждено);
  **с Bearer-токеном → 200**, отдаёт полную актуальную спецификацию (~254 KB). Это
  авторитетный источник правды о реальных путях/схемах — предпочтительнее любого внешнего
  описания API, расхождения с ним ниже отмечены явно.
- Созданный тестовый токен сохранён на сервере Panel: `/root/.secrets/panel-api-token.txt`
  (chmod 600, root only) — **не публиковать, не коммитить в репозиторий**. Снятая спецификация:
  `/root/panel-openapi.json` на Panel (не секрет, можно коммитить при необходимости, но лучше
  переснимать свежей при начале реализации — панель могла обновиться).

### Два слоя API (подтверждена архитектура, legacy не тестировался подробно)

- **Legacy (inbound-centric):** `/panel/api/inbounds/*` — не тестировался в этой сессии
  (приоритет отдан modern API, как и планировалось архитектурно решением 3). Существование
  подтверждено только по косвенным данным (упоминания в openapi.json не проверялись построчно).
- **Modern (client-centric):** `/panel/api/clients/*` — полностью верифицирован ниже.

### Полный список путей `/panel/api/clients/*` (получено из реального `openapi.json`, 04.10.2026)

Список значительно шире, чем предполагалось в первой версии документации (со слов внешнего
агента) — обнаружены пути, ранее не упоминавшиеся вовсе:

```
POST   /panel/api/clients/activeInbounds
POST   /panel/api/clients/add
POST   /panel/api/clients/bulkAdjust
POST   /panel/api/clients/bulkAttach
POST   /panel/api/clients/bulkCreate
POST   /panel/api/clients/bulkDel
POST   /panel/api/clients/bulkDetach
POST   /panel/api/clients/bulkDisable
POST   /panel/api/clients/bulkEnable
POST   /panel/api/clients/bulkResetTraffic
POST   /panel/api/clients/clearIps/{email}
POST   /panel/api/clients/clientIpsByGuid
POST   /panel/api/clients/del/{email}            -- ⚠️ POST, не DELETE (расходится с прежним описанием)
POST   /panel/api/clients/delDepleted
POST   /panel/api/clients/delOrphans
GET    /panel/api/clients/export
GET    /panel/api/clients/get/tgId/{tgId}
GET    /panel/api/clients/get/{email}            -- ⚠️ путь "get/{email}", не "/{email}"
GET    /panel/api/clients/groups
POST   /panel/api/clients/groups/bulkAdd
POST   /panel/api/clients/groups/bulkRemove
POST   /panel/api/clients/groups/create
POST   /panel/api/clients/groups/delete
POST   /panel/api/clients/groups/rename
POST   /panel/api/clients/groups/resetTraffic
GET    /panel/api/clients/groups/{name}/emails
POST   /panel/api/clients/happLink/{id}
POST/DELETE /panel/api/clients/hwids/{email}
DELETE /panel/api/clients/hwids/{email}/{id}
POST   /panel/api/clients/import
POST   /panel/api/clients/ips/{email}
POST   /panel/api/clients/lastOnline
GET    /panel/api/clients/links/{email}
GET    /panel/api/clients/list                   -- плоский список, БЕЗ summary (см. ниже)
GET    /panel/api/clients/list/paged             -- summary + пагинация + фильтры (см. ниже)
POST   /panel/api/clients/onlines
POST   /panel/api/clients/onlinesByGuid
POST   /panel/api/clients/renewalPreview
POST   /panel/api/clients/resetAllTraffics
POST   /panel/api/clients/resetTraffic/{email}
GET    /panel/api/clients/subLinks/{subId}
GET    /panel/api/clients/traffic/{email}
POST   /panel/api/clients/update/{email}
POST   /panel/api/clients/updateTraffic/{email}
POST   /panel/api/clients/{email}/attach
POST   /panel/api/clients/{email}/detach
POST   /panel/api/clients/{email}/externalLinks
```

### Проверенные вызовы (реальные тесты на боевой Panel, тестовый клиент id=7, email
`test-bot-verify@internal`, привязан к инбаунду `testS2` id=3)

**1. `POST /panel/api/clients/add` — ✅ подтверждено рабочим**
```json
{
  "client": {
    "email": "test-bot-verify@internal",
    "tgId": 0,
    "limitIp": 1,
    "totalGB": 1073741824,
    "expiryTime": 1791297771649,
    "enable": true,
    "comment": "..."
  },
  "inboundIds": [3]
}
```
- Ответ: `{"success":true,"msg":"Inbound client(s) have been added.","obj":null}` — `obj` пуст,
  данные созданного клиента нужно получать отдельным `GET`.
- `subId` сгенерирован автоматически сервером, несмотря на то что явно не передавался —
  **issue #3237 (subId не генерируется) НЕ воспроизведён** на modern `/clients/add` в нашей
  версии (баг из исследования агента относился к legacy `addClient`, не проверялся там).
- `tgId: 0` (JSON-число, не строка) принят и сохранён корректно — issue #5934 учтён и не
  выстрелил, поведение ожидаемое.
- `uuid`, `password` и т.п. сгенерированы сервером автоматически (не передавались).

**2. `GET /panel/api/clients/get/{email}` — ✅ подтверждено, структура ОТЛИЧАЕТСЯ от `/list`**
- Путь: `get/{email}`, а не `/{email}`, как предполагалось изначально.
- Ответ **вложенный**: `obj.client.*` (все поля клиента — `email`, `subId`, `uuid`, `limitIp`,
  `tgId`, `enable`, `comment`, `expiryTime`, `totalGB`, `group`, `reset*`, `trafficReset*`,
  `createdAt`, `updatedAt`, `reverse` и протокол-специфичные поля), плюс на уровне `obj` —
  `externalLinks` (список), `inboundIds` (список id инбаундов клиента), `usedTraffic`.
- ⚠️ Не путать со структурой `/list` (см. ниже) — там `obj` плоский список клиентов без
  вложенности `.client`.

**3. `GET /panel/api/clients/list` — ✅ подтверждено, `obj` — ПЛОСКИЙ список, БЕЗ summary**
- `obj` — массив полных объектов клиентов (включая `uuid`, `password`, `auth` и прочие
  тяжёлые/чувствительные поля) напрямую, без обёртки `.client`.
- **Summary (`active`/`expiring`/`deactive`/`depleted`/`online` счётчики) здесь ОТСУТСТВУЕТ** —
  расхождение с первой версией документации (там summary ошибочно приписывался этому пути).

**4. `GET /panel/api/clients/list/paged` — ⚠️ схема изучена из openapi.json, САМ ВЫЗОВ НЕ
ТЕСТИРОВАЛСЯ в этой сессии.** Именно этот эндпоинт — правильный источник для cron-сверки
просроченных подписок бота:
- Параметры: `page` (default 1), `pageSize` (default 25, max 200), `search` (substring по
  email/subId/comment/uuid/password/auth/tgId), `filter` (CSV: `online`/`active`/`deactive`/
  `depleted`/`expiring`, значения через ИЛИ), `protocol` (CSV), `inbound` (CSV id), `sort`
  (`enable`/`email`/`inboundIds`/`traffic`/`remaining`/`expiryTime`/`createdAt`/`updatedAt`/
  `lastOnline`), `order`.
- Строки в ответе **урезанные** (без `uuid`/`password`/`auth`/`flow`/`security`/`reverse`/
  `tgId`) — для полных данных конкретного клиента после пагинации нужен отдельный
  `get/{email}`.
- Содержит `summary`, вычисленный по всей БД (не только по текущей странице) — точные счётчики
  по статусам, с ограничением в 200 email в сопутствующих массивах (не растёт с размером базы).
- **TODO перед использованием в коде бота:** протестировать реальным вызовом (фильтр
  `filter=expiring`, сверить с ручным расчётом по `expiryTime`).

**5. `POST /panel/api/clients/update/{email}` — ⚠️ ПОДТВЕРЖДЕНО: FULL-REPLACE, НЕ PATCH (опасно для частичных изменений)**
- Тело — **плоское**, без обёртки `client` (в отличие от `add`):
  ```json
  {"email": "test-bot-verify@internal", "comment": "..."}
  ```
  При отправке в обёртке `{"client": {...}}` (по аналогии с `add`) — ошибка:
  `{"success":false,"msg":"Something went wrong (client email is required\n)","obj":null}`,
  **HTTP 200** (не 400!) — подтверждает правило «проверять `success` в теле ответа, не
  полагаться на HTTP-код».
- Дублирования строки в БД при одиночном вызове не происходит (`count(*) where email=... = 1`
  до и после) — **issue #5870 (дублирование) не воспроизведён** в этом сценарии.
- 🔴 **ДОКАЗАНО КОНТРОЛИРУЕМЫМ ТЕСТОМ 04.10.2026 — `update` ПОЛНОСТЬЮ ЗАМЕНЯЕТ СТРОКУ КЛИЕНТА:**
  1. Установлен baseline через `update` с полным телом: `limitIp=5`, `totalGB=2147483648`,
     `enable=true`, `expiryTime=<+1 день>`. Подтверждено `GET get/{email}` — все значения
     применились.
  2. Выполнен `update` с **минимальным** телом `{"email":...,"comment":"..."}` (без остальных
     полей).
  3. `GET get/{email}` после — **все непереданные поля обнулились**: `limitIp:0`, `totalGB:0`,
     `enable:False` (!), `expiryTime:0`. Сохранился только переданный `comment` и привязки
     `inboundIds` (они живут в отдельной таблице `client_inbounds`, этим эндпоинтом не
     затрагиваются).
  - Это соответствует прямому предупреждению в самом `openapi.json`: *«Body is the JSON client
    payload — supply the full set of fields you want to keep (the server replaces the row, it
    does not patch)»* — теперь не гипотеза, а **подтверждённый на практике факт**.
- 🔴 **ПРАВИЛО ДЛЯ КОДА БОТА (обязательно к соблюдению):**
  - **Никогда не вызывать `update` с частичным телом** — это обнулит лимиты и **отключит
    клиента** (`enable` падает в `false`), даже если `enable` не передавался вовсе.
  - Если `update` всё же нужен — сначала `GET get/{email}`, взять **все** поля текущего
    клиента, применить нужное изменение поверх полного набора, отправить обратно целиком.
  - Для продления срока/трафика — **всегда использовать `bulkAdjust`** (addDays/addBytes),
    не `update` — подтверждено безопасным (дельта, не замена).
  - Для изменения `enable` — по возможности использовать `bulkEnable`/`bulkDisable` (есть в
    списке путей, не тестировались в этой сессии) вместо `update`.
  - Тестовый клиент после этого эксперимента остался в состоянии `enable:False`,
    `limitIp:0`, `totalGB:0`, `expiryTime:0` — не продакшн-данные, не критично, но учитывать
    при следующих тестах на этом же тестовом клиенте.

**5a. Доп. находки при round-trip `get` → `update` (08.10.2026, при разработке страницы подписки)**
- 🔴 Поле `id` в ответе `get/{email}` — число (`"id": 7`); `update/{email}` ожидает либо
  отсутствие поля, либо несовместимый тип — прямая передача объекта `get` в `update` без
  изменений падает: `{"success":false,"msg":"Something went wrong (json: cannot unmarshal
  number into Go struct field .id of type string)"}`.
  **Решение:** перед отправкой в `update` всегда удалять ключ `id` из тела (идентификация и
  так идёт по `email` в пути).
- 🔴 Поле `allowedIPs` (WireGuard-specific, не используется для VLESS/Reality) в ответе `get`
  сериализуется как пустая строка `""`, а `update` ожидает `[]string` — при пустой строке
  падает: `{"success":false,"msg":"Something went wrong (json: cannot unmarshal string into
  Go struct field .allowedIPs of type []string)"}`.
  **Решение:** перед отправкой в `update` конвертировать `allowedIPs` из `""` в `[]`, если
  встречается пустая строка.
- **Правило для кода бота:** перед любым `get → update` round-trip — нормализация: удалить
  `id`, привести пустые строки известных массивных полей (на 08.10.2026 — только
  `allowedIPs`) к `[]`. При появлении новых ошибок `cannot unmarshal string into ... []...`
  на `update` — добавлять поле в список.
- ✅ После нормализации `update` с полным набором полей (включая реальное изменение
  `expiryTime`) отработал корректно, подтверждено `GET get/{email}` до/после.

**5b. Критично для API-клиента бота: обязательный префикс `webBasePath` в URL**
- У Panel задан секретный `webBasePath` (`Settings → Panel → Panel URL Root Path`; значение —
  в менеджере паролей, НЕ в этом репозитории).
- Полный путь вызова: `https://netru.ru.net:25305/<webBasePath>/panel/api/clients/...`.
- Подтверждено 08.10.2026: без префикса — `HTTP 404` на любой путь `/panel/api/...`, не
  `401`/`403` — удобно для диагностики (отличает «неверный путь» от «неверный токен»/«нет прав»).
- **Для кода бота:** `webBasePath` — обязательная часть конфигурации (переменная окружения/
  секрет), не хардкодить, читать из защищённого конфига.

**6. `POST /panel/api/clients/bulkAdjust` — ✅ подтверждено рабочим, рекомендованный способ
продления подписок**
```json
{"emails": ["test-bot-verify@internal"], "addDays": 1}
```
- Ответ: `{"success":true,"msg":"","obj":{"adjusted":1}}`.
- По описанию в openapi.json — атомарная дельта (addDays/addBytes могут быть отрицательными),
  клиенты с `expiryTime=0`/`totalGB=0` (безлимит) пропускаются для соответствующего поля,
  автоматически снимает авто-отключение клиента при выходе из состояния "исчерпан". Также
  поддерживает `flow`, `limitHwid`, `adTag` одним вызовом на множество email сразу.
- **Рекомендация для бота**: использовать `bulkAdjust` для продления/изменения трафика вместо
  `update` — меньше риска (подтверждённое поведение, безопасная семантика "adjust", не
  "replace").

**7. `GET /panel/api/clients/subLinks/{subId}` — ✅ протестирован 08.10.2026, ⚠️ НЕ отдаёт ссылку
на страницу подписки**
- Ответ: `obj` — список сырых `vless://...` конфигов, по одному на каждый inbound, к которому
  привязан клиент (аналогично `{{ range .links }}` на кастомной странице подписки, см.
  `sub-page-custom.md`). Полезен для показа ссылки на конкретный сервер, НЕ для главной ссылки
  подписки.
- **Правильный способ получить ссылку подписки** (ту самую `https://netru.ru.net:2096/...`,
  которую отдаёт кастомная/нативная страница): собрать вручную по шаблону Panel —
  `<схема>://<домен>:<subPort><subPath><subId>`. Компоненты — настройки Panel
  (`Settings → Subscription`): `subPort` (у нас `2096`), `subPath` (секретный путь, не
  хранится в документации), `subDomain` (если не задан — используется основной домен панели).
  Прочитать текущие значения: `sqlite3 /etc/x-ui/x-ui.db "SELECT key,value FROM settings WHERE
  key IN ('subDomain','subPort','subPath');"` на Panel.
- В коде бота закреплено как `SUB_BASE_URL` (полный префикс до `subId`, порт+путь) —
  переменная окружения, хранится только в `secrets/panel-bot.env`, не в `.env.example`.

### Не протестировано (обновлено 08.10.2026)

- ✅ Риск full-replace `update` закрыт на уровне кода: `update_client_safe()` всегда делает
  `get → нормализация (id, allowedIPs) → merge → полная отправка`, частичный вызов напрямую
  нигде в коде не используется.
- `GET /panel/api/clients/list/paged` — реальный вызов с фильтрами/summary всё ещё НЕ делался
  (нужен для cron-сверки просроченных подписок — задача на будущее, после MVP-меню).
- `bulkCreate`, `bulkAttach`/`bulkDetach`, `bulkDel`, `bulkDisable`/`bulkEnable` (методы в
  `panel_api.py` есть, но сам HTTP-вызов на боевой Panel не делался), `bulkResetTraffic`,
  `groups/*`, `hwids/*`, `happLink`, `export`/`import`, `renewalPreview`, `onlines`/
  `onlinesByGuid`.
- Legacy `/panel/api/inbounds/*` — не тестировался вообще.
- Webhook/события — по-прежнему предположительно отсутствуют.

### Артефакты (обновлено 08.10.2026)

✅ Тестовые артефакты B8 удалены перед началом продакшн-разработки: токен `test-bot-verify`
отключён/удалён в UI, клиент `test-bot-verify@internal` удалён (`clients/del`),
`/root/panel-openapi.json` удалён с Panel.

**Текущие продакшн-артефакты на Panel:**
- `/root/.secrets/panel-bot-token.txt` (chmod 600) — боевой Bearer-токен `bot-prod`,
  используется ботом (`PANEL_API_TOKEN_FILE` в `.env`).
- `/opt/netru-bot/` — код бота (`src/`, задеплоен `rsync` из монорепо на S1, НЕ через
  `git clone` — репозиторий зашифрован `git-crypt`, ключ на Panel не хранится), venv (`venv/`),
  БД SQLite (`bot.db`), `.env` (chmod 600, копия `secrets/panel-bot.env`).
- `/etc/systemd/system/netru-bot.service` — systemd-юнит, `enabled`, автозапуск при перезагрузке.
  ⚠️ **Управлять только через `systemctl start/stop/restart netru-bot`** — ручной запуск
  `python3 -m app.main` напрямую через ssh 08.10.2026 приводил к дублированию процессов и
  `TelegramConflictError` (процесс не всегда завершается сразу по `Ctrl+C`, может зависать в
  состоянии `D` из-за socks5-прокси).

## Открытые вопросы (обновлено 08.10.2026)

1. ✅ API-схема исследована и верифицирована; находка про `subLinks` закрыта (см. выше).
   `update` full-replace учтён в коде.
2. Дождаться завершения регистрации ЮKassa (оператор завершает) — блокирует раздел «Тарифы»/оплату.
3. ✅ Long polling через прокси решён — бот использует `tg-proxy` на S2 (socks5, 38417), тот
   же инбаунд, что встроенный бот панели; отдельный outbound не потребовался.
4. Зафиксировать конкретные тарифы/множители (`tariffs.md`, TODO) — нужно для раздела «Тарифы».
5. Задача `s2-direct-entry` — отдельная, не блокирует текущий функционал (триал работает с
   одним входом), но блокирует полноценные многовходовые продакшн-подписки.
6. Добавить поле трафика (`total_gb`) в `Plan`/`Subscription`? Решение 08.10.2026: пока у всех
   тарифов безлимитный трафик (`totalGB=0`), ограничение только по сроку и `limitIp`.
   Пересмотреть при появлении тарифов с лимитом трафика.
7. Alembic-миграции не настроены — таблицы создаются через `Base.metadata.create_all()`
   (`init_db()`, явный TODO в коде). Настроить до накопления продакшн-данных.
8. Не реализовано: разделы «Тарифы»/«Мои подписки» (заглушки), оплата (ЮKassa/fallback),
   реферальные бонусы, admin-уведомления (`ADMIN_IDS` задан в конфиге, но не используется).

## Связанные документы

- [overview.md](overview.md) — архитектура коммерческого проекта
- [migration-3xui.md](migration-3xui.md) — журналы миграции и диагностики
- [tariffs.md](tariffs.md) — тарифная сетка, триал, рефералка (цены частично не зафиксированы)
