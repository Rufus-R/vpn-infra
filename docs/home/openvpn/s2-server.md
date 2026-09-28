# OpenVPN: Сервер S2 (Европа)

## Файлы конфигурации (S2: 77.105.161.151)

```
/etc/openvpn/server/server.conf
/etc/openvpn/easy-rsa/
/etc/openvpn/easy-rsa/pki/ca.crt
/etc/openvpn/easy-rsa/pki/issued/server.crt
/etc/openvpn/easy-rsa/pki/issued/s1-client.crt
/etc/openvpn/easy-rsa/pki/private/server.key
/etc/openvpn/easy-rsa/pki/private/s1-client.key
/etc/openvpn/easy-rsa/pki/dh.pem
/etc/openvpn/ta.key
/etc/openvpn/ccd/s1-client
/etc/openvpn/ccd/DEFAULT
/etc/iptables/rules.v4
/etc/sysctl.conf
/var/log/openvpn-status.log
```

## Установка

```bash
apt update && apt install -y openvpn easy-rsa iptables-persistent
```

## PKI (Easy-RSA)

Расположение: `/etc/openvpn/easy-rsa/`

```bash
make-cadir /etc/openvpn/easy-rsa
cd /etc/openvpn/easy-rsa
./easyrsa init-pki
./easyrsa build-ca nopass
./easyrsa gen-dh
export EASYRSA_BATCH=1
./easyrsa build-server-full server nopass
./easyrsa build-client-full s1-client nopass
openvpn --genkey secret /etc/openvpn/ta.key
```

### Выданные сертификаты

| CN | Статус | Серийный |
|----|--------|---------|
| `server` | ✅ Valid | `DA75F31F76CD59D30FB95E1A5572C9CD` |
| `s1-client` | ✅ Valid | `19C331F97BD96DCF35BDD08E8B79E195` |

## Конфигурация сервера

Файл: `/etc/openvpn/server/server.conf`

```conf
port 1194
proto udp
dev tun

user nobody
group nogroup

ca /etc/openvpn/easy-rsa/pki/ca.crt
cert /etc/openvpn/easy-rsa/pki/issued/server.crt
key /etc/openvpn/easy-rsa/pki/private/server.key
dh /etc/openvpn/easy-rsa/pki/dh.pem

topology subnet
server 10.8.0.0 255.255.255.0

tls-auth /etc/openvpn/ta.key 0

client-config-dir /etc/openvpn/ccd
route 10.9.0.0 255.255.255.0
route 192.168.0.0 255.255.255.0

keepalive 10 60
persist-key
persist-tun

status /var/log/openvpn-status.log
verb 3
```

**ВАЖНО**: НЕ пушить `redirect-gateway` клиенту S1 — иначе SSH-сессия к S1 порвётся.

## CCD файлы

Файл: `/etc/openvpn/ccd/s1-client`
```
iroute 10.9.0.0 255.255.255.0
iroute 192.168.0.0 255.255.255.0
```

Файл: `/etc/openvpn/ccd/DEFAULT`
```
iroute 10.9.0.0 255.255.255.0
iroute 192.168.0.0 255.255.255.0
```

## Sysctl

Файл: `/etc/sysctl.conf`
```
net.ipv4.ip_forward=1
```

```bash
sysctl -p
```

## iptables

Файл: `/etc/iptables/rules.v4` (последнее сохранение: 06.06.2026)

```bash
# FORWARD
iptables -I FORWARD -i tun0 -o ens3 -j ACCEPT
iptables -I FORWARD -i ens3 -o tun0 -m state --state RELATED,ESTABLISHED -j ACCEPT

# INPUT — Pi-hole только через tun0
iptables -I INPUT -i tun0 -p tcp --dport 80 -j ACCEPT
iptables -I INPUT -i tun0 -p udp --dport 53 -j ACCEPT
iptables -I INPUT -i tun0 -p tcp --dport 53 -j ACCEPT
iptables -A INPUT -p udp --dport 1194 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j DROP
iptables -A INPUT -p udp --dport 53 -j DROP
iptables -A INPUT -p tcp --dport 53 -j DROP

# NAT
iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o ens3 -j MASQUERADE
iptables -t nat -A POSTROUTING -s 10.9.0.0/24 -o ens3 -j MASQUERADE

netfilter-persistent save
```

⚠️ **Известная проблема**: в `/etc/iptables/rules.v4` накопились дублированные правила.
Требуется очистка. Подробности: [../problems/known-issues.md](../problems/known-issues.md)

## Запуск

```bash
systemctl enable --now openvpn-server@server
systemctl status openvpn-server@server
```

## Статус

**✅ Работает.** S1 подключается стабильно.

Проверка подключения:
```bash
cat /var/log/openvpn-status.log
```
