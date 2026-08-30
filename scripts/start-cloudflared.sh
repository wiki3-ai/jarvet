#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${WORKSPACE_DIR}/.cloudflared.log"
PID_FILE="${WORKSPACE_DIR}/.cloudflared.pid"

if [[ -f "${WORKSPACE_DIR}/.env" ]]; then
  set -a
  source "${WORKSPACE_DIR}/.env"
  set +a
fi

if [[ -z "${TUNNEL_TOKEN:-}" ]]; then
  exit 0
fi

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" >/dev/null 2>&1; then
  exit 0
fi

nohup cloudflared tunnel --no-autoupdate run \
  >"${LOG_FILE}" 2>&1 &

echo $! >"${PID_FILE}"

for _ in {1..50}; do
  if grep -q "Registered tunnel connection" "${LOG_FILE}" 2>/dev/null; then
    exit 0
  fi
  if ! kill -0 "$(cat "${PID_FILE}")" >/dev/null 2>&1; then
    cat "${LOG_FILE}" >&2
    exit 1
  fi
  sleep 0.2
done

echo "Cloudflare Tunnel did not become ready." >&2
exit 1