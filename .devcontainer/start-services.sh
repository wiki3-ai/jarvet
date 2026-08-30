#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

"${WORKSPACE_DIR}/.devcontainer/start-jupyterlab.sh"
"${WORKSPACE_DIR}/scripts/start-web.sh"
"${WORKSPACE_DIR}/scripts/start-cloudflared.sh"