# VPN Infrastructure — Документация

## Последнее обновление: 2026-08-03

## Структура документации

```
docs/
├── README.md                    # Этот файл — навигация и быстрый старт
├── architecture/
│   └── overview.md              # Общая архитектура, схема сети, узлы
├── openvpn/
│   ├── s2-server.md             # OpenVPN сервер на S2 (Европа)
│   ├── s1-client-to-s2.md      # OpenVPN клиент S1 → S2
│   ├── s1-server.md             # OpenVPN сервер S1 для клиентов
│   └── clients.md               # Список клиентов, CCD, сертификаты
├── services/
│   ├── pihole.md                # Pi-hole на S2
│   └── vpn-admin.md             # Веб-панель управления клиентами
├── networking/
│   ├── iptables-s1.md           # Правила iptables на S1
│   ├── iptables-s2.md           # Правила iptables на S2
│   └── routing.md               # Policy routing, таблицы маршрутизации
├── admin/
│   ├── backups.md               # Бэкапы, артефакты, расположение файлов
│   └── opnsense.md              # Настройки OPNsense
├── docker/
│   └── migration.md             # План миграции в Docker, статус
├── problems/
│   ├── lan-access.md            # ОТКРЫТАЯ ПРОБЛЕМА: family → LAN
│   └── known-issues.md          # Известные проблемы и замечания
├── commercial/
│   ├── overview.md               # Архитектура коммерческого VPN-проекта
│   ├── routing.md                 # Geo-split маршрутизация RU/EU
│   ├── tariffs.md                 # Тарифы, триал, реферальная программа
│   ├── bot.md                     # Telegram-бот, схема БД, сценарии
│   ├── deployment.md              # Порядок развёртывания
│   └── known-issues.md            # Риски коммерческого проекта
└── reference/
    ├── commands.md              # Полезные команды для диагностики
    ├── ports.md                 # Таблица всех портов
    └── versions.md              # Версии ПО, ресурсы серверов
```

## Быстрая навигация

| Задача | Файл |
|--------|------|
| Понять общую схему сети | [architecture/overview.md](architecture/overview.md) |
| Настроить OpenVPN на S2 | [openvpn/s2-server.md](openvpn/s2-server.md) |
| Настроить S1 как клиент к S2 | [openvpn/s1-client-to-s2.md](openvpn/s1-client-to-s2.md) |
| Настроить OpenVPN сервер S1 | [openvpn/s1-server.md](openvpn/s1-server.md) |
| Добавить/отозвать клиента | [services/vpn-admin.md](services/vpn-admin.md) |
| Список всех клиентов | [openvpn/clients.md](openvpn/clients.md) |
| Настройки OPNsense | [admin/opnsense.md](admin/opnsense.md) |
| Диагностика проблемы LAN | [problems/lan-access.md](problems/lan-access.md) |
| Все открытые проблемы | [problems/known-issues.md](problems/known-issues.md) |
| Все порты | [reference/ports.md](reference/ports.md) |
| Быстрые команды | [reference/commands.md](reference/commands.md) |
| Миграция в Docker | [docker/migration.md](docker/migration.md) |
| Коммерческий VPN-проект | [commercial/overview.md](commercial/overview.md) |

## Текущий статус сервисов

| Компонент | Статус |
|-----------|--------|
| OpenVPN S2↔S1 туннель | ✅ Работает |
| OpenVPN клиенты → интернет через S2 | ✅ Работает |
| Pi-hole на S2 | ✅ Работает |
| vpn-admin панель | ✅ Работает |
| MTProxy/MTG | ❌ Демонтирован (26.09.2026), признан нежизнеспособным |
| OPNsense подключение к S1 | ✅ Работает |
| OPNsense → интернет через VPN | ✅ Работает |
| Family → LAN доступ | ✅ Работает (исправлено 03.08.2026) |
| Let's Encrypt | ❌ Ошибка авторизации |
| sing-box / Hysteria2 | 🔲 Не начато |
| Docker-миграция | 🔲 В процессе планирования |
| Коммерческий VPN (S_RU) | Планирование, документация зафиксирована |
