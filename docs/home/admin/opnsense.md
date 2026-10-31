# OPNsense (LAN-роутер)

## Роль

OPNsense — домашний роутер, подключённый к S1 как VPN-клиент.
Даёт возможность family-клиентам получить доступ к LAN `192.168.0.0/24`.

## Параметры подключения к S1

| Параметр | Значение |
|---------|---------|
| Role | Client |
| Protocol | UDP IPv4 |
| Device mode | TUN |
| Server host | `194.55.236.229` |
| Server port | `1194` |
| Topology | subnet |
| VPN IP | `10.9.0.5` (статический, из CCD) |
| Аптайм с | 2026-07-22 01:16:21 |

## Сертификаты

| Файл | Источник |
|------|---------|
| `ca.crt` | от S1 (`/etc/openvpn/server-easy-rsa/pki/ca.crt`) |
| `OPNsense01.crt` | от S1 (`/etc/openvpn/server-easy-rsa/pki/issued/OPNsense01.crt`) |
| `OPNsense01.key` | от S1 (`/etc/openvpn/server-easy-rsa/pki/private/OPNsense01.key`) |
| `ta.key` | от S1 (`/etc/openvpn/server/ta.key`), **key-direction 1** |

Копия на S1: `/root/opnsense01/`

**Актуально на 31.10.2026:** сертификат `OPNsense01` перевыпущен (serial `5F9F0FEB…`,
прежний `195E0B58…` отозван и внесён в CRL), обновлены `ta.key` и `.ovpn`.
Готовый комплект для переноса — `/root/opnsense01-rotate/handoff/`.
Откат — `/root/opnsense01-rotate/rollback.sh`.

### Замена сертификата на роутере

Порядок обязателен: сначала S1 отзывает старый серт (CRL), потом роутер получает новый.
Иначе роутер подключается отозванным сертификатом и получает отказ.

1. System → Trust → Certificates → **Import** `ca.crt` (если ещё нет).
2. Certificates → **Import** `OPNsense01.crt` + `OPNsense01.key`.
3. VPN → OpenVPN → Clients → `VPN_S1`:
   - **Certificate** → выбрать новый `OPNsense01` (по serial, не по имени: имена совпадают);
   - **TLS Shared Secret** → вставить содержимое `ta.key` (это и есть причина обрыва
     31.10.2026 — старый `ta.key` после ротации);
   - **TLS Shared Secret Key Direction** → `1` (критично: направление 1, не 0).
4. Сохранить и **переподключить** клиент. Проверить: `vpn status` показывает `up`,
   на S1 `CLIENT_LIST` содержит `OPNsense01` с `10.9.0.5`.

## Команды: получить материал ключей с S1

Все команды выполняются **на S1**, от `root`. Приватный ключ никуда не передавать:
копировать через терминал, не через чат и не через почту.

### Вариант A: архив целиком

```bash
cd /root/opnsense01-rotate/handoff
tar tzvf opnsense01-keys.tar.gz          # проверить содержимое
sha256sum -c SHA256SUMS                  # проверить целостность
base64 -w0 opnsense01-keys.tar.gz        # получить строку для переноса
```

На своей машине сохранить строку в файл и распаковать:

```bash
base64 -d opnsense01-keys.tar.gz.b64 > opnsense01-keys.tar.gz
tar xzf opnsense01-keys.tar.gz
```

### Вариант B: по блокам, для вставки в веб-интерфейс

```bash
/root/opnsense01-rotate/handoff/show-block.sh ca     # → CA
/root/opnsense01-rotate/handoff/show-block.sh cert   # → Certificate
/root/opnsense01-rotate/handoff/show-block.sh key    # → Private key
/root/opnsense01-rotate/handoff/show-block.sh ta     # → TLS Shared Secret
```

Чтобы вывод не попал в историю shell, писать в файл и читать редактором:

```bash
umask 077
/root/opnsense01-rotate/handoff/show-block.sh ca   > /root/out-ca.txt
/root/opnsense01-rotate/handoff/show-block.sh cert > /root/out-cert.txt
/root/opnsense01-rotate/handoff/show-block.sh key  > /root/out-key.txt
/root/opnsense01-rotate/handoff/show-block.sh ta   > /root/out-ta.txt
```

### Источники файлов напрямую

| Блок | Файл на S1 | Куда вставлять |
|---|---|---|
| CA | `/etc/openvpn/server-easy-rsa/pki/ca.crt` | System → Trust → Certificates → Authorities → Import |
| Certificate | `/etc/openvpn/server-easy-rsa/pki/issued/OPNsense01.crt` | Trust → Certificates → Certificates → Import (вместе с ключом) |
| Private key | `/etc/openvpn/server-easy-rsa/pki/private/OPNsense01.key` | там же, поле Private key |
| TLS Shared Secret | `/etc/openvpn/server/ta.key` | VPN → OpenVPN → Clients → `VPN_S1` → TLS Shared Secret |

**Про `OPNsense01.crt`:** проверено — `pki/issued/OPNsense01.crt` содержит **ровно один**
блок `-----BEGIN CERTIFICATE-----` … `-----END CERTIFICATE-----`, 85 строк, без
приватного ключа. `handoff/OPNsense01.crt` — тот же блок побайтово (`diff` чистый).
Оба файла годятся для импорта; в `handoff/` просто лежит готовый комплект.

**Проверка перед вставкой:**

```bash
openssl x509 -in /root/opnsense01-rotate/handoff/OPNsense01.crt -noout -serial -dates
# ожидается: serial=5F9F0FEB3368F4D1618109C306E0770C, notAfter=Feb  2 18:19:09 2029 GMT
```

Если serial другой — взят старый или не тот файл, подключения не будет.

## Custom options

```
remote-cert-tls server;
persist-key;
persist-tun;
verb 3;
```

## Interfaces → Assignments

- Интерфейс `ovpnc1` → назван `VPN_S1`
- **Block private networks**: ВЫКЛЮЧЕНО ← важно!
- **Block bogon networks**: ВЫКЛЮЧЕНО ← важно!

## Firewall Rules на интерфейсе VPN_S1

| Действие | Протокол | Источник | Назначение |
|---------|---------|---------|-----------|
| Pass | IPv4 any | `10.9.0.0/24` | This Firewall |
| Pass | IPv4 any | `10.9.0.0/24` | LAN net |

## Outbound NAT

Режим: Hybrid/Manual

| Правило | Описание |
|---------|---------|
| `lan` | Стандартный NAT для LAN |
| `S1RU` | Translate Source IP для VPN-интерфейса |

⚠️ **Правило `S1RU` обязательно!**
Если отключить — пропадает интернет у LAN-клиентов через VPN.

## Статус

- ✅ Подключается к S1, получает `10.9.0.5`
- ✅ Интернет через VPN работает для LAN-клиентов
- ✅ Доступ family → LAN (192.168.0.0/24)


## Диагностика (shell OPNsense)

```sh
# Найти VPN-интерфейс
ifconfig | grep -B2 '10.9.0.5'

# tcpdump на VPN-интерфейсе
tcpdump -ni ovpnc1 icmp

# tcpdump на LAN-интерфейсе
tcpdump -ni <LAN_IF> icmp

# Таблица маршрутизации
netstat -rn4 | egrep '10\.9\.0|192\.168\.0'

# Правила pf
pfctl -sr | egrep -n '10\.9\.0\.0/24|reply-to'
```
