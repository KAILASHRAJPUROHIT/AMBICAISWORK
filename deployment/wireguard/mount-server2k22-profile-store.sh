#!/usr/bin/env bash
set -euo pipefail

MOUNT_ROOT=/mnt/server2k22-d
TARGET="$MOUNT_ROOT/AradhanaPaymentAuditor"
CREDENTIALS=/etc/samba/credentials/server2k22-rtgs

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
[[ -f "$CREDENTIALS" ]] || { echo "Create $CREDENTIALS first (mode 600)." >&2; exit 1; }
ping -c 1 -W 3 10.241.77.2 >/dev/null
nc -zvw 5 192.168.0.100 445

apt-get update
apt-get install -y cifs-utils
install -d -m 700 "$MOUNT_ROOT"

if ! mountpoint -q "$MOUNT_ROOT"; then
  mount -t cifs //192.168.0.100/D "$MOUNT_ROOT" \
    -o "credentials=$CREDENTIALS,vers=3.1.1,seal,uid=10003,gid=10003,dir_mode=0700,file_mode=0600,noserverino"
fi
install -d -m 700 "$TARGET"
touch "$TARGET/.rtgs-profile-store-write-test"
rm "$TARGET/.rtgs-profile-store-write-test"
echo "Mounted and write-tested: $TARGET"
