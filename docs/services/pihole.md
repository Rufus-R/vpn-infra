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

## Порты

| Порт | Протокол | Bind | Защита |
|------|----------|------|--------|
| 53 | TCP/UDP | `0.0.0.0` | iptables: только `tun0` |
| 80 | TCP | `0.0.0.0` | iptables: только `tun0` |
| 443 | TCP | `0.0.0.0` | ⚠️ НЕ заблокирован в iptables |
| 123 | UDP | `0.0.0.0` | ⚠️ НЕ заблокирован в iptables |

⚠️ **Pi-hole слушает на всех интерфейсах включая `ens3`!**
Защита обеспечивается только iptables. При сбросе iptables Pi-hole
станет open resolver и открытым web-сервером.

Рекомендуется добавить блокировку:
```bash
iptables -A INPUT -i tun0 -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j DROP
iptables -A INPUT -p udp --dport 123 -j DROP
netfilter-persistent save
```

## Доступ

- Web-интерфейс: `http://10.8.0.1/admin/login`
- DNS: `10.8.0.1:53`
- Доступно **ТОЛЬКО через туннель** (из сети `10.8.0.0/24`)
- Снаружи (`77.105.161.151`) — заблокировано iptables

## Диагностика

```bash
# На S2
ss -tlnup | grep pihole
systemctl status pihole-FTL
pihole status

# Проверка доступности с S1 (через тоннель)
curl -I http://10.8.0.1/admin/login
```

## Статус

**✅ Работает.** DNS работает, web-интерфейс доступен через тоннель.
