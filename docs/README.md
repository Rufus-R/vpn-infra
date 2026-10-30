# VPN Infrastructure — Документация

## Последнее обновление: 30.10.2026

## Принципы организации документации

- `docs/` (корень) — кросс-контурные мета-файлы: этот README,
  `session-start.md` (точка входа сессии), `system-state.md` (текущее
  состояние, обновляется после каждой сессии), `service-checklist.md`
  (порядок диагностики сервисов), `diagnostic-commands.md` (read-only команды)
- `docs/home/` — домашний контур (S1, S2 как OpenVPN/Pi-hole, OPNsense, LAN)
- `docs/commercial/` — коммерческий проект (S_RU, Panel, S2 как 3x-ui нода)
- `docs/shared/` — инфраструктура на стыке контуров (S2 физически один
  хост для обеих ролей): `shared/networking/iptables-s2.md`,
  `shared/reference/ports.md`
- Правило архивации: закрытые проблемы старше ~1 сессии с длинным
  post-mortem выносятся в `<раздел>/archive/`, в живом документе
  остаётся краткое резюме + ссылка

## Структура

```
docs/
├── README.md, session-start.md, system-state.md, service-checklist.md, diagnostic-commands.md, next-session-todo.md
├── archive/ (закрытое из system-state и next-session-todo, журнал сессий 30.09–09.10)
├── home/
│   ├── architecture/overview.md
│   ├── openvpn/{clients,s1-server,s2-server,s1-client-to-s2}.md
│   ├── networking/{routing,iptables-s1}.md
│   ├── admin/{backups,opnsense}.md
│   ├── docker/migration.md
│   ├── services/{pihole,vpn-admin}.md, services/archive/
│   ├── problems/known-issues.md, problems/archive/
│   └── reference/{commands,versions}.md
├── shared/
│   ├── networking/iptables-s2.md
│   └── reference/ports.md
└── commercial/
    ├── overview.md, operations-log.md, tariffs.md, bot.md
    ├── reference/{commands,versions}.md (заглушки, TODO)
    └── archive/ (Marzban-эпоха; журнал сессий 27.09–06.10 и 08–13.10; раздел Robokassa из bot.md)
```

## Быстрая навигация

| Задача | Файл |
|--------|------|
| Начать сессию | [session-start.md](session-start.md) |
| Текущее состояние системы | [system-state.md](system-state.md) |
| Чек-лист сервисов (порядок диагностики) | [service-checklist.md](service-checklist.md) |
| Домашняя архитектура | [home/architecture/overview.md](home/architecture/overview.md) |
| Домашние открытые проблемы | [home/problems/known-issues.md](home/problems/known-issues.md) |
| Firewall S2 — ufw (общий хост) | [shared/networking/iptables-s2.md](shared/networking/iptables-s2.md) |
| Все порты (общий хост) | [shared/reference/ports.md](shared/reference/ports.md) |
| Коммерческий проект | [commercial/overview.md](commercial/overview.md) |
| Операционный журнал коммерческого проекта | [commercial/operations-log.md](commercial/operations-log.md) |
| Открытые задачи | [next-session-todo.md](next-session-todo.md) |

## Текущий статус (30.10.2026)

| Компонент | Статус |
|-----------|--------|
| OpenVPN S2↔S1, клиенты → интернет | ✅ Работает |
| Pi-hole на S2 | ✅ Работает |
| S2 security (открытые порты 53/80/1194) | ✅ Исправлено 27.09.2026 |
| S2 как коммерческий exit | ⛔ Входящий трафик блокирован провайдером с 29.10.2026 (тикет отправлен) |
| Коммерческий канал | ✅ Клиент → S_RU:443 → S3:10001 → интернет; geo-split на S_RU сохранён |
| Panel (мастер-панель, бот, лендинг) | ✅ `31.77.78.144`; серт до 14.01.2027 |
| Telegram-бот | ✅ Работает; поллинг Telegram через socks5 на S3 с 30.10.2026 (до этого 17 ч простоя из-за прокси на заблокированном S2) |
| Туннель S1↔S3 (`home-backup`, 8443/TCP) | ⚠️ Handshake есть, трафик не проходит — открытая задача |
| DNSSEC для `netru.ru.net` | ⚠️ DS в зоне `ru.net` не добавлен — обращение в SpaceWeb |
