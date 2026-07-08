"""DSL Extractor.

Parses the card DSL (JSON) and provides an AST walker for
structural analysis (Phase 3).

DSL is auxiliary -- screenshots always win when they conflict.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def load_dsl(dsl_path: str) -> tuple[dict[str, Any] | None, str]:
    """Load DSL JSON from file path.

    Returns:
        (dsl_tree, status) where status is one of:
        - "OK": Successfully loaded
        - "NOT_PROVIDED": No DSL path provided
        - "FILE_NOT_FOUND": File doesn't exist
        - "PARSE_FAILED": JSON parsing error
    """
    if not dsl_path:
        return None, "NOT_PROVIDED"

    path = Path(dsl_path)
    if not path.exists():
        logger.warning("DSL file not found: %s", dsl_path)
        return None, "FILE_NOT_FOUND"

    with open(path, "r", encoding="utf-8") as f:
        try:
            dsl_tree = json.load(f)
            return dsl_tree, "OK"
        except json.JSONDecodeError as e:
            logger.error("Failed to parse DSL JSON: %s", e)
            return None, "PARSE_FAILED"


def walk_dsl(
    node: Any,
    visitor: Callable[[Any, int], None],
    depth: int = 0,
) -> None:
    """Recursively walk a DSL tree, calling visitor(node, depth) at each node.

    Handles both dict and list structures.
    """
    if isinstance(node, dict):
        visitor(node, depth)
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                walk_dsl(value, visitor, depth + 1)
    elif isinstance(node, list):
        for item in node:
            walk_dsl(item, visitor, depth)


def get_max_nesting_depth(dsl_tree: dict[str, Any]) -> int:
    """Calculate the maximum nesting depth of a DSL tree."""
    max_depth = 0

    def _visitor(node: Any, depth: int) -> None:
        nonlocal max_depth
        if depth > max_depth:
            max_depth = depth

    walk_dsl(dsl_tree, _visitor)
    return max_depth


def find_empty_containers(dsl_tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Find container nodes with no children."""
    empty: list[dict[str, Any]] = []

    def _visitor(node: Any, depth: int) -> None:
        if isinstance(node, dict):
            children = node.get("children", node.get("items", []))
            # Only flag nodes that explicitly declare a children/items key
            has_children_key = "children" in node or "items" in node
            if has_children_key and isinstance(children, list) and len(children) == 0:
                if "type" in node or "component" in node:
                    empty.append(node)

    walk_dsl(dsl_tree, _visitor)
    return empty
