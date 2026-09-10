#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
test -f .env || { echo "Missing deployment/aws/.env. Copy .env.example and set secrets on the VM." >&2; exit 1; }

set -a
. ./.env
set +a

sudo install -d -m 0750 -o 10001 -g 10001 "${AIS_DATA_DIR:-/srv/aradhana-print/data}"
docker compose pull --ignore-buildable
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
curl --fail --silent --show-error "http://127.0.0.1:${AIS_BIND_PORT:-8000}/health"
