# S3 — relay/exit нода (аварийная замена S2)

Инцидент 29.10.2026: у S2 заблокирован входящий трафик на уровне сети
провайдера. S3 — замена exit-роли для коммерческого канала.
Runbook и архитектура: `servers/s3/relay-node/runbook-s3.md`.

## Состав

- `bootstrap-s3.sh` — bootstrap НА S3: ufw (зеркало S2), IP-серт,
  Xray `_release` (GitHub), relay-инбаунд `in-10001-tcp` (VLESS+TLS),
  systemd-юнит `xray-relay`, проверки.
- `relay-node/xray-config-template.json` — шаблон конфига Xray
  (зеркало рабочего конфига S2, uuid подставляется скриптом).

## Запуск

```bash
# скопировать на S3 (с S1):
scp servers/s3/bootstrap-s3.sh servers/s3/relay-node/xray-config-template.json root@IP_S3:/root/
# выполнить на S3:
bash /root/bootstrap-s3.sh 31.77.169.67 31.77.78.144
```

В конце печатает блок «ДАННЫЕ ДЛЯ ПЕРЕКЛЮЧЕНИЯ S_RU» (uuid, IP:порт) —
сохранить. Переключение S_RU — вручную через мастер-панель (runbook, шаг 4).
