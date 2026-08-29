#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ONET_VERSION="${ONET_VERSION:-31_0}"
ARCHIVE_NAME="db_${ONET_VERSION}_nt.zip"
DATA_DIR="${WORKSPACE_DIR}/data/db_${ONET_VERSION}_nt"
DOWNLOAD_URL="https://www.onetcenter.org/dl_files/database/${ARCHIVE_NAME}"
BRIGHT_OUTLOOK_FILE="${DATA_DIR}/BrightOutlook.csv"
BRIGHT_OUTLOOK_URL="https://www.onetonline.org/find/bright/All_Bright_Outlook_Occupations.csv?b=0&fmt=csv"
VA_DATA_DIR="${WORKSPACE_DIR}/data/va-comparison"
VA_COMPARISON_FILE="${VA_DATA_DIR}/ComparisonToolData.xlsx"
VA_COMPARISON_URL="https://www.benefits.va.gov/GIBILL/docs/job_aids/ComparisonToolData.xlsx"
ZCTA_FILE="${VA_DATA_DIR}/2025_Gaz_zcta_national.zip"
ZCTA_URL="https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_zcta_national.zip"

if [[ -f "${DATA_DIR}/Read Me.txt" ]]; then
  echo "O*NET ${ONET_VERSION//_/.} N-Triples data is already initialized."
else
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
fi

if [[ ! -f "${BRIGHT_OUTLOOK_FILE}" ]]; then
  echo "Downloading current O*NET Bright Outlook occupations..."
  curl --fail --location --retry 3 --output "${BRIGHT_OUTLOOK_FILE}" "${BRIGHT_OUTLOOK_URL}"
fi

mkdir -p "${VA_DATA_DIR}"
if [[ ! -f "${VA_COMPARISON_FILE}" || "${REFRESH_VA_DATA:-0}" == "1" ]]; then
  echo "Downloading the VA GI Bill Comparison Tool dataset..."
  curl --fail --location --retry 3 --output "${VA_COMPARISON_FILE}.download" "${VA_COMPARISON_URL}"
  mv "${VA_COMPARISON_FILE}.download" "${VA_COMPARISON_FILE}"
fi
if [[ ! -f "${ZCTA_FILE}" || "${REFRESH_VA_DATA:-0}" == "1" ]]; then
  echo "Downloading Census ZIP-area centroids..."
  curl --fail --location --retry 3 --output "${ZCTA_FILE}.download" "${ZCTA_URL}"
  mv "${ZCTA_FILE}.download" "${ZCTA_FILE}"
fi