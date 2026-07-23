from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .math_utils import json_pointer_get, json_pointer_set
from .models import DslComponentBox, DslInfo, Rect, RequiredText


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
    root_id = infer_root_id(messages, components)
    surface_width, surface_height = infer_surface_size(messages, components, root_id)
    geometry_boxes, geometry_warnings = estimate_geometry_boxes(
        components=components,
        data_model=data_model,
        root_id=root_id,
        surface_width=surface_width,
        surface_height=surface_height,
    )
    warnings = [] if messages else [f"没有解析到有效 DSL 消息：{path}"]
    warnings.extend(geometry_warnings)
    return DslInfo(
        path=path,
        required_texts=texts,
        data_model=data_model,
        component_count=len(components),
        components=components,
        messages=messages,
        root_id=root_id,
        surface_width=surface_width,
        surface_height=surface_height,
        geometry_boxes=geometry_boxes,
        warnings=warnings,
    )


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


def infer_root_id(messages: list[dict[str, Any]], components: list[dict[str, Any]]) -> str | None:
    known = {str(component.get("id")) for component in components if component.get("id") is not None}
    for message in messages:
        body = message.get("updateComponents")
        if not isinstance(body, dict):
            continue
        root = body.get("root")
        if isinstance(root, str) and root in known:
            return root
    if "root" in known:
        return "root"
    child_ids: set[str] = set()
    for component in components:
        children = component.get("children")
        if isinstance(children, list):
            child_ids.update(str(child) for child in children if isinstance(child, str))
        elif isinstance(children, dict) and isinstance(children.get("componentId"), str):
            child_ids.add(str(children["componentId"]))
    candidates = [str(component.get("id")) for component in components if component.get("id") is not None and str(component.get("id")) not in child_ids]
    return candidates[0] if candidates else None


def infer_surface_size(
    messages: list[dict[str, Any]], components: list[dict[str, Any]], root_id: str | None
) -> tuple[float | None, float | None]:
    width: float | None = None
    height: float | None = None
    for message in messages:
        body = message.get("createSurface")
        if not isinstance(body, dict):
            continue
        width = numeric_style_value(body.get("width"))
        height = numeric_style_value(body.get("height"))
        if width and height:
            return width, height
    root = next((component for component in components if component.get("id") == root_id), None)
    styles = root.get("styles") if isinstance(root, dict) and isinstance(root.get("styles"), dict) else {}
    width = numeric_style_value(styles.get("width"))
    height = numeric_style_value(styles.get("height"))
    return width, height


def estimate_geometry_boxes(
    components: list[dict[str, Any]],
    data_model: dict[str, Any],
    root_id: str | None,
    surface_width: float | None,
    surface_height: float | None,
) -> tuple[list[DslComponentBox], list[str]]:
    if not components or root_id is None:
        return [], ["DSL 几何估算跳过：缺少 root 组件。"]
    by_id = {str(component.get("id")): component for component in components if component.get("id") is not None}
    if root_id not in by_id:
        return [], [f"DSL 几何估算跳过：root 组件不存在：{root_id}。"]
    root = by_id[root_id]
    root_styles = styles_of(root)
    width = surface_width or numeric_style_value(root_styles.get("width")) or 160.0
    height = surface_height or numeric_style_value(root_styles.get("height")) or 160.0
    boxes: list[DslComponentBox] = []
    warnings: list[str] = []
    visiting: set[str] = set()

    def visit(component_id: str, rect: Rect) -> None:
        if component_id in visiting:
            warnings.append(f"DSL 几何估算跳过循环引用：{component_id}。")
            return
        component = by_id.get(component_id)
        if component is None:
            warnings.append(f"DSL 几何估算发现缺失 children 引用：{component_id}。")
            return
        visiting.add(component_id)
        component_type = normalize_component_type(component.get("component"))
        styles = styles_of(component)
        text = first_component_text(component, data_model)
        font_size = numeric_style_value(styles.get("fontSize"))
        boxes.append(
            DslComponentBox(
                component_id=component_id,
                component_type=component_type,
                bbox=rect,
                font_size=font_size,
                text=text or None,
                styles=styles,
            )
        )
        child_ids = children_of(component)
        if child_ids:
            layout_children(component, child_ids, rect)
        visiting.remove(component_id)

    def layout_children(component: dict[str, Any], child_ids: list[str], rect: Rect) -> None:
        component_type = normalize_component_type(component.get("component"))
        styles = styles_of(component)
        padding = box_edges(styles.get("padding"))
        content_x = rect.x + padding["left"]
        content_y = rect.y + padding["top"]
        content_w = max(0.0, rect.width - padding["left"] - padding["right"])
        content_h = max(0.0, rect.height - padding["top"] - padding["bottom"])
        item_margin = numeric_style_value(component.get("itemMargin")) or numeric_style_value(styles.get("itemMargin")) or 0.0
        if component_type == "row":
            layout_linear(child_ids, "row", content_x, content_y, content_w, content_h, item_margin, styles)
        elif component_type == "column":
            layout_linear(child_ids, "column", content_x, content_y, content_w, content_h, item_margin, styles)
        elif component_type == "stack":
            for child_id in child_ids:
                child = by_id.get(child_id)
                if child is None:
                    warnings.append(f"DSL 几何估算发现缺失 children 引用：{child_id}。")
                    continue
                child_w, child_h = component_size(child, content_w, content_h)
                child_rect = Rect(content_x + max(0.0, (content_w - child_w) / 2), content_y + max(0.0, (content_h - child_h) / 2), child_w, child_h)
                visit(child_id, apply_margin(child_rect, box_edges(styles_of(child).get("margin"))))
        else:
            layout_linear(child_ids, "column", content_x, content_y, content_w, content_h, item_margin, styles)

    def layout_linear(
        child_ids: list[str],
        axis: str,
        x: float,
        y: float,
        width: float,
        height: float,
        gap: float,
        parent_styles: dict[str, Any],
    ) -> None:
        sizes: dict[str, tuple[float, float]] = {}
        fixed_main = 0.0
        weighted: list[str] = []
        for child_id in child_ids:
            child = by_id.get(child_id)
            if child is None:
                warnings.append(f"DSL 几何估算发现缺失 children 引用：{child_id}。")
                continue
            child_styles = styles_of(child)
            weight = numeric_style_value(child_styles.get("layoutWeight"))
            if weight and weight > 0:
                weighted.append(child_id)
                sizes[child_id] = (0.0, 0.0)
                continue
            child_w, child_h = component_size(child, width, height)
            sizes[child_id] = (child_w, child_h)
            fixed_main += child_w if axis == "row" else child_h
        gaps_total = gap * max(0, len(child_ids) - 1)
        available_main = width if axis == "row" else height
        remaining = max(0.0, available_main - fixed_main - gaps_total)
        weight_sum = sum(numeric_style_value(styles_of(by_id[item]).get("layoutWeight")) or 1.0 for item in weighted)
        for child_id in weighted:
            child = by_id[child_id]
            share = remaining * ((numeric_style_value(styles_of(child).get("layoutWeight")) or 1.0) / max(weight_sum, 1e-6))
            if axis == "row":
                sizes[child_id] = (share, component_size(child, share, height)[1])
            else:
                sizes[child_id] = (component_size(child, width, share)[0], share)
        cursor = x if axis == "row" else y
        justify = str(parent_styles.get("justifyContent") or "start").lower()
        used_main = sum((sizes.get(child_id, (0.0, 0.0))[0 if axis == "row" else 1]) for child_id in child_ids) + gaps_total
        if justify in {"center", "centre"}:
            cursor += max(0.0, (available_main - used_main) / 2)
        elif justify in {"end", "flexend", "flex-end"}:
            cursor += max(0.0, available_main - used_main)
        for child_id in child_ids:
            if child_id not in sizes:
                continue
            child = by_id[child_id]
            child_w, child_h = sizes[child_id]
            align = str(parent_styles.get("alignItems") or "start").lower()
            if axis == "row":
                child_x = cursor
                child_y = aligned_cross_position(y, height, child_h, align)
                cursor += child_w + gap
            else:
                child_x = aligned_cross_position(x, width, child_w, align)
                child_y = cursor
                cursor += child_h + gap
            visit(child_id, apply_margin(Rect(child_x, child_y, child_w, child_h), box_edges(styles_of(child).get("margin"))))

    def component_size(component: dict[str, Any], parent_w: float, parent_h: float) -> tuple[float, float]:
        styles = styles_of(component)
        component_type = normalize_component_type(component.get("component"))
        width_value = dimension_value(styles.get("width"), parent_w)
        height_value = dimension_value(styles.get("height"), parent_h)
        text = first_component_text(component, data_model)
        font_size = numeric_style_value(styles.get("fontSize")) or 14.0
        if width_value is None:
            if component_type in {"text", "button"} and text:
                width_value = min(parent_w, max(font_size * 2, len(text) * font_size * 0.58))
            elif component_type in {"image", "divider"}:
                width_value = min(parent_w, 24.0)
            else:
                width_value = parent_w
        if height_value is None:
            if component_type in {"text", "button"}:
                max_lines = numeric_style_value(styles.get("maxLines")) or 1.0
                height_value = font_size * 1.25 * max_lines
            elif component_type == "divider":
                height_value = dimension_value(styles.get("height"), parent_h) or parent_h
            elif component_type == "image":
                height_value = min(parent_h, width_value)
            else:
                height_value = parent_h
        return max(0.0, width_value), max(0.0, height_value)

    visit(root_id, Rect(0.0, 0.0, width, height))
    return boxes, warnings


def styles_of(component: dict[str, Any]) -> dict[str, Any]:
    styles = component.get("styles")
    return styles if isinstance(styles, dict) else {}


def children_of(component: dict[str, Any]) -> list[str]:
    children = component.get("children")
    if isinstance(children, list):
        return [str(child) for child in children if isinstance(child, str)]
    if isinstance(children, dict) and isinstance(children.get("componentId"), str):
        return [str(children["componentId"])]
    return []


def first_component_text(component: dict[str, Any], data_model: dict[str, Any]) -> str:
    component_type = normalize_component_type(component.get("component"))
    for field in display_fields_for(component_type):
        if field in component:
            value = resolve_dynamic_string(component[field], data_model)
            texts = split_display_text(value)
            if texts:
                return texts[0]
    return ""


def numeric_style_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith(("vp", "dp", "px")):
            text = text[:-2]
        try:
            return float(text)
        except ValueError:
            return None
    return None


def dimension_value(value: Any, parent: float) -> float | None:
    if isinstance(value, str) and value.strip().endswith("%"):
        try:
            return parent * float(value.strip()[:-1]) / 100.0
        except ValueError:
            return None
    return numeric_style_value(value)


def box_edges(value: Any) -> dict[str, float]:
    if isinstance(value, (int, float)):
        scalar = float(value)
        return {"top": scalar, "right": scalar, "bottom": scalar, "left": scalar}
    if isinstance(value, str):
        scalar = numeric_style_value(value)
        if scalar is not None:
            return {"top": scalar, "right": scalar, "bottom": scalar, "left": scalar}
    if isinstance(value, dict):
        top = numeric_style_value(value.get("top"))
        right = numeric_style_value(value.get("right"))
        bottom = numeric_style_value(value.get("bottom"))
        left = numeric_style_value(value.get("left"))
        horizontal = numeric_style_value(value.get("horizontal"))
        vertical = numeric_style_value(value.get("vertical"))
        all_value = numeric_style_value(value.get("all"))
        return {
            "top": top if top is not None else vertical if vertical is not None else all_value or 0.0,
            "right": right if right is not None else horizontal if horizontal is not None else all_value or 0.0,
            "bottom": bottom if bottom is not None else vertical if vertical is not None else all_value or 0.0,
            "left": left if left is not None else horizontal if horizontal is not None else all_value or 0.0,
        }
    return {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0}


def aligned_cross_position(origin: float, available: float, size: float, align: str) -> float:
    if align in {"center", "middle"}:
        return origin + max(0.0, (available - size) / 2)
    if align in {"end", "right", "bottom", "flexend", "flex-end"}:
        return origin + max(0.0, available - size)
    return origin


def apply_margin(rect: Rect, margin: dict[str, float]) -> Rect:
    return Rect(
        rect.x + margin["left"],
        rect.y + margin["top"],
        max(0.0, rect.width - margin["left"] - margin["right"]),
        max(0.0, rect.height - margin["top"] - margin["bottom"]),
    )


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
