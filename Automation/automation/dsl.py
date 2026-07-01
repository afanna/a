from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .ui_tree import UiTree


DSL_KEYWORDS = ("createSurface", "updateComponents", "updateDataModel", "v0.9")


@dataclass(frozen=True)
class DslExtraction:
    qid: str
    records: list[dict]
    source_text: str

    @property
    def found(self) -> bool:
        return bool(self.records)


class DslExtractor:
    def __init__(self, keywords: tuple[str, ...] = DSL_KEYWORDS):
        self.keywords = keywords

    def extract_from_tree(self, qid: str, tree: UiTree) -> DslExtraction:
        texts = [node.text for node in tree.nodes if node.text and any(k in node.text for k in self.keywords)]
        if not texts:
            return DslExtraction(qid=qid, records=[], source_text="")
        source = "\n".join(texts)
        records = self._parse_records(source)
        return DslExtraction(qid=qid, records=records, source_text=source)

    def save_jsonl(self, extraction: DslExtraction, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("[")
            for index, record in enumerate(extraction.records):
                if index > 0:
                    f.write(",\n")
                f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            f.write("]\n")
        return path

    def _parse_records(self, text: str) -> list[dict]:
        parsed_source = parse_json_records(text)
        if parsed_source:
            return parsed_source

        records: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not any(keyword in line for keyword in self.keywords):
                continue
            records.extend(parse_json_records(line))
        if records:
            return records

        for candidate in iter_json_candidates(text):
            if any(keyword in candidate for keyword in self.keywords):
                records.extend(parse_json_records(candidate))
        return records


def parse_json_records(text: str) -> list[dict]:
    text = strip_code_fence(text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|jsonl)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def iter_json_candidates(text: str):
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in "{[":
            if depth == 0:
                start = index
            depth += 1
        elif char in "}]":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : index + 1]
                start = None

