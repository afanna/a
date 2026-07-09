from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .math_utils import json_pointer_get, json_pointer_set
from .models import DslInfo, RequiredText


DISPLAY_COMPONENTS = {
    "checkbox",
    "choicepicker",
    "label",
    "radio",
    "richtext",
    "select",
    "subtitle",
    "tabcontent",
    "text",
    "button",
    "textfield",
    "textinput",
    "title",
    "toggle",
}
DISPLAY_FIELDS = ("content", "text", "label", "title", "subtitle", "placeholder")
COMPONENT_DISPLAY_FIELDS = {
    "button": ("content", "text", "label"),
    "checkbox": ("label",),
    "choicepicker": ("label", "title"),
    "radio": ("label", "text"),
    "select": ("label", "title", "placeholder", "value"),
    "tabcontent": ("title", "label"),
    "textfield": ("label", "text", "placeholder", "value"),
    "textinput": ("label", "text", "placeholder", "value"),
    "toggle": ("label",),
}
OPTION_FIELDS = ("label", "title", "text", "content", "value")
TEMPLATE_PATH_RE = re.compile(r"\$\{([^}]+)\}")
EXPRESSION_RE = re.compile(r"^\s*\{\{\s*(.*?)\s*\}\}\s*$")
EXPRESSION_DATA_RE = re.compile(r"\$__dataModel((?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)")


def load_dsl_info(path: Path | None) -> DslInfo:
    if path is None:
        return DslInfo(path=None, required_texts=[], data_model={}, component_count=0)
    if not path.exists():
        return DslInfo(
            path=path,
            required_texts=[],
            data_model={},
            component_count=0,
            warnings=[f"DSL 文件不存在：{path}"],
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return DslInfo(
            path=path,
            required_texts=[],
            data_model={},
            component_count=0,
            warnings=[f"DSL 文件读取失败：{path}：{exc}"],
        )
    messages = parse_dsl_messages(raw)
    data_model = build_data_model(messages)
    components = collect_components(messages)
    texts = extract_required_texts(components, data_model)
    warnings = [] if messages else [f"没有解析到有效 DSL 消息：{path}"]
    return DslInfo(path=path, required_texts=texts, data_model=data_model, component_count=len(components), warnings=warnings)


def parse_dsl_messages(raw: str) -> list[dict[str, Any]]:
    raw = raw.strip()
    if not raw:
        return []

    parsed = _loads_json(raw)
    if parsed is None:
        parsed = _loads_embedded_json(raw)
    if parsed is None:
        parsed = _loads_jsonl(raw)

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _loads_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _loads_embedded_json(text: str) -> Any | None:
    starts = [index for index in (text.find("["), text.find("{")) if index >= 0]
    if not starts:
        return None
    start = min(starts)
    end = text.rfind("]") if text[start] == "[" else text.rfind("}")
    if end <= start:
        return None
    return _loads_json(text[start : end + 1])


def _loads_jsonl(text: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = _loads_json(line)
        if isinstance(parsed, dict):
            messages.append(parsed)
    return messages


def build_data_model(messages: list[dict[str, Any]]) -> dict[str, Any]:
    model: dict[str, Any] = {}
    for message in messages:
        body = message.get("updateDataModel")
        if not isinstance(body, dict):
            continue
        path = str(body.get("path") or "/")
        value = body.get("value", {})
        updated = json_pointer_set(model, path, value)
        model = updated if isinstance(updated, dict) else {"value": updated}
    return model


def collect_components(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for message in messages:
        body = message.get("updateComponents")
        if not isinstance(body, dict):
            continue
        raw_components = body.get("components") or []
        if isinstance(raw_components, list):
            components.extend(item for item in raw_components if isinstance(item, dict))
    return components


def extract_required_texts(components: list[dict[str, Any]], data_model: dict[str, Any]) -> list[RequiredText]:
    required: list[RequiredText] = []
    seen: set[tuple[str, str | None]] = set()
    for component in components:
        component_type = normalize_component_type(component.get("component"))
        if component_type not in DISPLAY_COMPONENTS:
            continue
        component_id = str(component.get("id")) if component.get("id") is not None else None
        for field in display_fields_for(component_type):
            if field not in component:
                continue
            value = resolve_dynamic_string(component[field], data_model)
            add_required_texts(required, seen, value, component_type, field, component_id)
        for value, source in extract_option_texts(component, data_model):
            add_required_texts(required, seen, value, component_type, source, component_id)
    return required


def normalize_component_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw.rsplit(".", 1)[-1]


def display_fields_for(component_type: str) -> tuple[str, ...]:
    fields = COMPONENT_DISPLAY_FIELDS.get(component_type, DISPLAY_FIELDS)
    merged = list(fields)
    for field in DISPLAY_FIELDS:
        if field not in merged:
            merged.append(field)
    return tuple(merged)


def add_required_texts(
    required: list[RequiredText],
    seen: set[tuple[str, str | None]],
    value: Any,
    component_type: str,
    source: str,
    component_id: str | None,
) -> None:
    for text in split_display_text(value):
        key = (text, component_id)
        if key in seen:
            continue
        seen.add(key)
        required.append(RequiredText(text=text, source=f"{component_type}.{source}", component_id=component_id))


def extract_option_texts(component: dict[str, Any], data_model: dict[str, Any]) -> list[tuple[str, str]]:
    raw_options = component.get("options") or component.get("items")
    if isinstance(raw_options, dict):
        raw_options = json_pointer_get(data_model, str(raw_options.get("path") or "")) if "path" in raw_options else []
    values: list[tuple[str, str]] = []
    if not isinstance(raw_options, list):
        return values
    for index, option in enumerate(raw_options):
        if isinstance(option, (str, int, float, bool)):
            values.append((str(option), f"options[{index}]"))
            continue
        if not isinstance(option, dict):
            continue
        for field in OPTION_FIELDS:
            if field in option:
                values.append((resolve_dynamic_string(option[field], data_model), f"options[{index}].{field}"))
    return values


def resolve_dynamic_string(value: Any, data_model: dict[str, Any]) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, str):
        return resolve_template(value, data_model)
    if isinstance(value, dict):
        if "path" in value:
            found = json_pointer_get(data_model, str(value.get("path") or ""))
            return stringify_display_value(found)
        if value.get("call") == "formatString":
            args = value.get("args") if isinstance(value.get("args"), dict) else {}
            return resolve_dynamic_string(args.get("value", ""), data_model)
        if "value" in value:
            return resolve_dynamic_string(value.get("value"), data_model)
    return ""


def resolve_template(template: str, data_model: dict[str, Any]) -> str:
    expression = EXPRESSION_RE.match(template)
    if expression:
        return resolve_expression(expression.group(1), data_model)

    def replace_pointer(match: re.Match[str]) -> str:
        value = json_pointer_get(data_model, match.group(1))
        return stringify_display_value(value)

    text = TEMPLATE_PATH_RE.sub(replace_pointer, template)

    def replace_expression(match: re.Match[str]) -> str:
        value = json_pointer_get(data_model, data_model_expression_to_pointer(match.group(0)))
        return stringify_display_value(value)

    return EXPRESSION_DATA_RE.sub(replace_expression, text)


def resolve_expression(expression: str, data_model: dict[str, Any]) -> str:
    parts = split_expression_concat(expression)
    if not parts:
        return ""
    values: list[str] = []
    for part in parts:
        value = resolve_expression_part(part, data_model)
        if value is None:
            return ""
        values.append(value)
    return "".join(values)


def split_expression_concat(expression: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    in_string = False
    escaped = False
    for char in expression:
        if char == "\\" and in_string:
            escaped = not escaped
            buffer.append(char)
            continue
        if char == "'" and not escaped:
            in_string = not in_string
            buffer.append(char)
            continue
        escaped = False
        if char == "+" and not in_string:
            item = "".join(buffer).strip()
            if item:
                parts.append(item)
            buffer = []
            continue
        buffer.append(char)
    item = "".join(buffer).strip()
    if item:
        parts.append(item)
    return parts


def resolve_expression_part(part: str, data_model: dict[str, Any]) -> str | None:
    if len(part) >= 2 and part[0] == "'" and part[-1] == "'":
        return part[1:-1]
    if part.startswith("${") and part.endswith("}"):
        return stringify_display_value(json_pointer_get(data_model, part[2:-1]))
    if part.startswith("$__dataModel"):
        return stringify_display_value(json_pointer_get(data_model, data_model_expression_to_pointer(part)))
    if re.fullmatch(r"-?\d+(?:\.\d+)?", part):
        return part[:-2] if part.endswith(".0") else part
    if part in {"true", "false"}:
        return part
    return part if "$" not in part and "?" not in part and ":" not in part else None


def data_model_expression_to_pointer(expression: str) -> str:
    path = expression.removeprefix("$__dataModel")
    tokens = re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", path)
    parts = [name or index for name, index in tokens]
    return "/" + "/".join(parts) if parts else "/"


def stringify_display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(stringify_display_value(item) for item in value)
    if isinstance(value, dict):
        return " ".join(stringify_display_value(item) for item in value.values())
    return str(value)


def split_display_text(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    if _is_decorative_symbol(cleaned):
        return []
    return [cleaned]


def _is_decorative_symbol(text: str) -> bool:
    if any("\u4e00" <= char <= "\u9fff" or char.isalnum() for char in text):
        return False
    return len(text) <= 2
