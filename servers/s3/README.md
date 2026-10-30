# S3 — exit-нода + нода мастер-панели

Инцидент 29.10.2026: у S2 заблокирован входящий трафик на уровне сети
провайдера. S3 — замена exit-роли для коммерческого канала.
30.10.2026: DPI начал резать Reality-хендшейк на входе S_RU:443 → подтверждённый pivot
«клиенты ходят напрямую на S3». На S3 поднята **нода 3x-ui v3.11.0** (порт панели 25307),
которая обслуживает оба инбаунда вместо отдельного `xray-relay`.

Ключевые документы:
- `docs/checkpoint-2026-10-30-s3-node-master-panel.md` — сессия «нода на S3»: схема БД
  клиентов, грабли, E2E, порядок регистрации в мастере;
- `relay-node/runbook-s3.md` — исходная архитектура relay (историческая база);
- `docs/shared/reference/ports.md` — актуальные порты S3.

## Состав (с 30.10.2026)

| Что | Где |
|---|---|
| Панель ноды | `https://195.242.118.2:25307/4kNbpfhH09XSfBMt0D/` (self-signed, 10 лет) |
| БД | `/etc/x-ui/x-ui.db` |
| Серты | `/etc/x-ui/certs/server.{crt,key}` (пин `76145d04…6eef0`) |
| Инбаунды | `in-10001-tcp` (VLESS+TLS, 10001, 10 клиентов), `in-38417-socks` (socks+пароль, 38417) |
| Токен API для мастера | `/root/show-node-token.sh` (имя токена `Panel`) |
| Бэкапы | `/root/x-ui.db.bak-20261030-pre-master-sync`, `/root/xray-config.json.bak-20261030-pre-tgproxy` |

`xray-relay.service` остановлен и disabled: порты обслуживает xray под управлением x-ui.
Исторические файлы `bootstrap-s3.sh` и `relay-node/xray-config-template.json` описывают
прежнюю схему (чистый Xray без панели) — актуальны только как референс конфига.

## Регистрация ноды в мастере

1. Panel → Nodes → Add Node.
2. `https` / `195.242.118.2` / `25307` / basePath `/4kNbpfhH09XSfBMt0D/`.
3. **TLS Verify Mode = `pin`**, нажать Fetch (или вставить `76145d04…6eef0`).
   Дефолтный `verify` на self-signed серте даёт
   `x509: certificate signed by unknown authority`.
4. API Token — вывод `/root/show-node-token.sh` на S3 (значение не публиковать).
5. Inbound sync = `all`, Outbound tag — пусто. Test Connection → `online` → Save.

После Save мастер **усыновляет** совместимые инбаунды ноды и с этого момента пушит
конфиг: правки в БД ноды будут перезаписаны. Привязка клиентов к exit-ветке — в мастере.

## Запуск/проверка

```bash
systemctl status x-ui                # должно быть active
ss -tlnp | grep -E ':10001|:38417|:25307'
python3 -c 'import json;c=json.load(open("/usr/local/x-ui/bin/config.json"));print([(i["tag"],len(i.get("settings",{}).get("clients",[]))) for i in c["inbounds"]])'
```

E2E с S1 (публичный путь):

```bash
curl -x socks5h://127.0.0.1:<local-socks> -s -w " http=%{http_code}\n" http://ip-api.com/line/?fields=query
# ожидается 195.242.118.2 / http=200
```
