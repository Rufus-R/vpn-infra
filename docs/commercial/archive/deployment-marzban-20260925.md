# Порядок развёртывания

## Статус: Не начато

## Фазы

- [ ] Фаза 0: Документация (этот раздел) — ЗАВЕРШЕНО
- [ ] Фаза 1: Заказ S_RU (LandVPS, 2CPU/2GB/30GB/безлимит, 525р/мес)
      Проверить при получении: KVM подтверждён (та же линейка что S1)
- [ ] Фаза 2: Базовая настройка S_RU
      - Docker + docker-compose
      - Базовый firewall (ufw/iptables), закрыть всё кроме нужных портов
      - SSH-хардening
- [ ] Фаза 3: Marzban + Postgres + nginx
      - docker-compose.yml
      - self-signed сертификат для панели
      - Доступ к панели ограничить (см. Фаза 7 про VPN-доступ)
- [ ] Фаза 4: marzban-node на S_RU (RU inbound)
      - VLESS+Reality конфигурация
      - Изолированная docker-сеть
- [ ] Фаза 5: marzban-node на S2 (EU exit)
      - Изолированная docker-сеть, ОТДЕЛЬНО от домашних iptables-правил
      - Не трогать Pi-hole, не трогать домашний OpenVPN
- [ ] Фаза 6: Routing-шаблон (geo-split)
      - см. routing.md
- [ ] Фаза 7: Подключение S_RU к домашнему хабу S1 как VPN-клиент
      - Панель доступна только через internal IP (10.9.0.x)
      - Аналогично существующим клиентам Petr/Vova
- [ ] Фаза 8: Telegram-бот
      - см. bot.md
      - Разработка, тестирование локально
      - Деплой на S_RU (Docker)
- [ ] Фаза 9: Тестирование
      - Проверка direct routing (RU IP)
      - Проверка chain routing (EU IP через S_RU->S2)
      - Проверка триала (номер телефона, антифрод)
      - Проверка ручного подтверждения оплаты
      - Проверка реферальных бонусов
- [ ] Фаза 10: Мягкий запуск
      - Первые клиенты из личного круга

## Порты (черновик, финализировать при развёртывании)

| Сервер | Сервис | Порт | Протокол | Доступ |
|--------|--------|------|----------|--------|
| S_RU | Marzban panel | 8000 (internal) | TCP | только VPN (10.9.0.x) |
| S_RU | Postgres | 5432 | TCP | только docker-network |
| S_RU | marzban-node RU inbound | TBD | TCP | публично (клиенты) |
| S2 | marzban-node EU inbound | TBD | TCP | только от S_RU (relay) |

TODO: зафиксировать конкретные порты, не пересекающиеся с существующими
на S2 (Pi-hole 53, 18081 по плану миграции) и на S1.

## Прогресс (16.09.2026)

- [x] Фаза 1: S_RU заказан (LandVPS, 31.77.169.67, 295346.landvps.online)
- [x] Фаза 2: Docker + ufw + fail2ban установлены
- [x] Фаза 3: Marzban развёрнут (SQLite, без Postgres — пересмотр решения, см. overview.md)
      Панель доступна по /dashboard/, доступ только через SSH-туннель
      Sudo-админ создан
- [x] Фаза 4 (частично): VLESS+Reality inbound настроен и протестирован
      dest/serverName: ozon.ru:443
      Тестовый пользователь создан, подключение с клиента Hiddify — УСПЕШНО
      Публичный ключ: 3i_6GTcRKvpAKjgvLHI7jUUlEqnOpCT1iPElZe1U6zU
      Short ID: 9cde9e28846816db

## Осталось в Фазе 4

- [ ] marzban-node на S2 (EU exit для relay-цепочки)
- [ ] Routing-шаблон geo-split (RU direct / chain на EU) — см. routing.md

## ПОЛНОЕ СОСТОЯНИЕ НА 16.09.2026 (конец сессии) — для восстановления контекста

### Учётные данные и ключи (ЧУВСТВИТЕЛЬНО, только в этом файле, не публиковать)

**S_RU (31.77.169.67, hostname 295346.landvps.online)**
- SSH: пароль (техдолг, см. known-issues.md), алиас в Termux: `s-ru-commercial`
- Marzban admin: логин `sawrrg`, пароль сохранён отдельно у администратора
- Marzban панель: доступ только через `ssh -L 8000:localhost:8000 s-ru-commercial`,
  открывать `http://localhost:8000/dashboard/` (НЕ корень /, там пустая заглушка)

**Клиентский inbound "VLESS Reality" на S_RU (порт 443)**
```
Приватный ключ:  6JP9uEL099K0b4vImpTgnOU6ds2VqfQvfj7bjoqVWWI
Публичный ключ:  3i_6GTcRKvpAKjgvLHI7jUUlEqnOpCT1iPElZe1U6zU
Short ID:        9cde9e28846816db
Dest/SNI:        ozon.ru:443
Порт:            443
```

**Relay inbound "relay-in" на S2 (порт 8443, отдельный от Pi-hole/OpenVPN)**
```
Приватный ключ:  eOOhenrqlGjCDEkBf5W2a9gOcOkdwPmrUNItefMDbFY
Публичный ключ:  -29TmgczWnYyhqpw_ucFeE6Ks_MiqhbnNS43oaTn8Qc
UUID клиента:    9eeceb95-e7e1-4bf0-9412-e1aa29690c01
Short ID:        b2c2bae0765fc869
Dest/SNI:        www.microsoft.com:443
Порт:            8443
Путь конфига:    /opt/relay-node/config.json (на S2)
Путь compose:    /opt/relay-node/docker-compose.yml (на S2)
Контейнер:       relay-node (образ ghcr.io/xtls/xray-core:latest)
```

**Тестовый пользователь Marzban**
```
Username: test1
UUID: b8e4d93c-8076-4c4c-a61f-4aae49a047ef
Статус: active
Полная vless-ссылка (текущая, может измениться при пересоздании):
vless://b8e4d93c-8076-4c4c-a61f-4aae49a047ef@31.77.169.67:443?security=reality&type=tcp&sni=ozon.ru&fp=chrome&pbk=3i_6GTcRKvpAKjgvLHI7jUUlEqnOpCT1iPElZe1U6zU&sid=9cde9e28846816db
```

### Firewall на S2 (relay-порт 8443, ручные iptables, НЕ ufw)

```bash
# Уже применено на S2:
iptables -I INPUT 1 -p tcp -s 31.77.169.67 --dport 8443 -j ACCEPT
iptables -I INPUT 2 -p tcp --dport 8443 -j DROP
# Сохранено через netfilter-persistent save
```

### Firewall на S_RU (ufw)

```
22/tcp   ALLOW IN Anywhere  (SSH, техдолг - доступ по паролю)
443/tcp  ALLOW IN Anywhere  (VLESS Reality клиентский inbound)
```

### ТЕКУЩИЙ рабочий файл /var/lib/marzban/xray_config.json на S_RU (БЕЗ routing)

Путь на диске: /var/lib/marzban/xray_config.json
Путь .env: /opt/marzban/.env (содержит XRAY_JSON = "/var/lib/marzban/xray_config.json")
Путь compose: /opt/marzban/docker-compose.yml

Полное содержимое ТЕКУЩЕГО рабочего файла:

```json
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "tag": "VLESS Reality",
      "listen": "0.0.0.0",
      "port": 443,
      "protocol": "vless",
      "settings": { "clients": [], "decryption": "none" },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "ozon.ru:443",
          "xver": 0,
          "serverNames": ["ozon.ru"],
          "privateKey": "6JP9uEL099K0b4vImpTgnOU6ds2VqfQvfj7bjoqVWWI",
          "shortIds": ["9cde9e28846816db"]
        }
      },
      "sniffing": { "enabled": true, "destOverride": ["http", "tls"] }
    }
  ],
  "outbounds": [
    { "protocol": "freedom", "tag": "DIRECT" },
    { "protocol": "blackhole", "tag": "BLOCK" },
    {
      "tag": "to-eu",
      "protocol": "vless",
      "settings": {
        "vnext": [{
          "address": "77.105.161.151",
          "port": 8443,
          "users": [{ "id": "9eeceb95-e7e1-4bf0-9412-e1aa29690c01", "encryption": "none" }]
        }]
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "fingerprint": "chrome",
          "serverName": "www.microsoft.com",
          "publicKey": "-29TmgczWnYyhqpw_ucFeE6Ks_MiqhbnNS43oaTn8Qc",
          "shortId": "b2c2bae0765fc869"
        }
      }
    }
  ]
}
```

⚠️ ВАЖНО: этот конфиг НЕ содержит routing! Весь трафик от клиентов сейчас
идёт по правилу Xray "по умолчанию" - предположительно через ПЕРВЫЙ
outbound в списке (DIRECT), а to-eu вообще может быть НЕ ЗАДЕЙСТВОВАН
без явного routing-правила. ТРЕБУЕТСЯ ПРОВЕРКА в следующей сессии:
куда реально уходит трафик клиента (проверить внешний IP через 2ip.ru
с подключенным Hiddify - см. TODO).

### НЕУДАЧНАЯ версия конфига С routing (для истории, НЕ использовать как есть)

Отличие от рабочей версии - добавлен блок routing после outbounds:

```json
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [
      { "type": "field", "ip": ["geoip:private"], "outboundTag": "BLOCK" },
      { "type": "field", "ip": ["geoip:ru"], "outboundTag": "DIRECT" },
      { "type": "field", "domain": ["geosite:category-ru"], "outboundTag": "DIRECT" },
      { "type": "field", "network": "tcp,udp", "outboundTag": "to-eu" }
    ]
  }
```

С этим блоком клиент Hiddify получал timeout при подключении.
Geo-базы на месте (/usr/local/share/xray/geoip.dat и geosite.dat,
датированы Jan 9 2025 - не самые свежие, но присутствуют).

## TODO для следующей сессии (приоритет сверху вниз)

1. [ ] КРИТИЧНО: проверить, куда реально идёт трафик СЕЙЧАС (без routing) -
       подключиться Hiddify, открыть 2ip.ru/ifconfig.me, посмотреть IP.
       Если IP = S2 (77.105.161.151) - to-eu как outbound по умолчанию
       уже как-то работает (неожиданно, но возможно). Если IP = S_RU
       или вообще другой - трафик идёт через DIRECT, relay не используется.
2. [ ] Разобраться, почему секция routing ломает конфиг:
       - Проверить документацию Marzban на предмет "custom routing" -
         возможно, есть отдельный официальный способ задать routing
         именно через Marzban (не через прямую правку xray_config.json)
       - Попробовать балансировщик (balancers) вместо прямых правил
       - Проверить логи Xray на MAXIMUM verbosity (loglevel: debug)
         именно в момент попытки подключения с routing-блоком -
         в этой сессии этого не сделали, а стоило
3. [ ] После решения (2) - повторно включить geo-split, протестировать
       ОБА сценария (RU direct, мир через EU)
4. [ ] Обновить geoip.dat/geosite.dat на более свежие
5. [x] Настроить SECRET_KEY в .env Marzban (сейчас генерируется заново
       при каждом рестарте контейнера - см. known-issues.md p.7)
6. [ ] Резервный транспортный канал (OpenVPN/AmneziaWG) S_RU-S2 - ещё не начато
- [x] Настроить SSH-ключ вместо пароля на всех серверах (Termux + Windows PC)

---

## Обновление от 19.09.2026 — Geo-split работает, geo-базы обновлены

### Достигнутые результаты
✅ **Релей-канал S_RU → S2 полностью работает** (порт 8443, REALITY, без flow)
✅ **Geo-split работает корректно**:
   - Российские сайты (geosite:category-ru, geoip:ru) → DIRECT (IP S_RU 31.77.169.67)
   - Международные сайты → через relay на S2 (IP 77.105.161.151)
✅ **Ключевые сайты открываются**: Wikipedia, Tilda, arena.ai (через EU relay)
✅ **Geo-базы обновлены** до актуальных (Loyalsoldier, сентябрь 2026)

### Обновление geo-баз (персистентное решение)
Geo-базы хранятся на хосте в `/opt/marzban/xray-assets/` и монтируются в контейнер:
```yaml
volumes:
  - /var/lib/marzban:/var/lib/marzban
  - /opt/marzban/xray-assets:/usr/local/share/xray
```

**Команда обновления (раз в неделю через cron или вручную):**
```bash
cd /opt/marzban/xray-assets
wget -O geoip.dat https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat
wget -O geosite.dat https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat
cd /opt/marzban && docker compose restart
```

### Ключи REALITY (финальные, зафиксированы 19.09.2026)

**Клиентский inbound "VLESS Reality" на S_RU (порт 443)**
- Приватный ключ: `6JP9uEL099K0b4vImpTgnOU6ds2VqfQvfj7bjoqVWWI`
- Публичный ключ: `3i_6GTcRKvpAKjgvLHI7jUUlEqnOpCT1iPElZe1U6zU`
- Short ID: `9cde9e28846816db`
- Dest/SNI: `ozon.ru:443`

**Релейный inbound "relay-in" на S2 (порт 8443)**
- Приватный ключ: `EJYay7aXtb2YibPeXUwI8b5ihmzmNI_IFzohKrFc2m4`
- Публичный ключ: `M98Lpo-Tpv_6ySdyswpR7RSZvVRWCM46oAeqTryV-xo`
- UUID клиента: `9eeceb95-e7e1-4bf0-9412-e1aa29690c01`
- Short ID: `b2c2bae0765fc869`
- Dest/SNI: `1.1.1.1:443` (serverName: `cloudflare-dns.com`)
- **БЕЗ `flow: xtls-rprx-vision`** — вызывает конфликты версий

### Бэкапы (сделаны 19.09.2026)
- S_RU: `/root/vpn-commercial-backup/xray_config_20260919.json`
- S_RU: `/root/vpn-commercial-backup/marzban_env_20260919`
- S2: `/root/vpn-commercial-backup/relay_config_20260919.json`

### Известные ограничения (осознанно принятые)
- **Ozon, Wildberries, Сбербанк** могут блокировать датацентр-IP S_RU (`31.77.169.67`) при прямом доступе через DIRECT. Если критично — можно добавить их в исключения для routing через EU relay.
- **Клиентские настройки Hiddify** — дефолтные настройки работают. Кастомные параметры (`execute-config-as-is` и др.) могут ломать подключение.

### Что дальше (приоритеты на следующую сессию)
- [ ] Настроить SECRET_KEY в Marzban (постоянный, не генерируемый при каждом рестарте)
- [x] Настроить SSH-ключ вместо пароля на всех серверах (Termux + Windows PC)
- [ ] Telegram-бот (см. bot.md)
- [x] Автоматизация обновления geo-баз через cron

## Обновление от 20.09.2026 — Автоматизация обновления geo-баз

### Настроен cron для еженедельного обновления geo-баз (S_RU)
- Скрипт: `/opt/marzban/update-geo.sh`
- Расписание: каждое воскресенье в 04:00
- Лог: `/var/log/marzban-geo-update.log`
- Базы: Loyalsoldier (geosite + geoip)

## Завершено 22.09.2026
- [x] Сбор конфигов с S_RU (Marzban, xray_config, scripts)
