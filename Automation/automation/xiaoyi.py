from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .config import AutomationConfig
from .dsl import DSL_KEYWORDS, DslExtraction, DslExtractor
from .hdc import HdcClient
from .ui_tree import UiTree


@dataclass(frozen=True)
class QueryResult:
    qid: str
    dsl_path: Path
    extraction: DslExtraction


class XiaoyiClient:
    def __init__(self, config: AutomationConfig, hdc: HdcClient, extractor: DslExtractor | None = None):
        self.config = config
        self.hdc = hdc
        self.extractor = extractor or DslExtractor()
        self.dump_path = config.work_dir / "current_ui_tree.json"

    def dump_tree(self) -> UiTree:
        self.hdc.dump_layout(self.dump_path, self.config.remote_dump)
        return UiTree.from_file(self.dump_path)

    def wait_ready(self) -> None:
        deadline = time.monotonic() + self.config.ready_timeout
        while time.monotonic() <= deadline:
            tree = self.dump_tree()
            if tree.is_chat_ready():
                return
            time.sleep(self.config.poll_interval)
        raise TimeoutError("Timed out waiting for Xiaoyi chat UI to become ready")

    def send_query(self, query: str) -> None:
        input_xy = self._ensure_input()
        self._clear_input(*input_xy)
        self.hdc.ui_input("inputText", *input_xy, query)
        tree = self.dump_tree()
        send = tree.locate_control("send")
        if not send:
            raise RuntimeError("Send button not found after text input")
        self.hdc.ui_input("click", *send.center)

    def collect_dsl_for_query(self, qid: str, query: str) -> QueryResult:
        self.wait_ready()
        self.send_query(query)
        extraction = self._wait_and_extract(qid)
        dsl_path = self.config.dsl_dir / f"{qid}.jsonl"
        self.extractor.save_jsonl(extraction, dsl_path)
        return QueryResult(qid=qid, dsl_path=dsl_path, extraction=extraction)

    def _ensure_input(self) -> tuple[int, int]:
        tree = self.dump_tree()
        candidate = tree.locate_control("input")
        if candidate:
            return candidate.center
        toggle = tree.locate_control("keyboard_toggle")
        if not toggle:
            raise RuntimeError("Neither text input nor keyboard toggle was found")
        self.hdc.ui_input("click", *toggle.center)
        tree = self.dump_tree()
        candidate = tree.locate_control("input")
        if not candidate:
            raise RuntimeError("Text input was not found after clicking keyboard toggle")
        return candidate.center

    def _clear_input(self, x: int, y: int) -> None:
        self.hdc.ui_input("click", x, y)
        self.hdc.ui_input("keyEvent", 2072, 2017, check=False)
        self.hdc.ui_input("keyEvent", 2055, check=False)

    def _wait_and_extract(self, qid: str) -> DslExtraction:
        sent_at = time.monotonic()
        deadline = sent_at + self.config.reply_timeout
        last_len = -1
        stable_count = 0
        latest_tree: UiTree | None = None

        while time.monotonic() <= deadline:
            tree = self.dump_tree()
            latest_tree = tree
            busy, has_dsl, reply_len = tree.reply_state(DSL_KEYWORDS)
            if reply_len == last_len:
                stable_count += 1
            else:
                stable_count = 0
                last_len = reply_len

            enough_time = time.monotonic() - sent_at >= self.config.extract_delay
            if enough_time and has_dsl and not busy and stable_count >= 1:
                extraction = self.extractor.extract_from_tree(qid, tree)
                if extraction.found:
                    return extraction
            time.sleep(self.config.poll_interval)

        if latest_tree is not None:
            extraction = self.extractor.extract_from_tree(qid, latest_tree)
            if extraction.found:
                return extraction
        return self._scroll_scan_for_dsl(qid)

    def _scroll_scan_for_dsl(self, qid: str) -> DslExtraction:
        for _ in range(self.config.scroll_limit):
            self.hdc.ui_input("swipe", 600, 1800, 600, 500, 600, check=False)
            tree = self.dump_tree()
            extraction = self.extractor.extract_from_tree(qid, tree)
            if extraction.found:
                return extraction
        raise TimeoutError(f"DSL not found for query {qid}")

