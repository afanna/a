#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <text-to-input> [local-dump-json]" >&2
  exit 1
fi

INPUT_TEXT="$1"
LOCAL_DUMP="${2:-current.json}"
REMOTE_DUMP="/data/local/tmp/current_ui_tree.json"

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
  echo "Dumping UI tree to device: ${REMOTE_DUMP}" >&2
  MSYS_NO_PATHCONV=1 hdc shell uitest dumpLayout -p "${REMOTE_DUMP}" >/dev/null
  echo "Receiving UI tree to local: ${LOCAL_DUMP}" >&2
  MSYS_NO_PATHCONV=1 hdc file recv "${REMOTE_DUMP}" "${LOCAL_DUMP}" >/dev/null
}

clear_input() {
  local x="$1"
  local y="$2"

  echo "Clearing input at (${x}, ${y})" >&2
  hdc shell uitest uiInput click "${x}" "${y}" >/dev/null
  hdc shell uitest uiInput keyEvent 2072 2017 >/dev/null || true
  hdc shell uitest uiInput keyEvent 2055 >/dev/null || true
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
            # Some builds remove send_hot_area id; after typing, the right hot area is the clickable Stack in keyboard_builder.
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

dump_tree
INPUT_COORDS="$(ensure_text_input)"
read -r INPUT_X INPUT_Y <<<"${INPUT_COORDS}"

clear_input "${INPUT_X}" "${INPUT_Y}"

echo "Inputting text" >&2
hdc shell uitest uiInput inputText "${INPUT_X}" "${INPUT_Y}" "${INPUT_TEXT}" >/dev/null

# The send button may only appear after text is entered, so refresh the tree.
dump_tree
SEND_COORDS="$(locate_control send)"
read -r SEND_X SEND_Y <<<"${SEND_COORDS}"

echo "Clicking send at (${SEND_X}, ${SEND_Y})" >&2
hdc shell uitest uiInput click "${SEND_X}" "${SEND_Y}" >/dev/null

echo "Done" >&2
