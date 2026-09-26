# Бэкапы и артефакты

## Бэкапы на S1

Расположение: `/root/vpn-infra-backup/s1/`

⚠️ **Основной бэкап (`pki/`, конфиги) снят ~22.06.2026 — устарел!**
Не содержит: SET01, Anna, Vova, Serafim, Nikita, VovaL, актуальные CCD
(статические адреса 10.9.0.22–27 от 18.08.2026), актуальные iptables
(без MTProxy, демонтирован 26.09.2026).

✅ **Отдельный свежий снимок PKI**: `pki_20260920/` (20.09.2026) —
содержит все 9 актуальных сертификатов (Anna, Mars, OPNsense01, Petr,
Serafim, server, SET01, Vova, VovaL), подтверждено `ls -la` 26.09.2026.
См. также раздел "Обновление бэкапа" ниже.

```
/root/vpn-infra-backup/s1/
├── app.py
├── ca.crt, s1-client.crt, s1-client.key
├── s2-client.conf
├── route-up.sh, route-100.txt, route-vpn.txt   # route-100.txt устарел (MTProxy демонтирован 26.09.2026)
├── server.conf
├── ta.key
├── ip-rules.txt
├── iptables.rules
├── sysctl.conf
├── pki/                    # УСТАРЕЛ (22.06.2026): friend1, Mars, OPNsense01, Petr, SET, server
├── pki_20260920/           # Актуальнее (20.09.2026), полный набор из 9 клиентов
├── ccd/                    # УСТАРЕЛ (22.06.2026): family-user1, lan-router, Mars, OPNsense01, SET
```

⚠️ **Технический долг**: помимо PKI (`pki_20260920`), остальные компоненты
бэкапа (конфиги, iptables, CCD целиком, route-up.sh) не обновлялись с
22.06.2026 — требуется полный свежий снимок, не только PKI. См. раздел
"Обновление бэкапа" ниже.

## Бэкапы на S2

Расположение: `/root/vpn-infra-backup/s2/`

```
/root/vpn-infra-backup/s2/
├── server.conf
├── ta.key
├── iptables.rules
├── sysctl.conf
├── pki/                    # PKI (server, s1-client)
└── ccd/
    └── s1-client
```

## Артефакты в /root на S1

| Путь | Содержимое | Актуальность |
|------|-----------|-------------|
| `/root/friend1/friend1.ovpn` | .ovpn файл для friend1 | ⚠️ устарел, friend1 отозван |
| `/root/opnsense01/` | ca.crt, OPNsense01.crt/.key, ta.key | ✅ актуален |
| `/root/s1-keys/` | ca.crt, s1-client.crt/.key, ta.key | ✅ актуален |
| `/root/.secrets/cloudflare.ini` | Cloudflare API Token | ✅ |

## Артефакты в /root на S2

| Путь | Содержимое | Актуальность |
|------|-----------|-------------|
| `/root/s1-keys/` | ca.crt, s1-client.crt/.key, ta.key | ✅ актуален (резервная копия) |

## Обновление бэкапа (рекомендуется)

```bash
# На S1 — обновить бэкап PKI
cp -r /etc/openvpn/server-easy-rsa/pki /root/vpn-infra-backup/s1/pki_$(date +%Y%m%d)

# Сохранить актуальные iptables
iptables-save > /root/vpn-infra-backup/s1/iptables_$(date +%Y%m%d).rules

# Сохранить актуальные ip rules и маршруты
ip rule list > /root/vpn-infra-backup/s1/ip-rules_$(date +%Y%m%d).txt
ip route show table all > /root/vpn-infra-backup/s1/routes_$(date +%Y%m%d).txt
```

## Важные файлы для восстановления

### Если нужно восстановить S1 с нуля:
1. PKI: `/etc/openvpn/server-easy-rsa/pki/` (содержит **приватные ключи!**)
2. TLS ключ: `/etc/openvpn/server/ta.key`
3. Клиентские ключи S2→S1: `/etc/openvpn/client/`
4. Конфиги: `/etc/openvpn/server/server.conf`, `/etc/openvpn/client/s2-client.conf`
5. CCD: `/etc/openvpn/ccd/`
6. app.py: `/opt/vpn-admin/app.py`
7. ~~MTG конфиги~~ — неактуально, MTProxy демонтирован 26.09.2026
8. Маршрутизация: `/etc/iproute2/rt_tables`, `/etc/openvpn/client/route-up.sh`
9. iptables: `/etc/iptables/rules.v4`
10. sysctl: `/etc/sysctl.conf`
