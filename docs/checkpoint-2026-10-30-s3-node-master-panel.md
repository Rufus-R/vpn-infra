# Чекпоинт 30.10.2026 — нода мастер-панели на S3 (3x-ui v3.11.0)

Сессия: прод-аутэйдж коммерческого VPN (клиенты Людмила, Александр и др. офлайн).
Мандат: диагностика/read-only по живым серверам, изменения — только в рамках явно
поставленной задачи «поднять ноду мастер-панели на S3».

## Задача и решение

DPI режет Reality-хендшейк на входе S_RU:443 → подтверждённый pivot: клиенты ходят
**напрямую на S3**, exit строго S3. Подписки продолжает раздавать мастер
(`netru.ru.net`, Panel `31.77.78.144`) — автообновление само выдаст новый адрес.
Мастер **опрашивает API нод** (push-модель), поэтому на S3 нужна не «полная панель»,
а **нода** того же форка.

## Что установлено на S3 (195.242.118.2)

| Параметр | Значение |
|---|---|
| Панель | MHSanaei 3x-ui **v3.11.0** (последний релиз 25.10.2026 = версия мастера) |
| Xray | **26.10.21** (совпадает с S_RU/мастером) |
| Порт панели | **25307** (было зарезервировано в ports.md) |
| URL | `https://195.242.118.2:25307/4kNbpfhH09XSfBMt0D/` |
| Серт | self-signed `/etc/x-ui/certs/server.{crt,key}`, CN/SAN=`195.242.118.2`, 10 лет (29.10.2026 → 26.10.2036) |
| Пин серта | `76145d045ba251990c8f17dd2b43b087ce124f2db378464bfc2e648c5dd6eef0` (переиспользован серт релея — клиентские конфиги и S_RU не меняются) |
| Подписка | единственный источник — мастер. На ноде sub-сервер фактически слушает :2096 (settings.subEnable не задан), но на 2096 нет правила ufw → снаружи недоступен. Оставлено как есть (решение не принималось) |
| Доп. | fail2ban, IP Limit, ufw-allowlist уже был в bootstrap |

`/etc/default/x-ui` пуст: адрес/токен связи мастер↔нода живут в БД ноды и в
`install-result.env`.

## Инбаунды, перенесённые с релея в ноду

`xray-relay.service` — **остановлен и disabled**; порты обслуживает xray под управлением x-ui
(один процесс вместо двух).

| Инбаунд | Порт | Протокол | Клиенты |
|---|---|---|---|
| `in-10001-tcp` | 10001 | VLESS+TLS (серт `/etc/x-ui/certs/`) | **10**: 9 коммерческих + `relay-s3` |
| `in-38417-socks` | 38417 | SOCKS5 с паролем (`user`/`pass`), `udp:false`, `ip:127.0.0.1` | — (tg-proxy для бота Panel) |

UUID клиентов идентичны S_RU (9 шт.), плюс релейный
`7efdd1f8-16a8-4769-8507-a63373642366` (`relay-s3`) — **без него рвётся туннельный путь S_RU→S3**.

## ⚠️ Схема хранения клиентов в этом форке (3.11)

Клиент хранится **в трёх местах консистентно**, иначе генератор конфига молча даёт `clients: []`:

1. таблица `clients` — одна строка на клиента (`email, sub_id, uuid, password, auth, limit_ip, total_gb, expiry_time, enable, tg_id, comment, reset, traffic_reset, traffic_reset_day`);
2. таблица `client_inbounds` — `(client_id, inbound_id, flow_override, created_at)`;
3. JSON `inbounds.settings` → `"clients": [ {полный объект} ]` — эталон полей:
   `auth, comment, created_at, email, enable, expiryTime, id(UUID), limitIp, password,
   reset, resetDay, resetMax, resetWeekday, security, subId, tgId, totalGB,
   trafficReset(never), trafficResetDay, updated_at`.

Плюс учёт трафика — `client_traffics` (строка на `(inbound_id, email)`).

**Что НЕ работает (не повторять):** минимальный JSON `{email,id}` в `settings.clients`;
инжект прямо в `bin/config.json` (панель регенерирует из `xrayTemplateConfig`);
попытки только через `client_inbounds`/`client_traffics` без полного объекта.

**Грабли, на которые уже наступили:**
- `clients.tg_id` — **INTEGER**; строка `""` → `Scan error ... converting driver.Value type string ("") to a int64` → «Restart xray failed» в цикле, панель active, но xray не поднимается.
- Вставка с неверным порядком колонок сдвинула данные (`total` получил `remark`) → crash-loop. Вставлять явным списком колонок.
- `xrayTemplateConfig` без `outbounds` (`{}`) → `app/dispatcher: default outbound handler not exist`, трафик чёрной дырой. Минимум:
  `{"log":{"loglevel":"info"},"outbounds":[{"protocol":"freedom","tag":"direct"}]}`.
- `loglevel:"none"` не даёт диагностики; для проверки временно ставили `info` (на ноде оставлен `info`).

## E2E-проверки (итог)

| Путь | Результат |
|---|---|
| Public S1 → S3:10001 (UUID клиента) | ✅ http=200, exit **195.242.118.2**, ~2.6 s |
| Tunnel S_RU → 10.11.0.2:10001 (UUID `relay-s3`) | ✅ http=200, exit 195.242.118.2, 0.36 s |
| tg-proxy socks 38417 с авторизацией | ✅ exit S3 |
| Бот Panel | ✅ 0 `ProxyConnectionError`, `Connection established` |
| Пин серта извне | ✅ `76145d04…6eef0` |
| Персистентность | ✅ рестарт x-ui → 10 клиентов на месте |

## Регистрация ноды в мастере

Мастер требует валидный TLS. В форме Node (`pages.nodes`) есть
`tlsVerifyMode`: **verify | pin | skip | mtls** (дефолт `verify` → на self-signed серте
`x509: certificate signed by unknown authority`).

**Рекомендовано — `pin`**: нажать **Fetch** рядом с полем «Pinned certificate SHA-256»
(панель сама снимает SHA-256 с ноды) либо вставить вручную
`76145d045ba251990c8f17dd2b43b087ce124f2db378464bfc2e648c5dd6eef0`.
`skip` работает, но хуже (тултип панели: «token API could be intercepted. Prefer pinning»).
`mtls` (как у существующих `s-ru-entry`/`S2-EU-exit`, оба `tls_verify_mode=mtls`) требует
расшарить CA мастер-панели в mTLS-настройку ноды (кнопка «mTLS» в тулбаре Nodes).

Параметры формы:

| Поле | Значение |
|---|---|
| Name | `S3-RU-exit` |
| Scheme / Address / Port | `https` / `195.242.118.2` / `25307` |
| Base path | `/4kNbpfhH09XSfBMt0D/` |
| TLS Verify Mode | `pin` + Fetch/вставить SHA-256 |
| API Token | токен `Panel` с ноды, см. ниже |
| Inbound sync | `all` |
| Outbound tag | пусто |

**API-токен** (создан заранее, scope=admin, в БД ноды `api_tokens`, имя `Panel`):
на S3 есть хелпер `/root/show-node-token.sh` (python3, читает БД read-only):

```bash
# с S1:
ssh root@195.242.118.2 /root/show-node-token.sh
```

Значение в документацию/чат не выводить. Альтернатива — удалить токен `Panel` и создать
новый через UI ноды (панель покажет значение один раз).

## Что известно про БД мастера (read-only)

- `nodes`: `s-ru-entry` (31.77.169.67:24167, mtls, online), `S2-EU-exit` (77.105.161.151:25307, mtls, offline).
- `inbounds`: `n1-in-443-tcp` (443, VLESS, node 1, **9 клиентов**),
  **`n2-in-10001-tcp`** (10001, VLESS+TLS, node 2 = S2, 1 клиент `sru-to-s2`),
  `in-38417-tcp` (38417, **mixed**, node 2), `in-443-udp` (443, amneziawg, node 1).
- `clients` 10, `client_inbounds` 11; 9 клиентов привязаны к `inbound_id=1` (вход S_RU).
- В бинаре мастера: `adopted compatible inbound %q on node %s as %q`,
  `adopted-inbound check`, `inbounds_adopted_at` → мастер **усыновляет** совместимые
  инбаунды ноды по тегу/порту/протоколу, а не создаёт дубликаты.

**Вывод для следующего шага:** после регистрации ноды мастер увидит `in-10001-tcp` на
S3 и усыновит его; при `inbound_sync_mode=all` дальнейшая правда — за мастером (он пушит
конфиг на ноду). Значит клиентов к exit-ветке надо привязывать **в мастере**, а не в БД
ноды, иначе пуш перезапишет.

## Откат

- БД ноды до регистрации: `/root/x-ui.db.bak-20261030-pre-master-sync`
- Конфиг релея (до tg-proxy): `/root/xray-config.json.bak-20261030-pre-tgproxy`
- Прежний relay-конфиг полностью воспроизведён в ноде (10 клиентов + socks);
  при необходимости `systemctl enable --now xray-relay` и остановка x-ui.

## Firewall S3 (актуально)

`10001/tcp` открыт `Anywhere` (комментарий `relay public clients pivot 20261030`) — это
следствие pivot «клиенты напрямую на S3». Отдельные allow: S_RU, S1, `10.11.0.0/24`
(туннель). `25307` — только S1 / Panel / оператор / `10.8.0.0/24`. `38417` — только Panel.

## Открытые вопросы

1. Поведение усыновления при конфликте настроек (наш TLS-стрим с файловым сертом vs
   мастерский `certificates`): ожидаемо мастер перезапишет своё — серт на ноде должен
   остаться тот же файл, иначе сменится пин и клиенты отвалятся. **Проверить сразу после
   регистрации** `curl -k https://195.242.118.2:25307/.../panel/api/server/status` и пин.
2. `in-38417-tcp` в мастере — `mixed`, на ноде — `socks`. Протоколы не совпадут → усыновление
   может создать второй инбаунд или не сработать; tg-proxy важнее подписки, решать точечно.
3. После усыновления — проверить, что подписка выдаёт `195.242.118.2:10001` и клиенты
   (Людмила/Александр) поднялись.
