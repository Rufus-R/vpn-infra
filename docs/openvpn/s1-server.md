# OpenVPN: Сервер S1 для клиентов

## Файлы конфигурации (S1: 194.55.236.229)

```
/etc/openvpn/server/server.conf
/etc/openvpn/server/ta.key
/etc/openvpn/server-easy-rsa/                       # PKI (симлинки на /usr/share/easy-rsa/)
/etc/openvpn/server-easy-rsa/easyrsa                # → /usr/share/easy-rsa/easyrsa
/etc/openvpn/server-easy-rsa/vars
/etc/openvpn/server-easy-rsa/pki/ca.crt
/etc/openvpn/server-easy-rsa/pki/dh.pem
/etc/openvpn/server-easy-rsa/pki/crl.pem            # CRL (генерируется при отзыве)
/etc/openvpn/server-easy-rsa/pki/index.txt          # База сертификатов
/etc/openvpn/server-easy-rsa/pki/issued/            # Выданные сертификаты
/etc/openvpn/server-easy-rsa/pki/private/           # Приватные ключи
/etc/openvpn/server-easy-rsa/pki/inline/            # Inline конфиги (.ovpn)
/etc/openvpn/server-easy-rsa/pki/revoked/           # Отозванные
/etc/openvpn/ccd/                                   # Client Config Dir
/var/log/openvpn-status-tun1.log
```

## PKI

Расположение: `/etc/openvpn/server-easy-rsa/`
**Отдельный PKI от S2!**

```bash
make-cadir /etc/openvpn/server-easy-rsa
cd /etc/openvpn/server-easy-rsa
./easyrsa init-pki
./easyrsa build-ca nopass
export EASYRSA_BATCH=1
./easyrsa build-server-full server nopass
./easyrsa gen-dh
openvpn --genkey secret /etc/openvpn/server/ta.key
```

### Добавление нового клиента вручную:
```bash
cd /etc/openvpn/server-easy-rsa
export EASYRSA_BATCH=1
./easyrsa build-client-full <name> nopass
```

### Отзыв сертификата:
```bash
cd /etc/openvpn/server-easy-rsa
export EASYRSA_BATCH=1
./easyrsa revoke <name>
./easyrsa gen-crl
```

## Конфигурация сервера

Файл: `/etc/openvpn/server/server.conf`

```conf
port 1194
proto udp
dev tun1

ca /etc/openvpn/server-easy-rsa/pki/ca.crt
cert /etc/openvpn/server-easy-rsa/pki/issued/server.crt
key /etc/openvpn/server-easy-rsa/pki/private/server.key
dh /etc/openvpn/server-easy-rsa/pki/dh.pem
tls-auth /etc/openvpn/server/ta.key 0

topology subnet
server 10.9.0.0 255.255.255.0

client-config-dir /etc/openvpn/ccd
route 192.168.0.0 255.255.255.0

client-to-client

push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS 10.8.0.1"
push "route 192.168.0.0 255.255.255.0"

keepalive 10 60
persist-key
persist-tun
status /var/log/openvpn-status-tun1.log
verb 3
crl-verify /etc/openvpn/server-easy-rsa/pki/crl.pem
```

✅ **crl-verify настроен** (строка 31 в `server.conf`, подтверждено
26.09.2026): `crl-verify /etc/openvpn/server-easy-rsa/pki/crl.pem`.
Каждый запуск сервиса подтверждает загрузку CRL в логах:
`journalctl -u openvpn-server@server | grep -i crl` →
`CRL: loaded 1 CRLs from file /etc/openvpn/server-easy-rsa/pki/crl.pem`.
Отозванные клиенты (friend1, SET, Nikita, старый сертификат Vova от
05.08.2026) не могут подключиться.

Отзыв сертификата обновляет CRL немедленно (`easyrsa gen-crl`), но
файл `crl.pem` перечитывается OpenVPN только при перезапуске сервиса
или по истечении внутреннего кэша — при массовом/срочном отзыве
рекомендуется `systemctl restart openvpn-server@server` для
гарантии.

## Запуск

```bash
systemctl enable --now openvpn-server@server
systemctl status openvpn-server@server
```

## Проверка статуса клиентов

```bash
cat /var/log/openvpn-status-tun1.log
```

Пример вывода:
```
CLIENT_LIST,Petr,31.134.187.32:1385,10.9.0.2,...
CLIENT_LIST,OPNsense01,46.32.82.242:8729,10.9.0.5,...
ROUTING_TABLE,192.168.0.0/24,OPNsense01,...
```

## Статус

**✅ Работает.** Клиенты подключаются, интернет через S2 работает.

**✅ crl-verify настроен и подтверждён рабочим** — см. выше.
