# Миграция в Docker

## Статус: Частично отменено (26.09.2026)

## Обновление 26.09.2026

Планы по sing-box (VLESS Reality/TLS) и Hysteria2 для домашнего сегмента
**отменены**. Причина: OpenVPN подтверждён стабильно рабочим через
Мегафон (единственный оператор, с которым ранее была проблема) — нужды
во втором протоколе для обхода блокировок в домашнем сегменте больше
нет. См. `system-state.md`, "Решённые проблемы", п.9.

MTProxy демонтирован ранее в этот же день (26.09.2026), по не связанной,
но аналогичной причине — признан нежизнеспособным. Подробности:
`services/archive/mtg-deprecated-20260926.md`.

Единственное, что остаётся актуальным ниже — контейнеризация vpn-admin
(изоляция веб-панели, не связана с выбором протокола) и общий раздел
про Let's Encrypt (может понадобиться для других целей в будущем).

## Принятые решения (актуально)

- **OpenVPN НЕ переносится в Docker** (рабочая система, высокий риск)
- **sing-box / Hysteria2 — ОТМЕНЕНО** (см. выше)
- **MTProxy — ДЕМОНТИРОВАН** (26.09.2026, не переносится в Docker)
- **vpn-admin** — контейнеризация всё ещё рассматривается как отдельная,
  низкоприоритетная задача (изоляция веб-панели от хост-системы)
- **Pi-hole** остаётся нативным на S2 — не трогаем

## Let's Encrypt (Cloudflare DNS API)

### Статус: ❌ НЕ работает

Сохраняется как справочная информация — может понадобиться для доступа
к домену `maximum.ru.net` в других целях (не для VLESS TLS/Hysteria2,
эти протоколы отменены).

Файл: `/root/.secrets/cloudflare.ini`
```ini
```

```bash
# Установка
apt install -y certbot python3-certbot-dns-cloudflare

# Получение сертификата
certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /root/.secrets/cloudflare.ini \
  -d maximum.ru.net \
  --agree-tos --no-eff-email \
  -m your@email.com
```

### Диагностика токена
```bash
curl -s https://api.cloudflare.com/client/v4/user/tokens/verify \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

### Необходимые права токена
- Zone / DNS / Edit
- Zone / Zone / Read
- Zone Resources: зона где `maximum.ru.net`

### Альтернатива (если DNS API не заработает)
```bash
# 1. Снять Cloudflare proxy (серое облако) для maximum.ru.net
# 2. Открыть порт 80
iptables -I INPUT -p tcp --dport 80 -j ACCEPT
# 3. Получить сертификат
certbot certonly --standalone -d maximum.ru.net
# 4. Вернуть Cloudflare proxy, закрыть 80
iptables -D INPUT -p tcp --dport 80 -j ACCEPT
netfilter-persistent save
```

## Certbot автообновление

На S1 активен `certbot.timer` (2 раза в день).
Cron: `/etc/cron.d/certbot`

После получения сертификата автообновление работает автоматически.
Сертификат будет в: `/etc/letsencrypt/live/maximum.ru.net/`

## Планируемые сервисы и порты

### S1

| Сервис | Порт | Протокол | Примечание |
|--------|------|----------|-----------|
| vpn-admin | 18080 | TCP | только из VPN (низкий приоритет) |

~~VLESS Reality (2443), VLESS TLS (2444), Hysteria2 (2445)~~ —
отменено 26.09.2026, см. выше.

### S2

| Сервис | Порт | Протокол | Примечание |
|--------|------|----------|-----------|
| Pi-hole Web | 18081 | TCP | только tun0 |

## Планируемая структура репозитория

```
vpn-infra/
├── .gitignore              # ВАЖНО: исключить все секреты
├── README.md
├── s1/
│   └── vpn-admin/
└── s2/
    ├── docker-compose.yml
    └── pihole/
```

## .gitignore (обязательные исключения)

```
**/pki/private/*
**/pki/*.key
**/ca.key
**/ta.key
**/*.key
**/crl.pem
.env
cloudflare.ini
```

## Что осталось сделать

1. [ ] (низкий приоритет) Портировать vpn-admin под Docker
2. [ ] (низкий приоритет) Починить Cloudflare API token / Let's Encrypt,
       если появится конкретная цель использования сертификата

## Секреты

Реальный Cloudflare API Token хранится в зашифрованном виде:
- Файл: `secrets/cloudflare-token.txt` (зашифрован через git-crypt)
- Расшифровка: `git-crypt unlock` (требуется GPG-ключ)
