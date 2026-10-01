# Firewall на S2 (ufw)

## Обновлено: 01.10.2026 — миграция с iptables/netfilter-persistent на ufw

Предыдущая версия документа (iptables + `netfilter-persistent`, до 30.09.2026) — в
[archive/iptables-s2-pre-ufw-20260930.md](archive/iptables-s2-pre-ufw-20260930.md).

## Текущая конфигурация

- Firewall: `ufw` (единообразно с S_RU и Panel). Default: deny incoming, allow outgoing, deny routed.
- Правила: `/etc/ufw/user.rules` (создаются командами `ufw ...`, комментарии в `ufw status`).
- NAT: блок `*nat` в начале `/etc/ufw/before.rules` (MASQUERADE `10.8.0.0/24` и `10.9.0.0/24` через `ens3`).
- Forward: `ufw route allow in on tun0 out on ens3`; обратный трафик — по conntrack.
- `ip_forward=1` задан в `/etc/sysctl.conf`.
- `MANAGE_BUILTINS=no`, IPv6 включён в ufw (у сервера нет глобального IPv6, только link-local).
- fail2ban (jail `sshd`, `3x-ipl`) банит через `nftables` (таблица `inet f2b-table`) — с ufw не конфликтует.
- Удалены: `netfilter-persistent`, `iptables-persistent`, Docker (вместе с `DOCKER*`-цепочками и `docker0`).
- Устаревший файл `/etc/iptables/rules.v4.obsolete-20261001` оставлен как артефакт (не загружается).

## Правила (ufw status)

| Порт | Источник | Назначение |
|------|----------|-----------|
| 22/tcp | любой | SSH |
| 80/tcp | любой | ACME HTTP-01 |
| 10001/tcp | `31.77.169.67` (S_RU), `31.77.173.218` (Panel), `194.55.236.229` (S1) | relay-канал |
| 25307/tcp | `194.55.236.229`, `31.77.173.218`, `46.32.82.242`, `10.8.0.0/24` | управление 3x-ui нодой |
| 1194/udp | `194.55.236.229` | OpenVPN-туннель S1 |
| 53 (tcp+udp), `in on tun0` | `10.8.0.0/24` | Pi-hole DNS |
| 8080/tcp, `in on tun0` | `10.8.0.0/24`, `10.9.0.0/24`, `192.168.0.0/24` | Pi-hole admin |
| route `tun0 → ens3` | — | VPN → интернет |

## Правила работы

- Все изменения только через `ufw` (и `before.rules` для NAT). Прямые `iptables -I/-A` не использовать:
  они не переживут перезагрузку и нарушают порядок правил.
- Осторожно с `ufw reload`: NAT-правила из `before.rules` могут продублироваться (предположение,
  не проверено). После reload проверять `iptables -t nat -S POSTROUTING` (по одной строке на подсеть).
- Перед массовыми правками: `iptables-save > /root/fw-backup-<дата>.v4` и `cp -a /etc/ufw ...`.
- Временное правило для теста — с комментарием `(temporary test)` и пометкой в `system-state.md`.

## Бэкапы и откат

- На S2: `/root/fw-backup-20261001-143917/` — состояние до миграции (`iptables-live-final.v4`),
  `/etc/ufw` до/после, финальный снимок `*ufw-final*`, архивы пустых томов Docker.
- Откат на старый набор: `ufw --force disable && iptables-restore < iptables-live-final.v4`
  (персистентности после этого нет).

## Проверено

- **Ребут-тест пройден 01.10.2026 (18:37).** ufw, NAT (по одной MASQUERADE на подсеть), forward,
  fail2ban (nft), OpenVPN, x-ui, Pi-hole поднялись сами. Туннель S1↔S2, relay 10001 (S_RU, Panel),
  25307 (Panel), DNS и admin Pi-hole подтверждены. Сразу после загрузки службы стартуют с задержкой
  в секунды — проверять через 30–60 с.
- Консоль провайдера (VNC) не принимает ввод в поле `login:`. root-пароль задан, SSH по паролю закрыт.
  Аварийный путь — rescue-режим провайдера.

## История

- **27.09.2026** — исправлен неверный порядок ACCEPT/DROP: 53/80/1194 были открыты всему интернету.
- **28.09.2026** — демонтирован Docker-контейнер `relay-node` (порт 8443).
- **29.09.2026** — default policy INPUT переведена на DROP.
- **01.10.2026** — миграция на ufw. Выяснилось, что записи «сохранено персистентно» от 27–29.09
  были ошибочны: `/etc/iptables/rules.v4` содержал `INPUT ACCEPT` и 8443, а у
  `netfilter-persistent` не было плагинов — после ребута правил бы не было. Исправлено
  миграцией. Pi-hole web перенесён с 80 на 8080 (80 освобождён под ACME).
- **01.10.2026 (вечер)** — ребут-тест пройден, см. «Проверено».
