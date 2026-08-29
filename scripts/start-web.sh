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

for _ in {1..50}; do
  if curl --fail --silent "http://127.0.0.1:${JARVET_PORT:-8000}/api/health" >/dev/null; then
    exit 0
  fi
  if ! kill -0 "$(cat "${PID_FILE}")" >/dev/null 2>&1; then
    cat "${LOG_FILE}" >&2
    exit 1
  fi
  sleep 0.2
done

echo "Jarvet did not become ready on port ${JARVET_PORT:-8000}." >&2
exit 1