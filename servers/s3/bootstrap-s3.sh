#!/usr/bin/env bash
# Bootstrap S3 — relay/exit нода коммерческого проекта (аварийная замена S2 29.10.2026).
# Запуск: НА S3, от root: bash bootstrap-s3.sh <IP_S_RU> [PANEL_IP]
# Делает: ufw, сертификат (IP SAN, self-signed), xray (_release из GitHub), конфиг relay-инбаунда.
# НЕ делает: ничего на других серверах. Переключение S_RU — отдельным шагом (см. runbook).
set -euo pipefail

SRU_IP="${1:?usage: bash bootstrap-s3.sh <IP_S_RU> [PANEL_IP]}"
PANEL_IP="${2:-31.77.78.144}"

# TUNING (можно переопределить переменными окружения)
S3_IP="${S3_IP:-$(curl -4 -s --max-time 10 ifconfig.me)}"
RELAY_PORT="${RELAY_PORT:-10001}"
TG_PROXY_PORT="${TG_PROXY_PORT:-38417}"
UUID="${UUID:-$(cat /run/relay_uuid 2>/dev/null || python3 -c 'import uuid;print(uuid.uuid4())')}"

[[ "$S3_IP" =~ ^[0-9.]+$ ]] || { echo "FATAL: не удалось определить публичный IP"; exit 1; }
echo "== S3 bootstrap: ip=$S3_IP sru=$SRU_IP panel=$PANEL_IP relay_port=$RELAY_PORT =="
mkdir -p /run
echo "$UUID" > /run/relay_uuid

mkdir -p /root/.ssh && chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys
# Стандартный набор ключей оператора (источник: S1 /root/.ssh/authorized_keys, 29.10.2026)
for KEY in \
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEt9WsfaEKRqslAyAYzY7wj8bZM0kkoOxF3R89ATttA3 termux-admin' \
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIASm8qbeXUsADI53gUB2Re00gHP/j6XhmYf9pWMrMHC9 242SRIG-admin' \
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEYCFTMsi2J9QQ7ib7vK735AWucgXWTO6wZhg1tBx0qS s1-servers' \
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMpOg/RfxRvRiO2kdWj4+bZlRA3LhUO+CuPP0i1GsaSo ai-agent@openhands-500'; do
  grep -qF "${KEY#ssh-ed25519 }" /root/.ssh/authorized_keys || echo "$KEY" >> /root/.ssh/authorized_keys
done
echo "authorized_keys:"; cat /root/.ssh/authorized_keys

# --- 1. Базовые пакеты ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ufw curl jq openssl qrencode python3 iptables unzip >/dev/null

# --- 1a. Preflight: виртуализация и ограничения (важно для OpenVZ/LXC) ---
VIRT="$(systemd-detect-virt 2>/dev/null || echo unknown)"
echo "virt: ${VIRT}"
case "${VIRT}" in
  openvz|lxc)
    echo "WARN: контейнерная виртуализация (${VIRT}). Проверяю ограничения..."
    if ! iptables -A INPUT -p tcp --dport 65534 -j ACCEPT 2>/dev/null \
       || ! iptables -D INPUT -p tcp --dport 65534 -j ACCEPT 2>/dev/null; then
      echo "FATAL: iptables-модули на хосте не разрешены контейнеру — ufw работать не будет."
      echo "Решение: попросить провайдера включить netfilter-модули или взять тариф KVM."
      exit 1
    fi
    if [[ ! -c /dev/net/tun ]]; then
      echo "WARN: /dev/net/tun отсутствует — OpenVPN (домашний туннель) на этом VPS работать не будет."
      echo "Для роли relay/exit это не мешает. Для TUN попросите провайдера включить TUN/TAP."
    fi
    ;;
esac

# --- 2. ufw: зеркало S2 (порты/комментарии из docs/shared/networking/iptables-s2.md) ---
ufw default deny incoming
ufw default allow outgoing
ufw default deny routed
ufw --force reset >/dev/null
ufw allow 22/tcp  comment 'SSH'
ufw allow 80/tcp  comment 'ACME HTTP-01 (3x-ui)'
ufw allow from "$SRU_IP"   to any port "${RELAY_PORT}" proto tcp comment "relay from S_RU (${SRU_IP})"
ufw allow from 194.55.236.229 to any port "${RELAY_PORT}" proto tcp comment 'relay from S1'
ufw allow from 194.55.236.229 to any port 25307 proto tcp comment '3x-ui node: S1'
ufw allow from "$PANEL_IP" to any port 25307 proto tcp comment '3x-ui node: Panel master'
ufw allow from 46.32.82.242   to any port 25307 proto tcp comment '3x-ui node: operator'
ufw allow from 10.8.0.0/24    to any port 25307 proto tcp comment '3x-ui node: VPN'
ufw allow from "$PANEL_IP"   to any port 38417 proto tcp comment 'tg-proxy from Panel'
# FWD-правила и tun0 — добавлять вручную при развёртывании OpenVPN (см. runbook, не нужно для relay-роли)
ufw --force enable
ufw status numbered

# --- 3. Сертификат: IP SAN, self-signed (10 лет), зеркало подхода S2 (/etc/x-ui/certs) ---
mkdir -p /etc/xray/certs
openssl req -new -newkey rsa:2048 -days 3650 -nodes -x509 -subj "/CN=${S3_IP}" \
  -addext "subjectAltName=IP:${S3_IP}" \
  -keyout /etc/xray/certs/server.key -out /etc/xray/certs/server.crt 2>/dev/null
chmod 600 /etc/xray/certs/server.key

# --- 4. Xray (_release, без установки x-ui на S3 — конфиг и сервис ставим руками) ---
XRAY_VER="${XRAY_VER:-v26.10.21}"   # == версия на S2/S_RU; latest см. api.github.com
mkdir -p /usr/local/xray /etc/xray
curl -fsSL --retry 3 -o /tmp/xray.tgz \
  "https://github.com/XTLS/Xray-core/releases/download/${XRAY_VER}/Xray-linux-64.zip"
apt-get install -y -qq unzip >/dev/null
unzip -o /tmp/xray.tgz -d /usr/local/xray xray geoip.dat geosite.dat >/dev/null
chmod +x /usr/local/xray/xray
rm -f /tmp/xray.tgz

# --- 5. Конфиг relay-инбаунда (шаблон из репо: servers/s3/relay-node/) ---
# Шаблон содержит и socks5 tg-proxy (38417) для Telegram-бота Panel:
# подставляем учётные данные (генерируются вместе с UUID), выводим в финале.
python3 - "$S3_IP" <<PYEOF
import json, sys
s3_ip = sys.argv[1]
tpl_path = "/root/xray-config-template.json"
cfg = json.load(open(tpl_path))
tg_user, tg_pass = None, None
for inb in cfg["inbounds"]:
    if inb.get("tag") == "in-10001-tcp":
        inb["settings"]["clients"][0]["id"] = "$UUID"
        tls = inb["streamSettings"]["tlsSettings"]["certificates"][0]
        tls["certificateFile"] = "/etc/xray/certs/server.crt"
        tls["keyFile"] = "/etc/xray/certs/server.key"
    if inb.get("tag") == "in-38417-socks":
        acc = inb["settings"]["accounts"][0]
        tg_user, tg_pass = acc["user"], acc["pass"]
        if "PLACEHOLDER" in tg_user or "PLACEHOLDER" in tg_pass:
            import secrets
            tg_user = secrets.token_hex(6)
            tg_pass = secrets.token_hex(8)
            acc["user"], acc["pass"] = tg_user, tg_pass
with open("/etc/xray/config.json", "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
if tg_user and "PLACEHOLDER" not in (tg_user or ""):
    with open("/run/tgproxy_creds", "w") as f:
        f.write(f"{tg_user}:{tg_pass}\n")
PYEOF

# --- 6. systemd unit ---
cat > /etc/systemd/system/xray-relay.service <<'EOF'
[Unit]
Description=Xray relay node (S3)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/xray/xray run -c /etc/xray/config.json
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now xray-relay
sleep 2
systemctl is-active xray-relay

# --- 7. Проверки (read-only) ---
echo "== проверки =="
ss -tlnp | grep ":${RELAY_PORT}" || { echo "FATAL: ${RELAY_PORT} не слушается"; exit 1; }
timeout 3 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/${RELAY_PORT}" && echo "local ${RELAY_PORT} OK"
ss -tlnp | grep ":${TG_PROXY_PORT}" || { echo "FATAL: ${TG_PROXY_PORT} не слушается"; exit 1; }
timeout 3 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/${TG_PROXY_PORT}" && echo "local ${TG_PROXY_PORT} (tg-proxy) OK"

# --- 8. Вывод данных для переключения S_RU ---
echo
echo "=========== ДАННЫЕ ДЛЯ ПЕРЕКЛЮЧЕНИЯ S_RU (сохранить) ==========="
echo "S3_IP=${S3_IP}"
echo "S3_RELAY_PORT=${RELAY_PORT}"
echo "S3_RELAY_UUID=${UUID}"
echo "S3_TG_PROXY=socks5://<user>:<pass>@${S3_IP}:${TG_PROXY_PORT}"
echo "  (учётные данные в /run/tgproxy_creds на S3; прописать в .env бота TG_PROXY_URL)"
echo "S_RU outbound to-s2-relay: address=${S3_IP}, port=${RELAY_PORT}"
echo "  tlsSettings serverName='' (пусто), allowInsecure=1 (IP-серт, как на S2)"
echo "=================================================================="
qrencode -t ANSIUTF8 "vless://${UUID}@${S3_IP}:${RELAY_PORT}?encryption=none&security=tls&sni=&allowInsecure=1&type=tcp&alpn=h2,http/1.1#relay-s3" 2>/dev/null || true
echo "Готово. Дальше — runbook: servers/s3/relay-node/runbook-s3.md, шаг 4."
