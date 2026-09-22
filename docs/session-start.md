# Быстрый старт новой сессии

Этот файл — чекпоинт для передачи контекста инфраструктуры новому ассистенту.
Выполните команды из секции нужного сервера и приложите вывод.
Все команды ТОЛЬКО ЧИТАЮЩИЕ — они ничего не меняют.

Управление с мобильного (Termux), алиасы в ~/.ssh/config.
Коммерческий проект полностью изолирован от домашней инфраструктуры.

---

## Секция 1: Общая документация (выполнять на S1)

Выведите эти файлы в начале сессии для полного контекста.

    # Навигация по документации
    cat /root/docs/README.md

    # Общая архитектура (узлы, подсети, логика трафика)
    cat /root/docs/architecture/overview.md

    # Коммерческий проект — обзор и схема маршрутизации
    cat /root/docs/commercial/overview.md

    # Коммерческий проект — развёртывание, финальный рабочий конфиг
    cat /root/docs/commercial/deployment.md

    # Известные проблемы (домашняя инфраструктура)
    cat /root/docs/problems/known-issues.md

    # Известные проблемы (коммерческий проект)
    cat /root/docs/commercial/known-issues.md

Краткая справка для ассистента:
- 3 сервера: S1 (домашний хаб), S2 (выходной шлюз + коммерческий релея),
  S_RU (коммерческий проект).
- Коммерческий канал: клиент -> S_RU (порт 443) -> [не RU] релея -> S2 (порт 8443) -> интернет.
  [если RU] -> напрямую с S_RU.
- Рабочее состояние коммерческого канала зафиксировано в
  /root/docs/commercial/deployment.md (обновление от 19.09.2026).

---

## Секция 2: S1 (194.55.236.229, maximum.ru.net) — домашний хаб

Роль: точка входа для семейных и дружеских клиентов, туннель к S2,
MTProxy, веб-панель управления клиентами.

### Диагностика

    # Статус ключевых сервисов
    systemctl is-active openvpn-server@server openvpn-client@s2-client vpn-admin mtg@443

    # Подключённые клиенты (кто в сети сейчас)
    grep CLIENT_LIST /var/log/openvpn-status-tun1.log | awk -F',' '{print $2, $4}'

    # Туннель к S2 жив?
    ping -c 2 -W 2 10.8.0.1

    # Маршрутизация клиентов (таблица vpn)
    ip route show table vpn
    ip rule list

    # Фаервол (ключевые цепочки)
    iptables -vnL FORWARD --line-numbers | head -10
    iptables -t nat -vnL POSTROUTING --line-numbers | head -10

### Ожидаемый результат
- Все сервисы в статусе active.
- В списке клиентов: статические адреса 10.9.0.2–10.9.0.27, плюс 10.9.0.5 для OPNsense01.
- Пинг до 10.8.0.1 без потерь.
- В таблице маршрутизации: 10.9.0.0/24 через 10.8.0.1.

### Обязательная документация (читать на S1)

    cat /root/docs/openvpn/s1-server.md
    cat /root/docs/openvpn/s1-client-to-s2.md
    cat /root/docs/openvpn/clients.md
    cat /root/docs/services/vpn-admin.md
    cat /root/docs/services/mtg.md
    cat /root/docs/networking/iptables-s1.md
    cat /root/docs/networking/routing.md

---

## Секция 3: S2 (77.105.161.151) — выходной шлюз + коммерческий релея

Роль: выход в интернет для домашнего трафика через S1,
Pi-hole (DNS-фильтрация), коммерческий релея-узел (порт 8443).

### Диагностика (выполнять на S2)

    # Статус системных сервисов
    systemctl is-active openvpn-server@server pihole-FTL

    # Docker-контейнеры (коммерческий релея)
    docker ps --format 'table {{.Names}}\t{{.Status}}'

    # Ключевые порты (релея + системные)
    ss -tlnp | grep -E ':(8443|443|1194|53)\s'

    # Фаервол: порт 8443 открыт ТОЛЬКО для S_RU (31.77.169.67)
    iptables -vnL INPUT --line-numbers | grep 8443

    # Логи релея-контейнера (последние подключения)
    docker logs relay-node --tail 20 2>&1

    # Pi-hole доступен через туннель?
    curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1/admin/login

### Ожидаемый результат
- Контейнер релея в статусе Up.
- В фаерволе: правило для порта 8443 только с источником 31.77.169.67.
- В логах релея — записи о принятых подключениях (если был трафик).
- curl возвращает 200 или редирект (301/302).

### Обязательная документация (читать на S1)

    cat /root/docs/openvpn/s2-server.md
    cat /root/docs/services/pihole.md
    cat /root/docs/networking/iptables-s2.md
    cat /root/docs/commercial/deployment.md

---

## Секция 4: S_RU (31.77.169.67) — коммерческий проект

Роль: панель управления, точка входа для клиентов (порт 443),
разделение трафика по географическому признаку.

### Диагностика (выполнять на S_RU)

    # Статус контейнеров
    docker ps --format 'table {{.Names}}\t{{.Status}}'
    cd /opt/marzban && docker compose ps

    # Конфиг панели (ключевые секции)
    docker exec marzban-marzban-1 cat /var/lib/marzban/xray_config.json \
      | jq '{outbounds: [.outbounds[].tag], routing: .routing.rules | length, dns: .dns.servers}'

    # Фаервол
    ufw status numbered

    # Исходящий доступ (должен работать)
    curl -s --max-time 5 https://ifconfig.me; echo

    # Гео-базы (актуальность)
    docker exec marzban-marzban-1 ls -lh /usr/local/share/xray/geoip.dat /usr/local/share/xray/geosite.dat

### Ожидаемый результат
- Контейнер панели в статусе Up.
- В конфиге: три исходящих тега (прямой, блокировка, на ЕС), 4 правила маршрутизации.
- Фаервол: открыты порты 22 и 443.
- curl возвращает 31.77.169.67.
- ⚠️ Проверить дату гео-баз. Если дата старая (январь 2025) — это открытый вопрос.

### Обязательная документация (читать на S1)

    cat /root/docs/commercial/deployment.md
    cat /root/docs/commercial/routing.md
    cat /root/docs/commercial/overview.md
    cat /root/docs/commercial/known-issues.md

---

## Сквозная проверка коммерческого канала (с телефона)

Подключите клиент (дефолтные настройки) и откройте:

| Сайт | Ожидаемый результат |
|------|---------------------|
| yandex.ru | IP 31.77.169.67 (прямой выход) |
| google.com | Открывается |
| ifconfig.me | IP 77.105.161.151 (через ЕС-релея) |
| wikipedia.org | Открывается (через ЕС-релея) |

---

## Открытые вопросы и технический долг

1. Гео-базы: проверить, обновились ли они после монтажа тома.
2. Бэкапы коммерческого проекта (сделаны 19.09.2026).
3. Технический долг:
   - Фиксация секретного ключа панели.
   - Настройка доступа по ключу вместо пароля на S_RU.
   - Бэкап домашней инфраструктуры устарел.
   - Настройка отзыва сертификатов на S1.
