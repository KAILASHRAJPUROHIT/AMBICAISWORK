#!/usr/bin/env bash
set -euo pipefail

SERVER2K22_PUBLIC_KEY="${1:?Usage: sudo bash aws-add-server2k22-peer.sh <SERVER2K22_PUBLIC_KEY>}"
CONFIG=/etc/wireguard/wg-rtgs.conf
KEY=/etc/wireguard/keys/aws-private.key

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
[[ -f "$KEY" ]] || { echo "Run aws-initialize.sh first." >&2; exit 1; }
[[ ! -e "$CONFIG" ]] || { echo "$CONFIG already exists; inspect it before replacing it." >&2; exit 1; }

umask 077
cat > "$CONFIG" <<EOF
[Interface]
Address = 10.241.77.1/24
ListenPort = 51820
PrivateKey = $(cat "$KEY")
# Keep the SMB client source inside the tunnel address space. Server2k22 only
# accepts TCP/445 from 10.241.77.1, and no LAN port is exposed publicly.
PostUp = iptables -t nat -A POSTROUTING -o %i -d 192.168.0.100/32 -p tcp --dport 445 -j SNAT --to-source 10.241.77.1
PostDown = iptables -t nat -D POSTROUTING -o %i -d 192.168.0.100/32 -p tcp --dport 445 -j SNAT --to-source 10.241.77.1

[Peer]
PublicKey = $SERVER2K22_PUBLIC_KEY
AllowedIPs = 10.241.77.2/32, 192.168.0.100/32
EOF

chmod 600 "$CONFIG"
systemctl enable --now wg-quick@wg-rtgs
wg show wg-rtgs
