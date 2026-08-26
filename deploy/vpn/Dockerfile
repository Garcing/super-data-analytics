FROM alpine:3.20

# openvpn: 建隧道；socat: TCP 转发；iproute2: entrypoint 检测 tun0
RUN apk add --no-cache openvpn socat iproute2

COPY corp.ovpn /etc/openvpn/corp.ovpn
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
