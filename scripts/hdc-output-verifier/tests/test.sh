#!/usr/bin/env bash
set -euo pipefail

REMOTE_DIR="${REMOTE_DIR:-/storage/media/100/local/files/Docs/Download/com.huawei.hmos.vassistant}"
EXPECTED_FILE="${EXPECTED_FILE:-finance.html}"
EXPECTED_FILES="${EXPECTED_FILES:-${EXPECTED_FILE}}"
TEST_MODE="${TEST_MODE:-test1}"
OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
LOG_DIR="${LOG_DIR:-/logs/verifier}"
TEST_DIR="${TEST_DIR:-/tests}"

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}"

if ! command -v hdc >/dev/null 2>&1; then
  echo "hdc not found in PATH" >&2
  echo 0 > "${LOG_DIR}/reward.txt"
  exit 1
fi

echo "Receiving generated file(s) from device"
echo "Remote dir: ${REMOTE_DIR}"
echo "Expected files: ${EXPECTED_FILES}"
echo "Output dir: ${OUTPUT_DIR}"

IFS=',' read -r -a FILES <<< "${EXPECTED_FILES}"
for file in "${FILES[@]}"; do
  file="$(printf '%s' "${file}" | xargs)"
  [ -n "${file}" ] || continue

  local_file="${OUTPUT_DIR}/${file}"
  remote_file="${REMOTE_DIR}/${file}"
  local_file_for_hdc="${local_file}"
  if command -v cygpath >/dev/null 2>&1; then
    local_file_for_hdc="$(cygpath -w "${local_file}")"
  fi

  echo "Remote: ${remote_file}"
  echo "Local:  ${local_file}"
  echo "HDC local path: ${local_file_for_hdc}"

  rm -f "${local_file}"
  if ! MSYS_NO_PATHCONV=1 hdc file recv "${remote_file}" "${local_file_for_hdc}"; then
    echo "Failed to receive ${remote_file}" >&2
  fi
done

PYTEST_EXIT=0
if command -v uvx >/dev/null 2>&1; then
  uvx \
    --with pytest==8.4.1 \
    --with pytest-json-ctrf==0.3.5 \
    pytest --ctrf "${LOG_DIR}/ctrf.json" "${TEST_DIR}/test_outputs.py" -rA || PYTEST_EXIT=$?
else
  python -m pytest "${TEST_DIR}/test_outputs.py" -rA || PYTEST_EXIT=$?
fi

if [ "${PYTEST_EXIT}" -eq 0 ]; then
  echo 1 > "${LOG_DIR}/reward.txt"
else
  echo 0 > "${LOG_DIR}/reward.txt"
fi

for file in "${FILES[@]}"; do
  file="$(printf '%s' "${file}" | xargs)"
  [ -n "${file}" ] || continue
  local_file="${OUTPUT_DIR}/${file}"
  if [ -f "${local_file}" ]; then
    cp "${local_file}" "${LOG_DIR}/${file}"
  fi
done

exit "${PYTEST_EXIT}"
