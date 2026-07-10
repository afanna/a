#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

BACKEND="${AESTHETIC_V4_BACKEND:-model}"
FORCE_MOCK=0
if [[ "${1:-}" == "--mock" ]]; then
  BACKEND="mock"
  FORCE_MOCK=1
  shift
fi

INPUT_DIR="${1:-$PACKAGE_ROOT/input_html}"
RUN_DIR="${AESTHETIC_V4_RUN_DIR:-$PACKAGE_ROOT/runs/aesthetic-v4}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODE_BIN="${NODE_BIN:-node}"
INPUT_KIND="html"
case "$INPUT_DIR" in
  *.png|*.PNG|*.jpg|*.JPG|*.jpeg|*.JPEG|*.webp|*.WEBP)
    INPUT_KIND="image"
    ;;
esac

ENV_FILE="$PACKAGE_ROOT/config/aesthetic-v4.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'* && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$ENV_FILE"
fi

if [[ "$FORCE_MOCK" == "0" ]]; then
  BACKEND="${AESTHETIC_V4_BACKEND:-$BACKEND}"
fi

PANGU_BASE_URL="${PANGU_BASE_URL:-http://43.139.21.243:4000}"
PANGU_JUDGE_MODEL="${PANGU_JUDGE_MODEL:-claude-opus-4-7-thinking}"
PANGU_JUDGE_PROMPT_VERSION="${PANGU_JUDGE_PROMPT_VERSION:-aesthetic-v4}"
PANGU_JUDGE_OUTPUT_MODE="${PANGU_JUDGE_OUTPUT_MODE:-full}"
PANGU_JUDGE_TIMEOUT="${PANGU_JUDGE_TIMEOUT:-360}"
PANGU_JUDGE_MAX_TOKENS="${PANGU_JUDGE_MAX_TOKENS:-1200}"
AESTHETIC_V4_WORKERS="${AESTHETIC_V4_WORKERS:-1}"
AESTHETIC_V4_MANIFEST_VIEWPORT="${AESTHETIC_V4_MANIFEST_VIEWPORT:-all}"
AESTHETIC_V4_VIEWPORT="${AESTHETIC_V4_VIEWPORT:-all}"
AESTHETIC_V4_VIEWPORT_SELECTION="${AESTHETIC_V4_VIEWPORT_SELECTION:-auto}"
AESTHETIC_V4_AGGREGATE_STRATEGY="${AESTHETIC_V4_AGGREGATE_STRATEGY:-min}"
AESTHETIC_V4_SCREENSHOT_MODE="${AESTHETIC_V4_SCREENSHOT_MODE:-fullpage}"
AESTHETIC_V4_FULLPAGE_MAX_HEIGHT="${AESTHETIC_V4_FULLPAGE_MAX_HEIGHT:-12000}"
AESTHETIC_V4_ADAPTIVE_VIEWPORTS="${AESTHETIC_V4_ADAPTIVE_VIEWPORTS:-on}"
AESTHETIC_V4_SCORE_BREAKDOWN="${AESTHETIC_V4_SCORE_BREAKDOWN:-on}"
AESTHETIC_V4_DESIGNER_REVIEW="${AESTHETIC_V4_DESIGNER_REVIEW:-on}"
AESTHETIC_V4_FORMAL_REPORT="${AESTHETIC_V4_FORMAL_REPORT:-0}"
AESTHETIC_V4_OUTPUT_JSON="${AESTHETIC_V4_OUTPUT_JSON:-on}"
AESTHETIC_V4_OUTPUT_HTML="${AESTHETIC_V4_OUTPUT_HTML:-off}"
AESTHETIC_V4_JSON_OUT_DIR="${AESTHETIC_V4_JSON_OUT_DIR:-$PACKAGE_ROOT/outputs/json}"
AESTHETIC_V4_JSON_INDEX="${AESTHETIC_V4_JSON_INDEX:-$AESTHETIC_V4_JSON_OUT_DIR/index.json}"
AESTHETIC_V4_OCCLUSION_OVERLAP_CHECK="always_on"

case "$AESTHETIC_V4_SCREENSHOT_MODE" in
  fullpage|first_view) ;;
  *)
    echo "AESTHETIC_V4_SCREENSHOT_MODE must be fullpage or first_view, got: $AESTHETIC_V4_SCREENSHOT_MODE" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_MANIFEST_VIEWPORT" in
  desktop|mobile|all) ;;
  *)
    echo "AESTHETIC_V4_MANIFEST_VIEWPORT must be desktop, mobile, or all; got: $AESTHETIC_V4_MANIFEST_VIEWPORT" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_ADAPTIVE_VIEWPORTS" in
  off|on|auto) ;;
  *)
    echo "AESTHETIC_V4_ADAPTIVE_VIEWPORTS must be off, on, or auto; got: $AESTHETIC_V4_ADAPTIVE_VIEWPORTS" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_SCORE_BREAKDOWN" in
  off|on) ;;
  *)
    echo "AESTHETIC_V4_SCORE_BREAKDOWN must be off or on; got: $AESTHETIC_V4_SCORE_BREAKDOWN" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_DESIGNER_REVIEW" in
  off|on) ;;
  *)
    echo "AESTHETIC_V4_DESIGNER_REVIEW must be off or on; got: $AESTHETIC_V4_DESIGNER_REVIEW" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_OUTPUT_JSON" in
  off|on) ;;
  *)
    echo "AESTHETIC_V4_OUTPUT_JSON must be off or on; got: $AESTHETIC_V4_OUTPUT_JSON" >&2
    exit 2
    ;;
esac

case "$AESTHETIC_V4_OUTPUT_HTML" in
  off|on) ;;
  *)
    echo "AESTHETIC_V4_OUTPUT_HTML must be off or on; got: $AESTHETIC_V4_OUTPUT_HTML" >&2
    exit 2
    ;;
esac

case "$PANGU_JUDGE_OUTPUT_MODE" in
  full|score-only) ;;
  *)
    echo "PANGU_JUDGE_OUTPUT_MODE must be full or score-only; got: $PANGU_JUDGE_OUTPUT_MODE" >&2
    exit 2
    ;;
esac

for required_abs_path in "$INPUT_DIR" "$RUN_DIR"; do
  case "$required_abs_path" in
    /*) ;;
    *)
      echo "Input and output paths must be absolute. Got: $required_abs_path" >&2
      exit 2
      ;;
  esac
done

if [[ "$AESTHETIC_V4_OUTPUT_JSON" == "on" ]]; then
  for required_abs_path in "$AESTHETIC_V4_JSON_OUT_DIR" "$AESTHETIC_V4_JSON_INDEX"; do
    case "$required_abs_path" in
      /*) ;;
      *)
        echo "JSON output paths must be absolute. Got: $required_abs_path" >&2
        exit 2
        ;;
    esac
  done
fi

RENDER_EXTRA_ARGS=()
if [[ "$AESTHETIC_V4_SCREENSHOT_MODE" == "fullpage" ]]; then
  RENDER_EXTRA_ARGS+=(--full-page --max-screenshot-css-height "$AESTHETIC_V4_FULLPAGE_MAX_HEIGHT")
fi

SCORE_EXTRA_ARGS=(
  --adaptive-viewports "$AESTHETIC_V4_ADAPTIVE_VIEWPORTS"
  --score-breakdown "$AESTHETIC_V4_SCORE_BREAKDOWN"
  --designer-review "$AESTHETIC_V4_DESIGNER_REVIEW"
)
if [[ "$AESTHETIC_V4_FORMAL_REPORT" == "1" ]]; then
  SCORE_EXTRA_ARGS+=(--formal-report)
fi

mkdir -p "$RUN_DIR"

SCORE_INPUT="$RUN_DIR/screenshots/render_manifest.jsonl"
if [[ "$INPUT_KIND" == "image" ]]; then
  if [[ ! -f "$INPUT_DIR" ]]; then
    echo "Image input path not found: $INPUT_DIR" >&2
    exit 2
  fi
  SCORE_INPUT="$INPUT_DIR"
  echo "[aesthetic-v4] score image input"
else
  echo "[aesthetic-v4] build manifest"
  "$PYTHON_BIN" scripts/build_html_manifest.py \
    --input "$INPUT_DIR" \
    --out "$RUN_DIR/manifest.jsonl" \
    --summary "$RUN_DIR/manifest.summary.json" \
    --viewport "$AESTHETIC_V4_MANIFEST_VIEWPORT"

  echo "[aesthetic-v4] render screenshots ($AESTHETIC_V4_SCREENSHOT_MODE)"
  RENDER_COMMAND=(
    "$NODE_BIN" scripts/render_screenshots.mjs
    --manifest "$RUN_DIR/manifest.jsonl" \
    --out "$RUN_DIR/screenshots" \
    --viewport "$AESTHETIC_V4_VIEWPORT" \
    --screenshot-on-timeout \
    --capture-scroll-width
  )
  if [[ ${#RENDER_EXTRA_ARGS[@]} -gt 0 ]]; then
    RENDER_COMMAND+=("${RENDER_EXTRA_ARGS[@]}")
  fi
  "${RENDER_COMMAND[@]}"
fi

if [[ "$BACKEND" == "mock" ]]; then
  echo "[aesthetic-v4] score with mock backend"
  "$PYTHON_BIN" scripts/score_images.py \
    --input "$SCORE_INPUT" \
    --out "$RUN_DIR/scores.jsonl" \
    --cache "$RUN_DIR/score_cache.jsonl" \
    --backend mock \
    --viewport-selection "$AESTHETIC_V4_VIEWPORT_SELECTION" \
    --aggregate-strategy "$AESTHETIC_V4_AGGREGATE_STRATEGY" \
    --workers "$AESTHETIC_V4_WORKERS" \
    "${SCORE_EXTRA_ARGS[@]}" \
    --refresh
else
  if [[ -z "${PANGU_API_KEY:-}" ]]; then
    echo "PANGU_API_KEY is empty. Copy config/aesthetic-v4.env.example to config/aesthetic-v4.env and fill it, or run: npm run run:mock" >&2
    exit 2
  fi
  JUDGE_COMMAND="$PYTHON_BIN scripts/pangu_rubric_judge.py --base-url $PANGU_BASE_URL --prompt-version $PANGU_JUDGE_PROMPT_VERSION --model $PANGU_JUDGE_MODEL --output-mode $PANGU_JUDGE_OUTPUT_MODE --timeout $PANGU_JUDGE_TIMEOUT --max-tokens $PANGU_JUDGE_MAX_TOKENS"
  JUDGE_TIMEOUT="$((PANGU_JUDGE_TIMEOUT + 40))"

  echo "[aesthetic-v4] score with Pangu model backend ($PANGU_JUDGE_MODEL, output_mode=$PANGU_JUDGE_OUTPUT_MODE)"
  "$PYTHON_BIN" scripts/score_images.py \
    --input "$SCORE_INPUT" \
    --out "$RUN_DIR/scores.jsonl" \
    --cache "$RUN_DIR/score_cache.jsonl" \
    --backend command \
    --judge-command "$JUDGE_COMMAND" \
    --timeout "$JUDGE_TIMEOUT" \
    --viewport-selection "$AESTHETIC_V4_VIEWPORT_SELECTION" \
    --aggregate-strategy "$AESTHETIC_V4_AGGREGATE_STRATEGY" \
    --workers "$AESTHETIC_V4_WORKERS" \
    "${SCORE_EXTRA_ARGS[@]}" \
    --refresh
fi

if [[ "$AESTHETIC_V4_OUTPUT_JSON" == "on" ]]; then
  echo "[aesthetic-v4] export clean JSON"
  "$PYTHON_BIN" scripts/export_clean_html_score_json.py \
    --scores "$RUN_DIR/scores.jsonl" \
    --out-dir "$AESTHETIC_V4_JSON_OUT_DIR" \
    --index "$AESTHETIC_V4_JSON_INDEX"

  echo "[aesthetic-v4] validate clean JSON"
  "$PYTHON_BIN" scripts/validate_clean_json.py "$AESTHETIC_V4_JSON_INDEX"
fi

if [[ "$AESTHETIC_V4_OUTPUT_HTML" == "on" ]]; then
  echo "[aesthetic-v4] build report"
  "$PYTHON_BIN" scripts/build_aesthetic_v4_report.py \
    --scores "$RUN_DIR/scores.jsonl" \
    --out "$RUN_DIR/report.html" \
    --summary "$RUN_DIR/report.summary.json" \
    --csv "$RUN_DIR/scores.csv" \
    --score-breakdown "$AESTHETIC_V4_SCORE_BREAKDOWN"
fi

echo "[aesthetic-v4] done"
echo "scores: $RUN_DIR/scores.jsonl"
if [[ "$AESTHETIC_V4_OUTPUT_JSON" == "on" ]]; then
  echo "json index: $AESTHETIC_V4_JSON_INDEX"
fi
if [[ "$AESTHETIC_V4_OUTPUT_HTML" == "on" ]]; then
  echo "report: $RUN_DIR/report.html"
fi
