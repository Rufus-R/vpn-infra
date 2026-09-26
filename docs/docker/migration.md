# Миграция в Docker

## Статус: В процессе планирования

## Принятые решения

- **OpenVPN НЕ переносится в Docker** (рабочая система, высокий риск)
- **Переносятся в Docker**: sing-box, hysteria2, vpn-admin
- **Pi-hole уже нативный на S2** — пока не трогаем
- **MTProxy демонтирован 26.09.2026** (не переносится в Docker, признан нежизнеспособным)

## Let's Encrypt (Cloudflare DNS API)

### Статус: ❌ НЕ работает

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
| VLESS Reality | 2443 | TCP | sing-box, без сертификата |
| VLESS TLS | 2444 | TCP | требует Let's Encrypt |
| Hysteria 2 | 2445 | UDP | требует Let's Encrypt |
| vpn-admin | 18080 | TCP | только из VPN |

### S2

| Сервис | Порт | Протокол | Примечание |
|--------|------|----------|-----------|
| Pi-hole Web | 18081 | TCP | только tun0 |
| Pi-hole DNS | 53 | UDP/TCP | только tun0 |

## sing-box (генерация ключей)

```bash
# Reality keypair
docker run --rm ghcr.io/sagernet/sing-box:latest generate reality-keypair

# UUID для клиентов
docker run --rm ghcr.io/sagernet/sing-box:latest generate uuid
```

## Планируемая структура репозитория

```
vpn-infra/
├── .gitignore              # ВАЖНО: исключить все секреты
├── README.md
├── s1/
│   ├── docker-compose.yml
│   ├── sing-box/config/
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

1. [ ] Починить Cloudflare API token
2. [ ] Получить Let's Encrypt сертификат
3. [ ] Сгенерировать Reality keypair + UUID
4. [ ] Написать config.json для sing-box
5. [ ] Написать docker-compose.yml для S1
6. [ ] Написать docker-compose.yml для S2
7. [ ] Портировать vpn-admin под Docker
8. [ ] Тестировать параллельно с текущей системой
9. [ ] Создать приватный GitHub репозиторий

## Секреты

Реальный Cloudflare API Token хранится в зашифрованном виде:
- Файл: `secrets/cloudflare-token.txt` (зашифрован через git-crypt)
- Расшифровка: `git-crypt unlock` (требуется GPG-ключ)
