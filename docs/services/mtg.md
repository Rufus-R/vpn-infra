# MTProxy (MTG) на S1

## Файлы конфигурации (S1: 194.55.236.229)

```
/usr/local/bin/mtg                  # Исполняемый файл (v2.1.1)
/etc/mtg/443.toml                   # Порт 443 (активен)
/etc/mtg/8443.toml                  # Порт 8443 (не запущен)
/etc/mtg/9443.toml                  # Порт 9443 (не запущен)
/etc/mtg/443.env
/etc/mtg/8443.env
/etc/mtg/9443.env
/etc/mtg/10443.env
/etc/systemd/system/mtg@.service    # Systemd шаблон
```

## Установка

```bash
cd /opt
wget https://github.com/9seconds/mtg/releases/download/v2.1.1/mtg-2.1.1-linux-amd64.tar.gz
tar xvf mtg-2.1.1-linux-amd64.tar.gz
mv mtg-2.1.1-linux-amd64/mtg /usr/local/bin/
useradd -r -s /bin/false mtproxy    # создаётся с UID=999
```

## Конфигурации

Файл: `/etc/mtg/443.toml`
```toml
secret = "7m4WUWjEwPYM2ROATJwu8mxvem9uLnJ1"
bind-to = "0.0.0.0:443"
[network]
doh-ip = "1.1.1.1"
```

Файл: `/etc/mtg/8443.toml`
```toml
secret = "7rl2I8BzLwUusf940rhB2hoyZ2lzLnJ1"
bind-to = "0.0.0.0:8443"
[network]
doh-ip = "1.1.1.1"
```

Файл: `/etc/mtg/9443.toml`
```toml
secret = "7llbptot0-OWqbIa1c7NYbxjZGVrLnJ1"
bind-to = "0.0.0.0:9443"
[network]
doh-ip = "1.1.1.1"
```

```bash
chown root:mtproxy /etc/mtg/*.toml
chmod 640 /etc/mtg/*.toml
```

## Systemd unit

Файл: `/etc/systemd/system/mtg@.service`

```ini
[Unit]
Description=MTG instance %i
After=network-online.target
Wants=network-online.target

[Service]
User=mtproxy
Group=mtproxy
ExecStart=/usr/local/bin/mtg run /etc/mtg/%i.toml
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

## Синтаксис команд

```bash
mtg generate-secret -x <hostname>   # генерация секрета (hex формат)
mtg run /etc/mtg/443.toml           # запуск
mtg access /etc/mtg/443.toml        # получить ссылки подключения
```

## Изоляция трафика через S2

UID пользователя `mtproxy` = **999**

```bash
# Mangle: только TCP/443 от mtproxy маркируется
iptables -t mangle -I OUTPUT 1 -m owner --uid-owner 999 -p udp --dport 53 -j RETURN
iptables -t mangle -I OUTPUT 2 -m owner --uid-owner 999 -p tcp --dport 53 -j RETURN
iptables -t mangle -I OUTPUT 3 -m owner --uid-owner 999 -p tcp --dport 443 -j MARK --set-mark 100

# NAT: маркированный трафик уходит через tun0 → S2
iptables -t nat -A POSTROUTING -m owner --uid-owner 999 -o tun0 -j MASQUERADE
```

## Управление

```bash
systemctl start mtg@443
systemctl stop mtg@443
systemctl status mtg@443
journalctl -u mtg@443 -n 20 --no-pager
```

## Получение ссылок

```bash
mtg access /etc/mtg/443.toml
```

## Домены для fronting

Проверенные домены (TLS работает):
`ozon.ru`, `2gis.ru`, `cdek.ru`, `rutube.ru`, `avito.ru`,
`hh.ru`, `yandex.ru`, `vk.com`, `mail.ru`, `ok.ru`,
`kinopoisk.ru`, `dzen.ru`

## Статус

| Порт | Сервис | Состояние |
|------|--------|-----------|
| 443 | `mtg@443` | ⚠️ Запущен, но ошибки timeout при подключении к `ozon.ru` |
| 8443 | `mtg@8443` | ❌ Не запущен |
| 9443 | `mtg@9443` | ❌ Не запущен |

**РЕШЕНИЕ**: MTProxy отложен как приоритет.
Не работал во время реальных блокировок.

## Ошибки в логах

```
cannot dial to tcp:ozon.ru:443: i/o timeout
```

Причины: rate limiting со стороны ozon.ru, блокировка на S2,
или проблемы маршрутизации mtg → tun0 → S2 → ozon.ru.
