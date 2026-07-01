#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REMOTE_DIR="${REMOTE_DIR:-/storage/media/100/local/files/Docs/Download/com.huawei.hmos.vassistant}"
export EXPECTED_FILE="${EXPECTED_FILE:-finance.html}"
export EXPECTED_FILES="${EXPECTED_FILES:-${EXPECTED_FILE}}"
export TEST_MODE="${TEST_MODE:-test1}"
export OUTPUT_DIR="${OUTPUT_DIR:-${SCRIPT_DIR}/output}"
export LOG_DIR="${LOG_DIR:-${SCRIPT_DIR}/logs/verifier}"
export TEST_DIR="${TEST_DIR:-${SCRIPT_DIR}/tests}"

bash "${SCRIPT_DIR}/tests/test.sh"
