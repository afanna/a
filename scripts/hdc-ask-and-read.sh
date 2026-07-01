#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <text-to-input> [timeout-seconds] [local-dump-json] [log-file]" >&2
  exit 1
fi

INPUT_TEXT="$1"
TIMEOUT_SECONDS="${2:-60}"
LOCAL_DUMP="${3:-current.json}"
LOG_FILE="${4:-hdc-ask-and-read.log}"
LOCAL_DUMP_FOR_HDC="${LOCAL_DUMP}"
if command -v cygpath >/dev/null 2>&1; then
  LOCAL_DUMP_FOR_HDC="$(cygpath -w "${LOCAL_DUMP}")"
fi
REMOTE_DUMP="/data/local/tmp/current_ui_tree.json"
POLL_INTERVAL=2

mkdir -p "$(dirname "${LOG_FILE}")" 2>/dev/null || true
mkdir -p "$(dirname "${LOCAL_DUMP}")" 2>/dev/null || true
touch "${LOG_FILE}"
exec > >(tee -a "${LOG_FILE}") 2> >(tee -a "${LOG_FILE}" >&2)

echo "==== $(date '+%Y-%m-%d %H:%M:%S') hdc ask-and-read ===="
echo "Input: ${INPUT_TEXT}"
echo "Log: ${LOG_FILE}"

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

dump_tree() {
  MSYS_NO_PATHCONV=1 hdc shell uitest dumpLayout -p "${REMOTE_DUMP}" >/dev/null
  MSYS_NO_PATHCONV=1 hdc file recv "${REMOTE_DUMP}" "${LOCAL_DUMP_FOR_HDC}" >/dev/null
}

locate_control() {
  local mode="$1"
  PYTHONIOENCODING=utf-8 "${PYTHON_BIN}" - "${LOCAL_DUMP}" "${mode}" <<'PY'
import json
import re
import sys

path, mode = sys.argv[1], sys.argv[2]
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

def center(bounds):
    x1, y1, x2, y2 = bounds
    return (x1 + x2) // 2, (y1 + y2) // 2

def walk(node, depth=0, in_keyboard=False):
    if not isinstance(node, dict):
        return
    attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else node
    node_type = str(attrs.get("type", ""))
    node_id = str(attrs.get("id", ""))
    lowered_id = node_id.lower()
    hint = str(attrs.get("hint", ""))
    text = str(attrs.get("text", ""))
    enabled = str(attrs.get("enabled", "true")).lower() != "false"
    visible = str(attrs.get("visible", "true")).lower() != "false"
    clickable = str(attrs.get("clickable", "")).lower() == "true"
    bounds = parse_bounds(attrs.get("bounds"))
    now_in_keyboard = in_keyboard or lowered_id == "keyboard_builder"

    if bounds and enabled and visible:
        score = 0
        if mode == "input":
            if node_type == "TextArea":
                score += 100
            if node_type in ("TextInput", "Search", "TextField"):
                score += 80
            if "input" in lowered_id or "text_input" in lowered_id:
                score += 50
            if hint:
                score += 20
            if score > 0 and clickable:
                score += 5
        elif mode == "keyboard_toggle":
            if lowered_id == "chat_page.key_board.icon24":
                score += 120
            if "keyboard" in lowered_id or "key_board" in lowered_id:
                score += 80
            if now_in_keyboard and clickable and bounds[0] <= 250:
                score += 40
            if clickable:
                score += 5
        else:
            if lowered_id == "send_hot_area":
                score += 140
            if "send" in lowered_id:
                score += 100
            if "arrow_up" in lowered_id:
                score += 80
            if text in ("发送", "Send"):
                score += 80
            if now_in_keyboard and clickable and node_type == "Stack" and bounds[0] >= 1000:
                score += 40
        if score > 0:
            candidates.append((score, depth, node_type, node_id, text, hint, bounds))

    for child in node.get("children") or []:
        walk(child, depth + 1, now_in_keyboard)

walk(tree)
if not candidates:
    print(f"No {mode} control found", file=sys.stderr)
    sys.exit(2)

candidates.sort(key=lambda item: (item[0], item[6][1], item[6][0]), reverse=True)
score, depth, node_type, node_id, text, hint, bounds = candidates[0]
x, y = center(bounds)
print(f"{x} {y}", end="")
print(f"Found {mode}: type={node_type} id={node_id} text={text} hint={hint} bounds=[{bounds[0]},{bounds[1]}][{bounds[2]},{bounds[3]}] center=({x},{y})", file=sys.stderr)
PY
}

ensure_text_input() {
  local coords toggle_coords toggle_x toggle_y

  if coords="$(locate_control input 2>/dev/null)"; then
    echo "Text input box is already available" >&2
    printf '%s' "${coords}"
    return 0
  fi

  echo "Input box not found; trying to switch from voice mode to text input" >&2
  toggle_coords="$(locate_control keyboard_toggle)"
  read -r toggle_x toggle_y <<<"${toggle_coords}"
  echo "Clicking keyboard toggle at (${toggle_x}, ${toggle_y})" >&2
  hdc shell uitest uiInput click "${toggle_x}" "${toggle_y}" >/dev/null

  dump_tree
  locate_control input
}

clear_input() {
  local x="$1"
  local y="$2"

  echo "Clearing input at (${x}, ${y})" >&2
  hdc shell uitest uiInput click "${x}" "${y}" >/dev/null

  # Ctrl+A then Delete. Numeric key codes are used because key names vary across images.
  # 2072 = Ctrl, 2017 = A, 2055 = Delete on current HarmonyOS builds.
  hdc shell uitest uiInput keyEvent 2072 2017 >/dev/null || true
  hdc shell uitest uiInput keyEvent 2055 >/dev/null || true
}

try_allow_permission() {
  local coords x y

  coords="$(PYTHONIOENCODING=utf-8 "${PYTHON_BIN}" - "${LOCAL_DUMP}" <<'PY'
import json
import re
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    tree = json.load(f)

nodes = []

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
    nodes.append(attrs)
    for child in node.get("children") or []:
        walk(child)

walk(tree)
all_text = "\n".join(str(n.get("text", "")) for n in nodes)
if "隐私授权" not in all_text and "文件读取权限" not in all_text:
    sys.exit(1)

candidates = []
for attrs in nodes:
    text = str(attrs.get("text", ""))
    node_id = str(attrs.get("id", ""))
    enabled = str(attrs.get("enabled", "true")).lower() != "false"
    visible = str(attrs.get("visible", "true")).lower() != "false"
    bounds = parse_bounds(attrs.get("bounds"))
    if not (enabled and visible and bounds):
        continue
    score = 0
    if text == "允许":
        score += 100
    if node_id == "check.permission.card.build.left.text":
        score += 100
    if score:
        candidates.append((score, bounds))

if not candidates:
    sys.exit(1)

candidates.sort(key=lambda item: item[0], reverse=True)
x1, y1, x2, y2 = candidates[0][1]
print(f"{(x1 + x2) // 2} {(y1 + y2) // 2}", end="")
PY
)" || return 1

  read -r x y <<<"${coords}"
  [ -n "${x:-}" ] && [ -n "${y:-}" ] || return 1
  echo "Privacy permission detected; clicking Allow at (${x}, ${y})" >&2
  hdc shell uitest uiInput click "${x}" "${y}" >/dev/null
}

extract_reply() {
  PYTHONIOENCODING=utf-8 "${PYTHON_BIN}" - "${LOCAL_DUMP}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    tree = json.load(f)

cards = []
current_card = None
busy_words = ("正在使用工具", "正在思考", "生成中", "执行中", "处理中")
ignore_texts = {"任务处理已完成~", "内容由 AI 生成", "技能市场", "添加至桌面"}

def attrs_of(node):
    return node.get("attributes") if isinstance(node.get("attributes"), dict) else node

def walk(node, active_card=None):
    if not isinstance(node, dict):
        return
    attrs = attrs_of(node)
    node_id = str(attrs.get("id", ""))
    node_type = str(attrs.get("type", ""))
    text = str(attrs.get("text", ""))

    new_card = active_card
    if node_id == "chat_item.build.stream_text_card":
        new_card = []
        cards.append(new_card)

    if new_card is not None and node_type == "Text" and text.strip() and text not in ignore_texts:
        new_card.append(text)

    for child in node.get("children") or []:
        walk(child, new_card)

walk(tree)

busy = False
for card in cards:
    joined = "\n".join(card)
    if any(word in joined for word in busy_words):
        busy = True

reply = ""
for card in reversed(cards):
    meaningful = [t for t in card if not any(word in t for word in busy_words)]
    if meaningful:
        reply = "\n".join(meaningful).strip()
        break

print("BUSY=1" if busy else "BUSY=0")
print("REPLY_BEGIN")
print(reply)
print("REPLY_END")
PY
}

echo "Dumping UI tree" >&2
dump_tree
INPUT_COORDS="$(ensure_text_input)"
read -r INPUT_X INPUT_Y <<<"${INPUT_COORDS}"

clear_input "${INPUT_X}" "${INPUT_Y}"

echo "Inputting text" >&2
hdc shell uitest uiInput inputText "${INPUT_X}" "${INPUT_Y}" "${INPUT_TEXT}" >/dev/null

echo "Refreshing UI tree for send button" >&2
dump_tree
SEND_COORDS="$(locate_control send)"
read -r SEND_X SEND_Y <<<"${SEND_COORDS}"

echo "Clicking send at (${SEND_X}, ${SEND_Y})" >&2
hdc shell uitest uiInput click "${SEND_X}" "${SEND_Y}" >/dev/null

echo "Waiting for reply" >&2
start_ts=$(date +%s)
last_reply=""
stable_count=0

while true; do
  dump_tree
  try_allow_permission || true
  parsed="$(extract_reply)"
  busy="$(printf '%s\n' "${parsed}" | awk -F= '/^BUSY=/{print $2; exit}')"
  reply="$(printf '%s\n' "${parsed}" | awk '/^REPLY_BEGIN$/{flag=1;next}/^REPLY_END$/{flag=0}flag')"

  if [ -n "${reply}" ] && [ "${reply}" = "${last_reply}" ]; then
    stable_count=$((stable_count + 1))
  else
    stable_count=0
    last_reply="${reply}"
  fi

  if [ -n "${reply}" ] && [ "${busy}" = "0" ] && [ "${stable_count}" -ge 1 ]; then
    printf '%s\n' "${reply}"
    exit 0
  fi

  now_ts=$(date +%s)
  if [ $((now_ts - start_ts)) -ge "${TIMEOUT_SECONDS}" ]; then
    echo "Timed out waiting for stable reply; latest reply:" >&2
    printf '%s\n' "${reply}"
    exit 124
  fi

  sleep "${POLL_INTERVAL}"
done
