# Geo-split маршрутизация

## Концепция

Клиентский конфиг содержит ДВА outbound'а и правило выбора между ними:

```
routing rules (Xray-core, в шаблоне подписки Marzban):
├── geoip:ru ИЛИ geosite:category-ru → outbound "direct"
└── default (всё остальное)          → outbound "chain-to-eu"
```

## outbound "direct"

Прямое соединение клиента с российскими ресурсами БЕЗ прохождения через VPN.
Клиент виден как обычный российский IP (важно для банков, госуслуг).

## outbound "chain-to-eu"

Цепочка: Клиент → S_RU (VLESS+Reality inbound) → relay → S2 (EU exit) → интернет.
Реализуется через chain outbound (proxyOutbound) в Xray-core на стороне S_RU:
трафик, попавший на S_RU не по direct-правилу, дополнительно проксируется на S2.

## Обновление geoip/geosite баз

Источник: v2fly/domain-list-community (geosite), community geoip базы.
Периодичность: раз в неделю, через cron на S_RU.
TODO: настроить cron-job и путь к файлам после разворачивания marzban-node.

## Статус реализации

Обновлено 19.09.2026 (см. `commercial/overview.md`, раздел "Обновление от 19.09.2026"):

- [x] outbound "direct" настроен
- [x] outbound "chain-to-eu" настроен (S_RU → S2), порт 8443, без flow
- [x] Cron автообновления geoip/geosite (каждое воскресенье 04:00)
- [x] Тестирование: RU-домен идёт напрямую (подтверждено, IP 31.77.169.67)
- [x] Тестирование: мировой домен идёт через S_RU→S2 (подтверждено, IP 77.105.161.151)
- [ ] Кастомный Jinja-шаблон подписки в Marzban с routing-блоком — не требовался,
      routing настроен напрямую в xray_config.json
