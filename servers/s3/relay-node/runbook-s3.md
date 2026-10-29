# S3 — аварийный relay/exit (инцидент S2 29.10.2026)

Контекст: у S2 (`77.105.161.151`) заблокирован весь входящий трафик на уровне
сети провайдера (tcpdump на S2 пуст при SYN с whitelisted-источников; исходящий
работает). Тикет провайдеру отправлен. S3 — замена exit-роли S2 для
коммерческого канала. Домашний контур (OpenVPN S1↔S2, Pi-hole) пока остаётся
на S2 — туннель жив как established-сессия.

## Архитектура после переключения

```
клиент → S_RU:443 (VLESS+Reality, entry, geo-split)
              │ outbound to-s2-relay → МЕНЯЕТСЯ адрес на S3:10001
              └→ S3:10001 (VLESS+TLS, этот репо: servers/s3/) → интернет
```

Клиенты ничего не меняют (вход по-прежнему S_RU:443). Geo-split на S_RU
сохраняется (`geosite:category-ru`/`geoip:ru` → direct).

## Роли S3

1. **Сейчас (аварийно):** relay/exit для коммерческого трафика вместо S2.
2. **Опционально потом:** OpenVPN-сервер для нейтрального домашнего туннеля
   (задача `s2-direct-entry` / резервный канал) — отдельно, не в этом скрипте.

## Требования к VPS

- 1 vCPU / 1 ГБ RAM / 10 ГБ диска — с запасом.
- Локация: НЕ сеть провайдера S2; NL/DE/FI подходят.
- Виртуализация: **KVM предпочтительно**. OpenVZ/LXC допустим ТОЛЬКО если
  провайдер разрешает netfilter (iptables) и TUN/TAP внутри контейнера —
  скрипт проверяет это на старте (preflight) и прервётся с FATAL, если ufw
  невозможен.
- ОС: Debian 12 или Ubuntu 24.04, чистая, root по SSH.
- Домен не нужен: TLS по IP-сертификату (self-signed, как на S2:10001).

## Шаги

### 1. Купить VPS, зафиксировать IP

IP записать в этот файл (раздел «Факты») и в `docs/system-state.md` после ввода.

### 2. Передать скрипты на S3 (с S1, где есть ключи)

```bash
scp /root/vpn-infra/servers/s3/bootstrap-s3.sh /root/vpn-infra/servers/s3/relay-node/xray-config-template.json root@IP_S3:/root/
```

### 3. Запустить bootstrap НА S3

```bash
ssh root@IP_S3
bash /root/bootstrap-s3.sh 31.77.169.67 31.77.78.144
```

Скрипт (read-only вне S3): ufw (зеркало S2, см. `docs/shared/networking/iptables-s2.md`),
самоподписанный IP-серт 10 лет в `/etc/xray/certs/`, Xray `v26.10.21` в `/usr/local/xray`,
конфиг relay-инбаунда `in-10001-tcp` (порт 10001, uuid генерируется),
systemd-юнит `xray-relay`. В конце печатает блок «ДАННЫЕ ДЛЯ ПЕРЕКЛЮЧЕНИЯ S_RU» —
сохранить (uuid + IP:порт).

### 4. Переключить S_RU (вручную, через мастер-панель Panel)

На Panel (мастер 3x-ui, `netru.ru.net:25305`) → нода S_RU → outbound `to-s2-relay`:

- `address`: новый IP S3
- `port`: 10001 (или из вывода скрипта)
- `settings.vnext[0].address` — то же; `users[0].id` — uuid из вывода скрипта
- `streamSettings.tlsSettings.serverName`: оставить пустым (как на S2)
- `allowInsecure: true` — обязательно (IP-серт self-signed; на S2 так же)
- Перезапустить ядро S_RU из панели.

Эквивалент через curl/API — не автоматизирован сознательно: панель хранит
node-конфиг в своей БД, правка руками через UI безопаснее в аварийном режиме.

### 5. Проверки

```bash
# с S1 или Panel:
ssh root@IP_S3 "ss -tlnp | grep 10001"                      # слушается
ssh root@IP_S3 "systemctl is-active xray-relay"             # active

# сквозной (после переключения S_RU):
ssh root@31.77.169.67 "timeout 3 bash -c 'cat < /dev/null > /dev/tcp/IP_S3/10001' && echo RELAY_OK"
# с телефона/клиента:
#   https://2ip.io/ru/          → IP_S3 (exit теперь S3)
#   https://yandex.ru/internet  → 31.77.169.67 (geo-split жив)
#   YouTube, банки              → открываются
```

### 6. ufw на S3 — ПРОВЕРИТЬ после покупки (скрипт ставит по умолчанию)

Скрипт разрешает: 22/tcp всем, 80/tcp всем (ACME), 10001 с S_RU/S1,
25307 с S1/Panel/оператор/VPN. Если relay-порт меняется — поправить правило
в скрипте и в `docs/shared/reference/ports.md`.

## Факты (заполнить после покупки)

- IP S3: `195.242.118.2` (IPv6: `2a0d:1643:2d83::1`), KVM-VPS-1-1, hostname `s3s3.s2`
- Провайдер/локация: `TODO` (не landvps; локация — проверить по панели, ожидание NL)
- Дата ввода: `TODO` (покупка 29.10.2026)
- Root-пароль: известен оператору (в git НЕ вносить); после бутстрапа перейти на ключи
- Relay uuid: в `/run/relay_uuid` на S3 и в выводе bootstrap (шаг 3).

## Откат

Вернуть S_RU outbound `to-s2-relay` на `77.105.161.151:10001` (uuid прежний,
см. `secrets/s2-relay-config.json`) — если блокировку S2 снимут и решим вернуться.
S3 при этом остаётся как резерв (задача «резервный канал»).

## После стабилизации — документация

- `docs/system-state.md`: строка S3 в таблице серверов, обновить «Коммерческий сегмент».
- `docs/shared/reference/ports.md`: раздел S3 (10001, 25307).
- `docs/diagnostic-commands.md`: раздел S3 + обновить ожидания RELAY-теста.
- `docs/commercial/operations-log.md`: запись инцидента 29.10.2026.
- Чекпоинт: `docs/checkpoint-2026-10-29-s2-outage-s3.md`.
- Ключ агента `ai-agent@openhands-500` убрать из authorized_keys S2 после диагностики.
