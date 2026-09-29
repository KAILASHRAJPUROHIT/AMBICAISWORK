#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo 'Run with sudo.' >&2
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_PATH=/usr/local/sbin/ambic-mount-rtgs-profile-store
UNIT=/etc/systemd/system/ambic-rtgs-profile-store.service

install -m 700 "$SOURCE_DIR/mount-server2k22-profile-store.sh" "$INSTALL_PATH"

cat >"$UNIT" <<'UNIT'
[Unit]
Description=AMBIC RTGS profile store mount over WireGuard
Wants=network-online.target
After=network-online.target wg-quick@wg-rtgs.service
Requires=wg-quick@wg-rtgs.service
Before=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/ambic-mount-rtgs-profile-store
ExecStop=/usr/bin/umount /mnt/server2k22-d

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now ambic-rtgs-profile-store.service
systemctl is-active --quiet ambic-rtgs-profile-store.service
echo 'Persistent RTGS profile-store mount is active.'
