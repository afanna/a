#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <file-name|--auto> [local-dump-json]" >&2
  echo "Example: $0 finance.html" >&2
  echo "Example: $0 --auto" >&2
  exit 1
fi

TARGET_FILE="$1"
LOCAL_DUMP="${2:-current.json}"
REMOTE_DUMP="/data/local/tmp/current_ui_tree.json"
REMOTE_DIR="${REMOTE_DIR:-/storage/media/100/local/files/Docs/Download/com.huawei.hmos.vassistant}"
POLL_INTERVAL="${POLL_INTERVAL:-1}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-20}"
CONFIRM_AFTER_DIRECTORY="${CONFIRM_AFTER_DIRECTORY:-0}"

command -v hdc >/dev/null 2>&1 || {
  echo "hdc not found in PATH" >&2
  exit 1
}

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys' >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1 && python -c 'import sys' >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "python3/python not found in PATH" >&2
  exit 1
fi

LOCAL_DUMP_FOR_HDC="${LOCAL_DUMP}"
if command -v cygpath >/dev/null 2>&1; then
  LOCAL_DUMP_FOR_HDC="$(cygpath -w "${LOCAL_DUMP}")"
fi

remote_file_exists() {
  local file="$1"
  local remote_file="${REMOTE_DIR}/${file}"
  local result

  result="$(MSYS_NO_PATHCONV=1 hdc shell "if [ -f '${remote_file}' ]; then echo exists; else echo missing; fi" 2>/dev/null | tr -d '\r')"
  [ "${result}" = "exists" ]
}

remove_remote_file_if_exists() {
  local file="$1"
  local remote_file="${REMOTE_DIR}/${file}"
  local result

  result="$(MSYS_NO_PATHCONV=1 hdc shell "if [ -f '${remote_file}' ]; then rm -f '${remote_file}' && echo removed; else echo missing; fi" 2>/dev/null | tr -d '\r')"
  if [ "${result}" = "removed" ]; then
    echo "Removed existing remote file before saving: ${remote_file}" >&2
  fi
}

dump_tree() {
  MSYS_NO_PATHCONV=1 hdc shell uitest dumpLayout -p "${REMOTE_DUMP}" >/dev/null
  MSYS_NO_PATHCONV=1 hdc file recv "${REMOTE_DUMP}" "${LOCAL_DUMP_FOR_HDC}" >/dev/null
}

locate_text() {
  local match_mode="$1"
  shift
  PYTHONIOENCODING=utf-8 "${PYTHON_BIN}" - "${LOCAL_DUMP}" "${match_mode}" "$@" <<'PY'
import json
import re
import sys

path = sys.argv[1]
mode = sys.argv[2]
needles = sys.argv[3:]
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    tree = json.load(f)

candidates = []

def parse_bounds(value):
    nums = [int(n) for n in re.findall(r"-?\d+", str(value or ""))]
    if len(nums) < 4:
        return None
    x1, y1, x2, y2 = nums[:4]
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2

def walk(node, depth=0):
    if not isinstance(node, dict):
        return
    attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else node
    text = str(attrs.get("text", "") or "")
    node_id = str(attrs.get("id", "") or "")
    desc = str(attrs.get("description", "") or "")
    haystack = "\n".join([text, node_id, desc])
    bounds = parse_bounds(attrs.get("bounds"))
    enabled = str(attrs.get("enabled", "true")).lower() != "false"
    visible = str(attrs.get("visible", "true")).lower() != "false"
    clickable = str(attrs.get("clickable", "")).lower() == "true"

    if bounds and enabled and visible:
        for needle in needles:
            matched = haystack == needle if mode == "exact" else needle in haystack
            if matched:
                score = 100
                if text == needle:
                    score += 50
                if clickable:
                    score += 20
                if attrs.get("type") in ("Button", "Text"):
                    score += 10
                # Prefer lower visible candidates when duplicate menu labels exist.
                candidates.append((score, bounds[1], bounds[0], text, node_id, bounds))

    for child in node.get("children") or []:
        walk(child, depth + 1)

walk(tree)
if not candidates:
    sys.exit(1)

candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
score, _, _, text, node_id, bounds = candidates[0]
x1, y1, x2, y2 = bounds
print(f"{(x1 + x2) // 2} {(y1 + y2) // 2}", end="")
print(f"Found text target: text={text!r} id={node_id!r} bounds=[{x1},{y1}][{x2},{y2}] center=({(x1 + x2) // 2},{(y1 + y2) // 2})", file=sys.stderr)
PY
}

locate_saveable_file_card() {
  PYTHONIOENCODING=utf-8 "${PYTHON_BIN}" - "${LOCAL_DUMP}" <<'PY'
import json
import re
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    tree = json.load(f)

candidates = []
file_pattern = re.compile(r"[^\\/\s]+\.(?:html?|pdf|pptx?|docx?|md|markdown)\b", re.IGNORECASE)


def parse_bounds(value):
    nums = [int(n) for n in re.findall(r"-?\d+", str(value or ""))]
    if len(nums) < 4:
        return None
    x1, y1, x2, y2 = nums[:4]
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def walk(node):
    if not isinstance(node, dict):
        return
    attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else node
    text = str(attrs.get("text", "") or "")
    node_id = str(attrs.get("id", "") or "")
    desc = str(attrs.get("description", "") or "")
    bounds = parse_bounds(attrs.get("bounds"))
    enabled = str(attrs.get("enabled", "true")).lower() != "false"
    visible = str(attrs.get("visible", "true")).lower() != "false"
    clickable = str(attrs.get("clickable", "")).lower() == "true"
    haystack = "\n".join([text, node_id, desc])

    if bounds and enabled and visible:
        match = file_pattern.search(haystack)
        if match:
            x1, y1, x2, y2 = bounds
            score = 100
            if text == match.group(0):
                score += 40
            if clickable:
                score += 30
            if y1 > 250:
                score += 20
            candidates.append((score, y1, x1, match.group(0), bounds))

    for child in node.get("children") or []:
        walk(child)


walk(tree)
if not candidates:
    sys.exit(1)

candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
score, _, _, name, bounds = candidates[0]
x1, y1, x2, y2 = bounds
print(name)
print(f"Found saveable file card: name={name!r} bounds=[{x1},{y1}][{x2},{y2}] center=({(x1 + x2) // 2},{(y1 + y2) // 2})", file=sys.stderr)
PY
}

click_text_if_visible() {
  local description="$1"
  local mode="$2"
  shift 2
  local coords x y

  dump_tree
  if coords="$(locate_text "${mode}" "$@" 2>/dev/null)"; then
    read -r x y <<<"${coords}"
    echo "Clicking visible ${description} at (${x}, ${y})" >&2
    hdc shell uitest uiInput click "${x}" "${y}" >/dev/null
    return 0
  fi
  return 1
}

wait_and_click_text() {
  local description="$1"
  local mode="$2"
  shift 2
  local start_ts now_ts coords x y

  echo "Waiting for ${description}" >&2
  start_ts=$(date +%s)
  while true; do
    dump_tree
    if coords="$(locate_text "${mode}" "$@" 2>/dev/null)"; then
      read -r x y <<<"${coords}"
      echo "Clicking ${description} at (${x}, ${y})" >&2
      hdc shell uitest uiInput click "${x}" "${y}" >/dev/null
      return 0
    fi

    now_ts=$(date +%s)
    if [ $((now_ts - start_ts)) -ge "${WAIT_TIMEOUT}" ]; then
      echo "Timed out waiting for ${description}: $*" >&2
      return 1
    fi
    sleep "${POLL_INTERVAL}"
  done
}

click_top_right_action() {
  local coords x y

  coords="$(PYTHONIOENCODING=utf-8 "${PYTHON_BIN}" - "${LOCAL_DUMP}" <<'PY'
import json
import re
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    tree = json.load(f)

candidates = []
confirm_words = ("保存", "确定", "完成", "选择", "移动到此处", "复制到此处", "Save", "OK")


def parse_bounds(value):
    nums = [int(n) for n in re.findall(r"-?\d+", str(value or ""))]
    if len(nums) < 4:
        return None
    x1, y1, x2, y2 = nums[:4]
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def walk(node):
    if not isinstance(node, dict):
        return
    attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else node
    text = str(attrs.get("text", "") or "")
    node_id = str(attrs.get("id", "") or "")
    desc = str(attrs.get("description", "") or "")
    node_type = str(attrs.get("type", "") or "")
    haystack = "\n".join([text, node_id, desc])
    bounds = parse_bounds(attrs.get("bounds"))
    enabled = str(attrs.get("enabled", "true")).lower() != "false"
    visible = str(attrs.get("visible", "true")).lower() != "false"
    clickable = str(attrs.get("clickable", "")).lower() == "true"

    if bounds and enabled and visible:
        x1, y1, x2, y2 = bounds
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        width = x2 - x1
        score = 0

        if any(word in haystack for word in confirm_words):
            score += 120
        if clickable:
            score += 40
        if node_type in ("Button", "Text", "Image", "Stack"):
            score += 10

        # The final picker action is normally in the top-right title bar.
        if x1 >= 700:
            score += 40
        if y1 <= 220:
            score += 40
        if x1 >= 900 and y1 <= 260:
            score += 40
        if width <= 260:
            score += 10

        # Avoid picking file/directory rows in the content area.
        if cy > 350:
            score -= 120

        if score >= 140:
            candidates.append((score, x1, -y1, text, node_id, desc, bounds))

    for child in node.get("children") or []:
        walk(child)


walk(tree)
if not candidates:
    sys.exit(1)

candidates.sort(reverse=True)
score, _, _, text, node_id, desc, bounds = candidates[0]
x1, y1, x2, y2 = bounds
cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
print(f"{cx} {cy}", end="")
print(f"Found top-right action: text={text!r} id={node_id!r} desc={desc!r} bounds=[{x1},{y1}][{x2},{y2}] center=({cx},{cy})", file=sys.stderr)
PY
  )" || return 1

  read -r x y <<<"${coords}"
  [ -n "${x:-}" ] && [ -n "${y:-}" ] || return 1
  echo "Clicking top-right action at (${x}, ${y})" >&2
  hdc shell uitest uiInput click "${x}" "${y}" >/dev/null
}

if [ "${TARGET_FILE}" = "--auto" ]; then
  echo "[0/5] Detecting saveable file card" >&2
  dump_tree
  if ! TARGET_FILE="$(locate_saveable_file_card)"; then
    echo "No saveable file card found" >&2
    exit 2
  fi
  echo "Detected saveable file card: ${TARGET_FILE}" >&2
fi

echo "[1/5] Locating file card: ${TARGET_FILE}" >&2
dump_tree
if ! CARD_COORDS="$(locate_text contains "${TARGET_FILE}")"; then
  if remote_file_exists "${TARGET_FILE}"; then
    echo "File card not visible, but remote file already exists; skipping save: ${REMOTE_DIR}/${TARGET_FILE}" >&2
    exit 2
  fi
  echo "File card not visible and remote file does not exist: ${TARGET_FILE}" >&2
  exit 2
fi

remove_remote_file_if_exists "${TARGET_FILE}"
read -r CARD_X CARD_Y <<<"${CARD_COORDS}"

echo "[2/5] Long pressing file card at (${CARD_X}, ${CARD_Y})" >&2
hdc shell uitest uiInput longClick "${CARD_X}" "${CARD_Y}" >/dev/null

# The actual menu text can vary between builds. Try common save/download labels.
echo "[3/5] Choosing save/download action" >&2
wait_and_click_text "save/download action" contains \
  "保存" "下载" "另存" "存储" "保存到" "保存至" "文件管理" "Save" "Download"

echo "[4/5] Choosing 小艺服务 directory under Download" >&2
if click_text_if_visible "小艺服务 directory" contains "小艺服务" "com.huawei.hmos.vassistant"; then
  echo "Download appears expanded; 小艺服务 directory clicked directly" >&2
else
  echo "小艺服务 directory not visible; expanding Download first" >&2
  wait_and_click_text "Download directory" contains \
    "Download" "下载" "Downloads"
  wait_and_click_text "小艺服务 directory" contains \
    "小艺服务" "com.huawei.hmos.vassistant"
fi

# After entering/selecting the 小艺服务 directory, refresh the tree and click the top-right confirm/save button.
echo "Refreshing UI tree after clicking 小艺服务 directory" >&2
dump_tree

echo "Clicking top-right confirm/save button" >&2
if ! click_top_right_action; then
  echo "Top-right confirm/save button not found by position; falling back to text matching" >&2
  wait_and_click_text "final save/confirm button" contains \
    "保存" "确定" "完成" "选择" "移动到此处" "复制到此处" "Save" "OK"
fi

echo "Done" >&2
