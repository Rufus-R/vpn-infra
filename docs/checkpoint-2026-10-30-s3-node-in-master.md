# Чекпоинт 30.10.2026 — нода S3 в мастере: регистрация, усыновление, барьер привязки

Продолжение `checkpoint-2026-10-30-s3-node-master-panel.md`.

## Что сделано

1. **Регистрация ноды в мастере** — успешно. `nodes` id=3, `195.242.118.2:25307`,
   `tls_verify_mode=pin`, `inbound_sync_mode=selected`, `inbound_tags=["in-10001-tcp"]`,
   `status=online`, latency 44 мс.
   Имя после регистрации — `S3-RU-exit`, **переименовано в `S3-EU-exit`** (S3 физически в
   Европе, согласовано с `S2-EU-exit`). Через `POST /panel/api/nodes/update/3` с тем же
   payload без `apiToken` (токен переиспользован из БД — `RuntimeNodeFromRequest` подставляет
   существующий). `guid` не изменился (`2bf9d321-…`).

2. **Усыновление инбаунда** — чисто. Мастер создал `inbounds` id=8 `in-10001-tcp`
   (:10001, vless, node_id=3) с 10 клиентами из снапшота ноды; `stream_settings` сохранён
   как есть (`/etc-x-ui/certs/server.crt`, tls, alpn h2/http1.1) — серт ноды не менялся,
   пин `76145d04…6eef0` подтверждён снаружи после регистрации.

3. **Нода не перезаписана**: 2 инбаунда (3: in-10001-tcp 10 клиентов, 4: in-38417-socks
   tg-proxy 0 клиентов), 10 записей `clients`, `client_inbounds`=10, Xray pid 75933 живой,
   `user_id=1` сохранён.

4. **Идентичности клиентов не тронуты**: `clients.sub_id`/`uuid` в мастере совпадают
   с прежними (9 коммерческих + relay-s3).

## Барьер: почему клиентов нельзя привязать к двум нодам

`POST /panel/api/clients/bulkAttach` вернул `skipped` для всех 9 — сверка идёт с
`inbounds.settings.clients` инбаунда 8, где усыновлённые клиенты уже присутствуют.
Точечный `POST /panel/api/clients/:email/attach` вернул `success`, но через ~2 минуты
изменения **откатились** фоновым job'ом.

Причина — не баг, а правило `clientEmailsOwnedElsewhere` (`inbound_node.go:498`),
вызываемое из `setRemoteTraffic` (`inbound_node.go:1372`): если email уже привязан к
инбаунду **другой** ноды, снимок с этой ноды не усыновляется. Лог подтвердил:

```
WARNING - setRemoteTraffic: node 3 reported client "medmtcoqzd",
  which is attached only to inbounds of another node — not adopting
  (rename one side to remove the duplicate email)
```

Все 9 клиентов висят на `inbound 1` (`n1-in-443-tcp`, node 1 = S_RU) → для мастера они
«собственность» S_RU, поэтому привязка к S3 откатывается. Итог: `client_inbounds`
inbound 8 = только `relay-s3`.

## Что это значит для прода

Модель мастера: **email ↔ одна нода**. Схема «вход S_RU + выход S3 на одном клиенте»
через две ноды не поддерживается — нужен либо один email на ноду, либо отдельный
entry-инбаунд на S3.

Побочно замечено: node 1 (S_RU, `31.77.169.67:24167`) систематически **не отвечает**
мастеру по API (`context deadline exceeded` на `inbounds/list`, `onlines`, `lastOnline`),
начиная с 20:49. Трафик клиентов при этом идёт — `last_online` свежие (21:55 у
`vfuzirpd3h`, 21:53 у `tg1725556555`). То есть Reality-вход работает, но телеметрия и
пуши конфига на S_RU недоступны. Это согласуется с исходным инцидентом DPI.

## Решения, требующие оператора (не принимались)

- **A. Схема «вход + выход»**: нужен entry-инбаунд на самой S3 (или разрешение дубля
  email на двух нодах). Объём: правка инбаундов в мастере + перевыпуск ссылок.
- **B. `inbound_sync_mode=selected`**: ставился, чтобы не тянуть `in-38417-socks`
  (tg-proxy, port/protocol mismatch нода=socks / мастер=mixed, п. 8.5). Если хотите,
  чтобы мастер управлял всеми инбаундами ноды — переключить на `all` и решать 8.5.
- **C.** Attach к inbound 8 напрямую (без перестройки схемы) невозможен — откатывается
  правилом выше.

## Бэкапы

- S3: `/root/x-ui.db.bak-20261030-pre-token-rotate`, `-pre-userid-fix`
- Мастер: `/root/x-ui.db.bak-20261030-pre-s3-node-add` (21:26)

## Гигиена

- `/tmp/node-token.txt` на ноде → `/root/.node-token` (600), временный удалён (shred).
- `/tmp/node-token.txt` на мастере удалён.
- Проверено: `show-node-token.sh` не используется сервисами/cron/bashrc.
