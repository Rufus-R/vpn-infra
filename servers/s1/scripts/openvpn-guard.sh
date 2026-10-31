#!/bin/bash
# Сторож маршрутов OpenVPN на S1.
#
# Страхует от аварии 31.10.2026: конфиг сервера увёл весь egress S1 в туннель
# (route 0.0.0.0 0.0.0.0 -> 0.0.0.0/1 + 128.0.0.0/1), SSH перестал отвечать.
#
# Правило: любое изменение конфига OpenVPN на S1 считается НЕПОДТВЕРЖДЁННЫМ, пока
# оператор явно не выполнил `openvpn-guard.sh confirm`. Пока подтверждения нет,
# сторож при каждом запуске таймера проверяет главную таблицу и снимает маршруты-угона.
#
# Команды:
#   openvpn-guard.sh check     — одна проверка (вызывается таймером)
#   openvpn-guard.sh confirm   — подтвердить текущий конфиг (снять сторожа)
#   openvpn-guard.sh revoke    — снять подтверждение (снова взвести сторожа)
#   openvpn-guard.sh status    — показать состояние
#
# Юниты OpenVPN остаются в автозагрузке: сторож не отменяет автозапуск, а откатывает
# небезопасное состояние. Автозапуск нужен, чтобы S1 возвращался после ребута
# (проверено 31.10.2026).

GUARD_DIR=/etc/openvpn-guard
CONFIRMED=$GUARD_DIR/confirmed
COUNT=$GUARD_DIR/hijack-count
LOG=/var/log/openvpn-guard.log
SUSPECT_UNIT=openvpn-server@home-s3
HIJACK_LIMIT=3

log() {
    echo "$(date -Is) $*" >> "$LOG"
}

hijack_routes() {
    ip route show table main | grep -E '^0\.0\.0\.0/1|^128\.0\.0\.0/1'
}

do_check() {
    mkdir -p "$GUARD_DIR"
    [ -f "$LOG" ] || touch "$LOG"

    [ -f "$CONFIRMED" ] && return 0

    local routes n
    routes=$(hijack_routes)
    [ -z "$routes" ] && return 0

    log "WARN hijack routes without confirmation: $(echo "$routes" | tr '\n' ' ')"

    n=0
    [ -f "$COUNT" ] && n=$(cat "$COUNT" 2>/dev/null || echo 0)
    n=$((n + 1))
    echo "$n" > "$COUNT"

    ip route del 0.0.0.0/1 2>/dev/null || true
    ip route del 128.0.0.0/1 2>/dev/null || true
    log "ROLLBACK hijack routes removed (attempt $n)"

    if [ "$n" -ge "$HIJACK_LIMIT" ]; then
        log "CRITICAL hijack re-added $n times, stopping $SUSPECT_UNIT"
        systemctl stop "$SUSPECT_UNIT" 2>/dev/null || true
    fi

    if hijack_routes | grep -q .; then
        log "ERROR rollback did not clean main table"
        return 1
    fi
    return 0
}

case "${1:-check}" in
    check)
        do_check
        ;;
    confirm)
        mkdir -p "$GUARD_DIR"
        date -Is > "$CONFIRMED"
        rm -f "$COUNT"
        log "CONFIRMED current config accepted by operator"
        echo "confirmed"
        ;;
    revoke)
        rm -f "$CONFIRMED" "$COUNT"
        log "REVOKED confirmation cleared, guard armed"
        echo "armed"
        ;;
    status)
        if [ -f "$CONFIRMED" ]; then
            echo "state: confirmed ($(cat "$CONFIRMED"))"
        else
            echo "state: armed (rollback on hijack routes)"
        fi
        if ip route show table main | grep -qE '^0\.0\.0\.0/1|^128\.0\.0\.0/1'; then
            echo "hijack-routes: present"
        else
            echo "hijack-routes: none"
        fi
        [ -f "$COUNT" ] && echo "hijack-attempts: $(cat "$COUNT")"
        tail -3 "$LOG" 2>/dev/null || true
        ;;
    *)
        echo "usage: $0 {check|confirm|revoke|status}" >&2
        exit 2
        ;;
esac
