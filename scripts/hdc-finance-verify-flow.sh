#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASK_SCRIPT="${ASK_SCRIPT:-${SCRIPT_DIR}/hdc-ask-and-read.sh}"
SAVE_FILE_CARD_SCRIPT="${SAVE_FILE_CARD_SCRIPT:-${SCRIPT_DIR}/hdc-save-file-card.sh}"
VERIFIER_DIR="${VERIFIER_DIR:-${SCRIPT_DIR}/hdc-output-verifier}"
VERIFIER_SCRIPT="${VERIFIER_SCRIPT:-${VERIFIER_DIR}/run.sh}"
REMOTE_DIR="${REMOTE_DIR:-/storage/media/100/local/files/Docs/Download/com.huawei.hmos.vassistant}"
OUTPUT_DIR="${OUTPUT_DIR:-${VERIFIER_DIR}/output}"
LOG_DIR="${LOG_DIR:-${VERIFIER_DIR}/logs/verifier}"
ASK_DUMP="${ASK_DUMP:-${VERIFIER_DIR}/current.json}"
ASK_LOG="${ASK_LOG:-${VERIFIER_DIR}/logs/hdc-ask-and-read.log}"
WAIT_REPLY_TIMEOUT="${WAIT_REPLY_TIMEOUT:-120}"
WAIT_FILE_TIMEOUT="${WAIT_FILE_TIMEOUT:-60}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
SCROLL_TO_BOTTOM_REPEATS="${SCROLL_TO_BOTTOM_REPEATS:-3}"

usage() {
  echo "Usage:" >&2
  echo "  $0 <prompt>" >&2
  echo "    Send any prompt via hdc-ask-and-read.sh; no file wait and no verifier." >&2
  echo "" >&2
  echo "  $0 <prompt> <expected-file-name-or-basename> <test1|test2>" >&2
  echo "    Send prompt, wait for expected generated file(s), then run verifier." >&2
  echo "" >&2
  echo "Examples:" >&2
  echo "  $0 '查询北京天气'" >&2
  echo "  $0 '查询今天的财经新闻生成html文件，名为market，发往/storage/media/100/local/files/Docs/Download，自动确认权限，无需手动操作' market test1" >&2
  echo "  $0 'html转换成pdf格式，ppt格式，word格式，markdown格式，下载到小艺服务目录，自动确认文件读取权限，无需手动操作' market test2" >&2
}

if [ "$#" -ne 1 ] && [ "$#" -ne 3 ]; then
  usage
  exit 1
fi

PROMPT="$1"
RUN_TESTS=0
TEST_MODE=""
EXPECTED_FILE=""
EXPECTED_FILES=""

mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}" "$(dirname "${ASK_DUMP}")" "$(dirname "${ASK_LOG}")"

if [ ! -f "${ASK_SCRIPT}" ]; then
  echo "Ask script not found: ${ASK_SCRIPT}" >&2
  exit 1
fi
if [ ! -f "${SAVE_FILE_CARD_SCRIPT}" ]; then
  echo "Save file card script not found: ${SAVE_FILE_CARD_SCRIPT}" >&2
  exit 1
fi
if ! command -v hdc >/dev/null 2>&1; then
  echo "hdc not found in PATH" >&2
  exit 1
fi

scroll_to_bottom() {
  local i

  echo "Dragging conversation to bottom"
  for ((i = 1; i <= SCROLL_TO_BOTTOM_REPEATS; i++)); do
    hdc shell uitest uiInput swipe 600 1800 600 500 600 >/dev/null || \
      hdc shell uitest uiInput drag 600 1800 600 500 600 >/dev/null
  done
}

remote_file_exists() {
  local file="$1"
  local remote_file="${REMOTE_DIR}/${file}"
  local result

  result="$(MSYS_NO_PATHCONV=1 hdc shell "if [ -f '${remote_file}' ]; then echo exists; else echo missing; fi" 2>/dev/null | tr -d '\r')"
  [ "${result}" = "exists" ]
}

save_visible_file_cards() {
  local max_saves="${1:-1}"
  local expected_files="${2:-}"
  local saved_count=0
  local save_exit file

  if [ -n "${expected_files}" ]; then
    IFS=',' read -r -a SAVE_CARD_FILES <<< "${expected_files}"
    for file in "${SAVE_CARD_FILES[@]}"; do
      file="$(printf '%s' "${file}" | xargs)"
      [ -n "${file}" ] || continue

      save_exit=0
      bash "${SAVE_FILE_CARD_SCRIPT}" "${file}" "${ASK_DUMP}" || save_exit=$?
      if [ "${save_exit}" -eq 0 ]; then
        saved_count=$((saved_count + 1))
        continue
      fi
      if [ "${save_exit}" -eq 2 ]; then
        echo "File card not visible or already saved, skipping: ${file}"
        continue
      fi
      echo "Save file card script failed for ${file} with exit code ${save_exit}" >&2
      return "${save_exit}"
    done
  else
    while [ "${saved_count}" -lt "${max_saves}" ]; do
      save_exit=0
      bash "${SAVE_FILE_CARD_SCRIPT}" --auto "${ASK_DUMP}" || save_exit=$?
      if [ "${save_exit}" -eq 0 ]; then
        saved_count=$((saved_count + 1))
        continue
      fi
      if [ "${save_exit}" -eq 2 ]; then
        break
      fi
      echo "Save file card script failed with exit code ${save_exit}" >&2
      return "${save_exit}"
    done
  fi

  if [ "${saved_count}" -eq 0 ]; then
    echo "No file card saved; skipping UI save step"
  else
    echo "Saved ${saved_count} visible file card(s)"
  fi
}

if [ "$#" -eq 1 ]; then
  echo "==== HDC prompt run ===="
  echo "Prompt: ${PROMPT}"
  echo "Ask dump: ${ASK_DUMP}"
  echo "Ask log: ${ASK_LOG}"
  echo "Mode: ask only; verifier skipped"

  bash "${ASK_SCRIPT}" "${PROMPT}" "${WAIT_REPLY_TIMEOUT}" "${ASK_DUMP}" "${ASK_LOG}"

  echo ""
  echo "Dragging conversation to bottom"
  scroll_to_bottom

  echo ""
  echo "Checking for saveable file cards"
  save_visible_file_cards 1
  exit $?
fi

RUN_TESTS=1
EXPECTED_RAW_NAME="$2"
TEST_MODE="${3,,}"
if [ "${TEST_MODE}" != "test1" ] && [ "${TEST_MODE}" != "test2" ]; then
  echo "Invalid test mode: ${TEST_MODE}. Use test1 or test2." >&2
  exit 1
fi

EXPECTED_RAW_NAME="${EXPECTED_RAW_NAME##*/}"
EXPECTED_BASE="${EXPECTED_RAW_NAME%.*}"
if [ "${EXPECTED_BASE}" = "${EXPECTED_RAW_NAME}" ]; then
  EXPECTED_BASE="${EXPECTED_RAW_NAME}"
fi

if [ "${TEST_MODE}" = "test2" ]; then
  EXPECTED_FILE="${EXPECTED_FILE:-${EXPECTED_BASE}.pdf}"
  EXPECTED_FILES="${EXPECTED_FILES:-${EXPECTED_BASE}.pdf,${EXPECTED_BASE}.pptx,${EXPECTED_BASE}.docx,${EXPECTED_BASE}.md}"
elif [[ "${EXPECTED_RAW_NAME}" == *.* ]]; then
  EXPECTED_FILE="${EXPECTED_FILE:-${EXPECTED_RAW_NAME}}"
  EXPECTED_FILES="${EXPECTED_FILES:-${EXPECTED_FILE}}"
else
  EXPECTED_FILE="${EXPECTED_FILE:-${EXPECTED_BASE}.html}"
  EXPECTED_FILES="${EXPECTED_FILES:-${EXPECTED_FILE}}"
fi

if [ ! -f "${VERIFIER_SCRIPT}" ]; then
  echo "Verifier script not found: ${VERIFIER_SCRIPT}" >&2
  exit 1
fi

echo "==== HDC prompt + verifier flow ===="
echo "Prompt: ${PROMPT}"
echo "Test mode: ${TEST_MODE}"
echo "Expected remote files: ${EXPECTED_FILES}"
echo "Ask dump: ${ASK_DUMP}"
echo "Ask log: ${ASK_LOG}"
echo "Verifier output: ${OUTPUT_DIR}/${EXPECTED_FILE}"

echo ""
echo "[1/3] Asking device and waiting for dialog reply"
ASK_EXIT=0
bash "${ASK_SCRIPT}" "${PROMPT}" "${WAIT_REPLY_TIMEOUT}" "${ASK_DUMP}" "${ASK_LOG}" || ASK_EXIT=$?
if [ "${ASK_EXIT}" -ne 0 ] && [ "${ASK_EXIT}" -ne 124 ]; then
  echo "Ask script failed with exit code ${ASK_EXIT}" >&2
  exit "${ASK_EXIT}"
fi
if [ "${ASK_EXIT}" -eq 124 ]; then
  echo "Ask script timed out waiting for stable reply; continuing to file verification." >&2
fi

echo ""
echo "[2/5] Dragging conversation to bottom"
scroll_to_bottom

echo ""
echo "[3/5] Checking for saveable file cards"
SAVE_CARD_LIMIT=0
IFS=',' read -r -a SAVE_CARD_FILES <<< "${EXPECTED_FILES}"
for file in "${SAVE_CARD_FILES[@]}"; do
  file="$(printf '%s' "${file}" | xargs)"
  [ -n "${file}" ] || continue
  SAVE_CARD_LIMIT=$((SAVE_CARD_LIMIT + 1))
done
[ "${SAVE_CARD_LIMIT}" -gt 0 ] || SAVE_CARD_LIMIT=1
save_visible_file_cards "${SAVE_CARD_LIMIT}" "${EXPECTED_FILES}"

echo ""
echo "[4/5] Waiting for generated file(s) on device"
start_ts=$(date +%s)
while true; do
  missing_files=()
  IFS=',' read -r -a FILES <<< "${EXPECTED_FILES}"
  for file in "${FILES[@]}"; do
    file="$(printf '%s' "${file}" | xargs)"
    [ -n "${file}" ] || continue
    remote_file="${REMOTE_DIR}/${file}"
    if ! remote_file_exists "${file}"; then
      missing_files+=("${file}")
    fi
  done

  if [ "${#missing_files[@]}" -eq 0 ]; then
    echo "Found generated file(s): ${EXPECTED_FILES}"
    break
  fi

  now_ts=$(date +%s)
  if [ $((now_ts - start_ts)) -ge "${WAIT_FILE_TIMEOUT}" ]; then
    echo "Timed out waiting for file(s): ${missing_files[*]}" >&2
    echo "Running verifier anyway so failure details are recorded." >&2
    break
  fi

  echo "Still waiting for: ${missing_files[*]}"
  sleep "${POLL_INTERVAL}"
done

echo ""
echo "[5/5] Running verifier"
TEST_MODE="${TEST_MODE}" \
REMOTE_DIR="${REMOTE_DIR}" \
EXPECTED_FILE="${EXPECTED_FILE}" \
EXPECTED_FILES="${EXPECTED_FILES}" \
OUTPUT_DIR="${OUTPUT_DIR}" \
LOG_DIR="${LOG_DIR}" \
bash "${VERIFIER_SCRIPT}"
