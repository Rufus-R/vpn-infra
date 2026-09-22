# ✅ РЕШЕНО (03.08.2026): Family → LAN доступ

## Статус: РЕШЕНО

`ping 192.168.0.1` и `ping 192.168.0.10` с S1 — 0% packet loss.
Доступ family-клиентов к LAN через OPNsense работает.

---

## Корневая причина

В CCD файле `/etc/openvpn/ccd/OPNsense01` была директива `push-reset`,
которая сбрасывала **все** глобальные push-опции сервера,
включая `topology subnet`.

OPNsense получал в PUSH_REPLY только:
```
ifconfig 10.9.0.5 255.255.255.0
```

Без `topology subnet` OpenVPN клиент интерпретирует два параметра
`ifconfig` в старом стиле **net30 (point-to-point)**:
- первый параметр = свой адрес
- второй параметр = адрес "пира" (peer)

В результате на OPNsense интерфейс выглядел так:
```
inet 10.9.0.5 --> 255.255.255.0 netmask 0xffffffff
```

Что должно было быть (topology subnet):
```
inet 10.9.0.5 netmask 0xffffff00 broadcast 10.9.0.255
```

На основе кривого интерфейса pf генерировал правило:
```
reply-to (ovpnc1 255.255.255.0)
```

`255.255.255.0` — это невалидный gateway (это маска, а не IP).
Поэтому ответные пакеты от OPNsense уходили в никуда.

## Исправление

Файл: `/etc/openvpn/ccd/OPNsense01`

**Было:**
```
ifconfig-push 10.9.0.5 255.255.255.0
iroute 192.168.0.0 255.255.255.0
push-reset
```

**Стало:**
```
ifconfig-push 10.9.0.5 255.255.255.0
iroute 192.168.0.0 255.255.255.0
push-reset
push "topology subnet"
push "route-gateway 10.9.0.1"
```

После рестарта `openvpn-server@server` на S1 и реконнекта OPNsense
интерфейс принял правильный вид, pf перегенерировал правила корректно.

## Правило: push-reset требует явного восстановления topology

Если в CCD используется `push-reset` — **всегда** нужно явно добавить:
```
push "topology subnet"
push "route-gateway <tun_ip>"
```
Иначе клиент откатится на net30 и получит некорректный интерфейс.

## Диагностика (хронология)

| Шаг | Наблюдение |
|-----|-----------|
| tcpdump tun1 на S1 | Пакеты уходят к 10.9.0.5, ответа нет |
| tcpdump ovpnc1 на OPNsense | Пакеты приходят, ответа нет |
| pfctl -sr -i ovpnc1 | `reply-to (ovpnc1 255.255.255.0)` — невалидный gateway |
| ifconfig на OPNsense | `inet 10.9.0.5 --> 255.255.255.0` — net30 вместо subnet |
| PUSH_REPLY в журнале S1 | Нет `topology subnet` у OPNsense01, есть у Mars/Petr |
| Конфиг клиента OPNsense | Нет `topology` — ждёт от сервера |
| CCD OPNsense01 | `push-reset` без явного `push "topology subnet"` |
