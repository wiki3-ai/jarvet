#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="${WORKSPACE_FOLDER:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
VENV_DIR="${WORKSPACE_DIR}/.venv"
LOG_FILE="${WORKSPACE_DIR}/.jupyterlab.log"
PID_FILE="${WORKSPACE_DIR}/.jupyterlab.pid"

if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" >/dev/null 2>&1; then
  exit 0
fi

nohup "${VENV_DIR}/bin/jupyter" lab \
  --ip=0.0.0.0 \
  --port="${JUPYTER_PORT:-7788}" \
  --no-browser \
  --IdentityProvider.token='' \
  --PasswordIdentityProvider.hashed_password='' \
  --ServerApp.allow_origin='*' \
  >"${LOG_FILE}" 2>&1 &

echo $! > "${PID_FILE}"
