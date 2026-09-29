#!/usr/bin/env bash
set -euo pipefail

CONFIG=/etc/wireguard/wg-rtgs.conf
RULE='iptables -t nat -D POSTROUTING -o wg-rtgs -d 192.168.0.100/32 -p tcp --dport 445 -j SNAT --to-source 10.241.77.1'

if [[ $EUID -ne 0 ]]; then
  echo 'Run with sudo.' >&2
  exit 1
fi

[[ -f "$CONFIG" ]] || { echo "Missing $CONFIG" >&2; exit 1; }

# The direct WireGuard SMB address is safer and avoids dependence on the LAN IP.
sed -i '/^PostUp = iptables -t nat -A POSTROUTING -o %i -d 192\.168\.0\.100\/32 -p tcp --dport 445 -j SNAT --to-source 10\.241\.77\.1$/d' "$CONFIG"
sed -i '/^PostDown = iptables -t nat -D POSTROUTING -o %i -d 192\.168\.0\.100\/32 -p tcp --dport 445 -j SNAT --to-source 10\.241\.77\.1$/d' "$CONFIG"
sed -i 's/, 192\.168\.0\.100\/32//' "$CONFIG"

while iptables -t nat -C POSTROUTING -o wg-rtgs -d 192.168.0.100/32 -p tcp --dport 445 -j SNAT --to-source 10.241.77.1 2>/dev/null; do
  $RULE
done

systemctl restart wg-quick@wg-rtgs
wg show wg-rtgs
nc -zvw 5 10.241.77.2 445
