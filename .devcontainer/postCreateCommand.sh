#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="${WORKSPACE_FOLDER:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
VENV_DIR="${WORKSPACE_DIR}/.venv"

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install "nmo-python @ git+https://github.com/wiki3-ai/nemo.git@main#subdirectory=nemo-python"
"${VENV_DIR}/bin/pip" install jupyterlab ipykernel
"${VENV_DIR}/bin/python" -m ipykernel install --user --name jarvet --display-name "Python (jarvet)"
