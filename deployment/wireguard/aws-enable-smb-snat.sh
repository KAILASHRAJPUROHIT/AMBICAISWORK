#!/usr/bin/env bash
set -euo pipefail

CONFIG=/etc/wireguard/wg-rtgs.conf
RULE='iptables -t nat -A POSTROUTING -o %i -d 192.168.0.100/32 -p tcp --dport 445 -j SNAT --to-source 10.241.77.1'
UNDO='iptables -t nat -D POSTROUTING -o %i -d 192.168.0.100/32 -p tcp --dport 445 -j SNAT --to-source 10.241.77.1'

if [[ $EUID -ne 0 ]]; then
  echo 'Run with sudo.' >&2
  exit 1
fi

[[ -f "$CONFIG" ]] || { echo "Missing $CONFIG" >&2; exit 1; }

if ! grep -Fqx "PostUp = $RULE" "$CONFIG"; then
  backup="$CONFIG.bak.$(date +%Y%m%d%H%M%S)"
  cp "$CONFIG" "$backup"
  sed -i "/^PrivateKey =/a PostUp = $RULE\nPostDown = $UNDO" "$CONFIG"
  chmod 600 "$CONFIG"
fi

systemctl restart wg-quick@wg-rtgs
wg show wg-rtgs
iptables -t nat -S POSTROUTING | grep -- '--dport 445' || true
