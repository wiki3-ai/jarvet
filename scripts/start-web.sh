#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${WORKSPACE_DIR}/.venv"
LOG_FILE="${WORKSPACE_DIR}/.jarvet.log"
PID_FILE="${WORKSPACE_DIR}/.jarvet.pid"

if [[ -f "${WORKSPACE_DIR}/.env" ]]; then
  set -a
  source "${WORKSPACE_DIR}/.env"
  set +a
fi

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" >/dev/null 2>&1; then
  exit 0
fi

cd "${WORKSPACE_DIR}"
nohup "${VENV_DIR}/bin/uvicorn" app.main:app \
  --host 0.0.0.0 \
  --port "${JARVET_PORT:-8000}" \
  >"${LOG_FILE}" 2>&1 &

echo $! >"${PID_FILE}"