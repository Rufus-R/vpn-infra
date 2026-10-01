# Pi-hole (S2)

## Установка

Нативная установка (НЕ Docker), пакет `pihole-meta 0.7`

```bash
curl -sSL https://install.pi-hole.net | bash
```

## Файлы конфигурации (S2: 77.105.161.151)

```
/etc/cron.d/pihole              # Cron задачи Pi-hole
/var/log/pihole/                # Логи
```

## Порты (проверено 01.10.2026)

| Порт | Протокол | Bind | Защита (ufw на S2) |
|------|----------|------|--------------------|
| 53 | TCP/UDP | `0.0.0.0`, `[::]` | только `10.8.0.0/24` (tun0) |
| 8080 | TCP | `0.0.0.0` | веб-админка: `10.8.0.0/24`, `10.9.0.0/24`, `192.168.0.0/24` |
| 123 | UDP | — | слушает (NTP Pi-hole), снаружи закрыт default deny; можно отключить |

Порты 80 и 443 на S2 свободны: веб Pi-hole перенесён на 8080, HTTPS отключён (01.10.2026).
Порт 80 оставлен открытым под ACME (acme.sh / x-ui).

⚠️ **Pi-hole по-прежнему слушает на всех интерфейсах, включая `ens3`.**
Защита — только firewall `ufw` (default deny incoming). Любое отключение ufw
делает Pi-hole open resolver и открытым web-сервером. Правила и история:
[../../shared/networking/iptables-s2.md](../../shared/networking/iptables-s2.md),
порты: [../../shared/reference/ports.md](../../shared/reference/ports.md).

## Доступ

- Web-интерфейс: `http://10.8.0.1:8080/admin/login`
- DNS: `10.8.0.1:53`
- Доступно **только через туннель**; снаружи (`77.105.161.151`) закрыто ufw

## Диагностика

```bash
# На S2
ss -tlnup | grep pihole
systemctl status pihole-FTL
pihole status
ufw status numbered

# Проверка доступности с S1 (через тоннель)
curl -I http://10.8.0.1:8080/admin/login
dig @10.8.0.1 google.com
```

## Статус

**✅ Работает.** DNS и web-интерфейс (8080) доступны через тоннель (проверено 01.10.2026).
