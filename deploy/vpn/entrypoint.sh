#!/bin/sh
# VPN 转发器入口：openvpn 后台建 tun，socat 前景转发 TCP。
# openvpn 死亡时终止整个容器，交给 restart 策略整体拉起。
set -eu

: "${LISTEN_PORT:=15432}"
: "${TARGET_HOST:?TARGET_HOST required}"
: "${TARGET_PORT:?TARGET_PORT required}"

openvpn --config /etc/openvpn/corp.ovpn --verb 3 &
VPN_PID=$!

# 等待 tun0 出现（最多 90 秒）；openvpn 提前退出则立即失败
i=0
until ip link show tun0 >/dev/null 2>&1; do
    if ! kill -0 "$VPN_PID" 2>/dev/null; then
        echo "[entrypoint] openvpn exited before tun was up" >&2
        exit 1
    fi
    i=$((i + 1))
    if [ "$i" -ge 90 ]; then
        echo "[entrypoint] timeout waiting for tun0" >&2
        exit 1
    fi
    sleep 1
done
echo "[entrypoint] tun0 up; forwarding 0.0.0.0:${LISTEN_PORT} -> ${TARGET_HOST}:${TARGET_PORT}"

# 看门狗：openvpn 进程消失则杀掉 PID 1（exec 后为 socat），容器退出重启
(
    while kill -0 "$VPN_PID" 2>/dev/null; do
        sleep 5
    done
    echo "[entrypoint] openvpn process died, stopping container" >&2
    kill 1 2>/dev/null || true
) &

exec socat TCP-LISTEN:"${LISTEN_PORT}",fork,reuseaddr,keepalive \
    TCP-CONNECT:"${TARGET_HOST}":"${TARGET_PORT}",connect-timeout=10
