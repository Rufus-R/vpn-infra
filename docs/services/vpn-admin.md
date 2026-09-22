# VPN Admin Panel (S1)

## Файлы конфигурации (S1: 194.55.236.229)

```
/opt/vpn-admin/app.py               # Основной скрипт Flask
/opt/vpn-admin/venv/                # Python virtualenv
/opt/vpn-admin/clients/             # Генерируемые .ovpn файлы
/opt/vpn-admin/clients/Anna.ovpn
/opt/vpn-admin/clients/Mars.ovpn
/opt/vpn-admin/clients/OPNsense01.ovpn
/opt/vpn-admin/clients/Petr.ovpn
/opt/vpn-admin/clients/Serafim.ovpn
/opt/vpn-admin/clients/SET01.ovpn
/opt/vpn-admin/clients/Vova.ovpn
/etc/systemd/system/vpn-admin.service
```

## Назначение

Веб-интерфейс на Flask + Gunicorn для:
- Создания OpenVPN клиентов (friend / family / opnsense)
- Отзыва клиентов
- Скачивания `.ovpn` конфигов
- Просмотра MTProxy ссылок

## Доступ

URL: `http://10.9.0.1:8080`
Доступен **только из VPN-сетей** (`10.9.0.0/24`, `10.8.0.0/24`)

## Установка

```bash
apt install -y python3-pip python3-venv
mkdir -p /opt/vpn-admin
cd /opt/vpn-admin
python3 -m venv venv
source venv/bin/activate
pip install flask gunicorn
```

## Переменные в app.py

```python
EASYRSA = "/etc/openvpn/server-easy-rsa"
CCD     = "/etc/openvpn/ccd"
TA_KEY  = "/etc/openvpn/server/ta.key"
SERVER_IP   = "194.55.236.229"
SERVER_PORT = "1194"
MTG_DIR = "/etc/mtg"
OVPN_DIR = "/opt/vpn-admin/clients"
```

## Логика определения группы клиента

```python
group = "friend"
if os.path.isfile(ccd_path):
    ccd = open(ccd_path).read()
    if "ifconfig-push 10.9.0.5" in ccd and "iroute 192.168.0.0 255.255.255.0" in ccd:
        group = "opnsense"
    elif "# group: family" in ccd or 'push "route 192.168.0.0 255.255.255.0"' in ccd:
        group = "family"
```

## Логика создания CCD при создании клиента

```python
# friend — CCD не создаётся

# family
with open(ccd_path, "w") as f:
    f.write('push "route 192.168.0.0 255.255.255.0"\n')
# ⚠️ НЕ добавляет "# group: family" — нужно добавить вручную для Mars-совместимости

# opnsense
with open(ccd_path, "w") as f:
    f.write("ifconfig-push 10.9.0.5 255.255.255.0\n")
    f.write("iroute 192.168.0.0 255.255.255.0\n")
```

## Systemd unit

Файл: `/etc/systemd/system/vpn-admin.service`

```ini
[Unit]
Description=VPN Admin Panel
After=network.target

[Service]
WorkingDirectory=/opt/vpn-admin
ExecStart=/opt/vpn-admin/venv/bin/gunicorn -b 10.9.0.1:8080 -w 2 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now vpn-admin
systemctl status vpn-admin
```

## Управление

```bash
# Перезапуск после правок app.py
systemctl restart vpn-admin

# Логи
journalctl -u vpn-admin -n 20 --no-pager

# Gunicorn слушает на
ss -tlnup | grep 8080
# tcp  LISTEN  0  2048  10.9.0.1:8080
```

## Известные проблемы

1. **Нет аутентификации** — любой VPN-клиент может управлять другими
2. **family CCD без метки** — `create_client()` не пишет `# group: family`,
   только `push "route ..."`. Новые family-клиенты определяются корректно,
   но не через метку, а через содержимое CCD
3. **`crl-verify` не настроен** в server.conf — отозванные клиенты
   могут подключаться (см. [../openvpn/s1-server.md](../openvpn/s1-server.md))

## Статус

**✅ Работает.** Создание/отзыв/скачивание работают.
