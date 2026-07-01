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
            for record in extraction.records:
                f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return path

    def _parse_records(self, text: str) -> list[dict]:
        records: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not any(keyword in line for keyword in self.keywords):
                continue
            parsed = parse_json_object(line)
            if parsed is not None:
                records.append(parsed)
        if records:
            return records

        for candidate in iter_json_candidates(text):
            parsed = parse_json_object(candidate)
            if parsed is not None and any(keyword in candidate for keyword in self.keywords):
                records.append(parsed)
        return records


def parse_json_object(text: str) -> dict | None:
    text = strip_code_fence(text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|jsonl)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def iter_json_candidates(text: str):
    start_stack: list[int] = []
    for index, char in enumerate(text):
        if char == "{":
            start_stack.append(index)
        elif char == "}" and start_stack:
            start = start_stack.pop()
            yield text[start : index + 1]

