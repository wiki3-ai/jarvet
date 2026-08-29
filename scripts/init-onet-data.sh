#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ONET_VERSION="${ONET_VERSION:-31_0}"
ARCHIVE_NAME="db_${ONET_VERSION}_nt.zip"
DATA_DIR="${WORKSPACE_DIR}/data/db_${ONET_VERSION}_nt"
DOWNLOAD_URL="https://www.onetcenter.org/dl_files/database/${ARCHIVE_NAME}"

if [[ -f "${DATA_DIR}/Read Me.txt" ]]; then
  echo "O*NET ${ONET_VERSION//_/.} N-Triples data is already initialized."
  exit 0
fi

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TEMP_DIR}"' EXIT

echo "Downloading O*NET ${ONET_VERSION//_/.} N-Triples data..."
curl --fail --location --retry 3 --output "${TEMP_DIR}/${ARCHIVE_NAME}" "${DOWNLOAD_URL}"
unzip -q "${TEMP_DIR}/${ARCHIVE_NAME}" -d "${TEMP_DIR}/extracted"

EXTRACTED_DIR="${TEMP_DIR}/extracted/db_${ONET_VERSION}_nt"
if [[ ! -f "${EXTRACTED_DIR}/Read Me.txt" ]]; then
  echo "The downloaded archive did not contain the expected O*NET data directory." >&2
  exit 1
fi

mkdir -p "${WORKSPACE_DIR}/data"
rm -rf "${DATA_DIR}"
mv "${EXTRACTED_DIR}" "${DATA_DIR}"
echo "O*NET data initialized at ${DATA_DIR}."