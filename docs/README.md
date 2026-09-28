# VPN Infrastructure — Документация

## Последнее обновление: 28.09.2026

## Принципы организации документации

- `docs/` (корень) — кросс-контурные мета-файлы: этот README,
  `session-start.md` (точка входа сессии), `system-state.md` (текущее
  состояние, обновляется после каждой сессии), `diagnostic-commands.md`
  (read-only диагностика)
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
├── README.md, session-start.md, system-state.md, diagnostic-commands.md
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
    ├── overview.md, migration-3xui.md, tariffs.md, bot.md
    ├── reference/{commands,versions}.md (заглушки, TODO)
    └── archive/ (Marzban-эпоха)
```

## Быстрая навигация

| Задача | Файл |
|--------|------|
| Начать сессию | [session-start.md](session-start.md) |
| Текущее состояние системы | [system-state.md](system-state.md) |
| Домашняя архитектура | [home/architecture/overview.md](home/architecture/overview.md) |
| Домашние открытые проблемы | [home/problems/known-issues.md](home/problems/known-issues.md) |
| iptables S2 (общий хост) | [shared/networking/iptables-s2.md](shared/networking/iptables-s2.md) |
| Все порты (общий хост) | [shared/reference/ports.md](shared/reference/ports.md) |
| Коммерческий проект | [commercial/overview.md](commercial/overview.md) |
| Миграция на 3x-ui | [commercial/migration-3xui.md](commercial/migration-3xui.md) |

## Текущий статус (28.09.2026)

| Компонент | Статус |
|-----------|--------|
| OpenVPN S2↔S1, клиенты → интернет | ✅ Работает |
| Pi-hole на S2 | ✅ Работает |
| S2 security (открытые порты 53/80/1194) | ✅ Исправлено 27.09.2026 |
| MTProxy / relay-node (legacy) | ❌ Демонтированы (26.09, 28.09.2026) |
| Коммерческий проект: Marzban | ❌ Полностью демонтирован (28.09.2026) |
| Коммерческий проект: 3x-ui | 🔶 В процессе, базовый канал работает, geo-split не настроен |
