#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR=/etc/wireguard
KEY_DIR=/etc/wireguard/keys
PRIVATE_KEY="$KEY_DIR/aws-private.key"
PUBLIC_KEY="$KEY_DIR/aws-public.key"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

apt-get update
apt-get install -y wireguard
install -d -m 700 "$KEY_DIR"

if [[ ! -f "$PRIVATE_KEY" ]]; then
  umask 077
  wg genkey > "$PRIVATE_KEY"
  wg pubkey < "$PRIVATE_KEY" > "$PUBLIC_KEY"
fi

echo "AWS WireGuard public key:"
cat "$PUBLIC_KEY"
echo
echo "Next: configure Server2k22 using this public key and the AWS public IPv4/DNS endpoint."
