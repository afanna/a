from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .config import AutomationConfig
from .dsl import DSL_KEYWORDS, DslExtraction, DslExtractor, is_complete_dsl
from .hdc import HdcClient, HdcError
from .logger import get_logger
from .obs_dsl import ObsDslCollector
from .ui_tree import UiTree


@dataclass(frozen=True)
class QueryResult:
    qid: str
    dsl_path: Path
    extraction: DslExtraction


class XiaoyiClient:
    def __init__(
        self,
        config: AutomationConfig,
        hdc: HdcClient,
        extractor: DslExtractor | None = None,
        obs_collector: ObsDslCollector | None = None,
    ):
        self.config = config
        self.hdc = hdc
        self.extractor = extractor or DslExtractor()
        self.obs_collector = obs_collector or ObsDslCollector(config, hdc)
        self.dump_path = config.work_dir / "current_ui_tree.json"
        self.last_dsl_fingerprint: str | None = None
        self._log = get_logger("xiaoyi", sn=config.safe_sn or "", log_dir=config.log_dir, debug=config.debug)

    def dump_tree(self) -> UiTree:
        self.hdc.dump_layout(self.dump_path, self.config.remote_dump)
        try:
            return UiTree.from_file(self.dump_path)
        except (OSError, json.JSONDecodeError) as exc:
            raise HdcError(f"Failed to read dumped UI tree: {self.dump_path}") from exc

    def wait_ready(self) -> None:
        deadline = time.monotonic() + self.config.ready_timeout
        last_len = -1
        stable_count = 0

        while time.monotonic() <= deadline:
            tree = self.dump_tree()
            busy, _has_dsl, reply_len = tree.reply_state(DSL_KEYWORDS)
            if reply_len == last_len:
                stable_count += 1
            else:
                stable_count = 0
                last_len = reply_len

            # 必须同时满足：无生成中关键词 且 回复文本连续稳定，避免单轮轮询误判放行
            if tree.is_chat_ready() and not busy and stable_count >= 2:
                self._log.info("wait_ready done: busy=%s stable_count=%d reply_len=%d", busy, stable_count, reply_len)
                return
            time.sleep(self.config.poll_interval)
        self._log.error("wait_ready timeout after %.0fs", self.config.ready_timeout)
        raise TimeoutError("Timed out waiting for Xiaoyi chat UI to become ready and idle")

    def send_query(self, query: str) -> None:
        send_xy = self.prepare_query(query)
        self.click_send(send_xy)

    def prepare_query(self, query: str) -> tuple[int, int]:
        input_xy = self._ensure_input()
        self._clear_input(*input_xy)
        self.hdc.ui_input("inputText", *input_xy, query)
        tree = self.dump_tree()
        send = tree.locate_control("send")
        if not send:
            self._log.error("send_query: Send button not found")
            raise RuntimeError("Send button not found after text input")
        return send.center

    def click_send(self, send_xy: tuple[int, int]) -> None:
        self.hdc.ui_input("click", *send_xy)

    def collect_dsl_for_query(self, qid: str, query: str, *, max_attempts: int | None = None) -> QueryResult:
        t0 = time.monotonic()
        last_error: Exception | None = None
        attempts = max(1, int(max_attempts or self.config.query_max_attempts))
        for attempt in range(1, attempts + 1):
            try:
                self.wait_ready()
                extraction = self._send_query_and_collect_dsl(qid, query)
                self.last_dsl_fingerprint = dsl_fingerprint(extraction)
                dsl_path = self.config.dsl_path_for(qid)
                self.extractor.save_jsonl(extraction, dsl_path)
                self._log.info("[%s] stage=DSL_READY dsl=%s elapsed_ms=%d", qid, dsl_path.name, int((time.monotonic() - t0) * 1000))
                self.clear_context(qid)
                return QueryResult(qid=qid, dsl_path=dsl_path, extraction=extraction)
            except (TimeoutError, HdcError) as exc:
                last_error = exc
                self._log.error("[%s] stage=DSL_ATTEMPT_FAILED attempt=%d error=%s", qid, attempt, exc)
                if attempt < attempts:
                    continue
        raise TimeoutError(f"DSL not found for query {qid} after {attempts} attempts") from last_error

    def _send_query_and_collect_dsl(self, qid: str, query: str) -> DslExtraction:
        source = self.config.dsl_source
        if source in {"obs", "auto"}:
            return self._send_query_and_collect_obs(qid, query, allow_ui_fallback=source == "auto")
        if source == "ui":
            self.send_query(query)
            return self._collect_ui_dsl(qid)
        raise RuntimeError(f"Unsupported DSL source: {source}")

    def _send_query_and_collect_obs(self, qid: str, query: str, *, allow_ui_fallback: bool) -> DslExtraction:
        send_xy = self.prepare_query(query)
        stream = self.obs_collector.start_stream(qid)
        try:
            self.click_send(send_xy)
        except Exception:
            self.obs_collector.stop_stream(stream)
            raise

        try:
            result = self.obs_collector.collect_from_stream(
                qid,
                stream,
                accept_extraction=self._is_complete_new_extraction,
            )
        except TimeoutError as exc:
            if not allow_ui_fallback:
                raise
            self._log.error("[%s] stage=OBS_DSL_FAILED_FALLBACK_UI error=%s", qid, exc)
            return self._collect_ui_dsl(qid)
        except HdcError:
            raise
        except Exception as exc:
            raise TimeoutError(f"OBS DSL collection failed for query {qid}: {exc}") from exc
        self._wait_for_reply_stable(qid)
        return result.extraction

    def _collect_dsl_after_query_sent(self, qid: str) -> DslExtraction:
        source = self.config.dsl_source
        if source == "ui":
            return self._collect_ui_dsl(qid)
        if source == "obs":
            return self._collect_obs_dsl(qid)
        if source == "auto":
            try:
                return self._collect_obs_dsl(qid)
            except TimeoutError as exc:
                self._log.error("[%s] stage=OBS_DSL_FAILED_FALLBACK_UI error=%s", qid, exc)
                return self._collect_ui_dsl(qid)
        raise RuntimeError(f"Unsupported DSL source: {source}")

    def _collect_obs_dsl(self, qid: str) -> DslExtraction:
        try:
            result = self.obs_collector.collect_after_query_sent(
                qid,
                accept_extraction=self._is_complete_new_extraction,
            )
        except HdcError:
            raise
        except Exception as exc:
            raise TimeoutError(f"OBS DSL collection failed for query {qid}: {exc}") from exc
        return self._validate_obs_result_after_reply_stable(qid, result.extraction)

    def _collect_obs_dsl_from_stream(self, qid: str, stream) -> DslExtraction:
        try:
            result = self.obs_collector.collect_from_stream(qid, stream)
        except HdcError:
            raise
        except Exception as exc:
            raise TimeoutError(f"OBS DSL collection failed for query {qid}: {exc}") from exc
        return self._validate_obs_result_after_reply_stable(qid, result.extraction)

    def _validate_obs_result_after_reply_stable(self, qid: str, extraction: DslExtraction) -> DslExtraction:
        self._wait_for_reply_stable(qid)
        if not self._is_complete_new_extraction(extraction):
            raise TimeoutError(f"OBS DSL not found for query {qid}")
        return extraction

    def _collect_ui_dsl(self, qid: str) -> DslExtraction:
        deadline = time.monotonic() + self.config.query_attempt_timeout
        time.sleep(min(self.config.post_query_wait, max(0, deadline - time.monotonic())))
        self._scroll_down(check=False)
        return self._wait_and_extract(qid, deadline)

    def _wait_for_reply_stable(self, qid: str) -> None:
        deadline = time.monotonic() + self.config.query_attempt_timeout
        last_len = -1
        stable_count = 0

        while time.monotonic() <= deadline:
            tree = self.dump_tree()
            busy, _has_dsl, reply_len = tree.reply_state(DSL_KEYWORDS)
            if reply_len == last_len:
                stable_count += 1
            else:
                stable_count = 0
                last_len = reply_len

            # 必须同时满足：无生成中关键词 且 回复文本连续稳定，避免回复流式生成期间提前放行
            if not busy and stable_count >= 2:
                self._log.info(
                    "[%s] stage=REPLY_STABLE busy=%s stable_count=%d reply_len=%d",
                    qid,
                    busy,
                    stable_count,
                    reply_len,
                )
                return
            time.sleep(self.config.poll_interval)

        raise TimeoutError(f"Timed out waiting for Xiaoyi reply to become stable for query {qid}")

    def _ensure_input(self) -> tuple[int, int]:
        tree = self.dump_tree()
        candidate = tree.locate_control("input")
        if candidate:
            return candidate.center
        toggle = tree.locate_control("keyboard_toggle")
        if not toggle:
            self._log.error("_ensure_input: no input or keyboard toggle found")
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

    def clear_context(self, qid: str) -> None:
        if not self.config.context_clear_enabled:
            return
        points = self.config.context_clear_points
        if not points:
            self._log.error("[%s] stage=CONTEXT_CLEAR_SKIPPED error=missing coordinates", qid)
            return

        for index, (x, y) in enumerate(points, 1):
            try:
                self.hdc.ui_input("click", x, y)
                time.sleep(self.config.context_clear_wait)
                self._log.info(
                    "[%s] stage=CONTEXT_CLEAR_TAP step=%d/%d x=%d y=%d wait=%.1fs",
                    qid,
                    index,
                    len(points),
                    x,
                    y,
                    self.config.context_clear_wait,
                )
            except HdcError as exc:
                self._log.error("[%s] stage=CONTEXT_CLEAR_FAILED step=%d/%d x=%d y=%d error=%s", qid, index, len(points), x, y, exc)

    def _wait_and_extract(self, qid: str, deadline: float) -> DslExtraction:
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

            should_extract = has_dsl and not busy and stable_count >= 2
            if should_extract:
                extraction = self.extractor.extract_from_tree(qid, tree)
                if self._is_complete_new_extraction(extraction):
                    return extraction
            time.sleep(self.config.poll_interval)

        if latest_tree is not None:
            extraction = self.extractor.extract_from_tree(qid, latest_tree)
            if self._is_complete_new_extraction(extraction):
                return extraction
        return self._scroll_scan_for_dsl(qid)

    def _scroll_scan_for_dsl(self, qid: str) -> DslExtraction:
        deadline = time.monotonic() + self.config.scroll_limit * self.config.poll_interval
        for _ in range(self.config.scroll_limit):
            if time.monotonic() > deadline:
                break
            self._scroll_down(check=False)
            tree = self.dump_tree()
            extraction = self.extractor.extract_from_tree(qid, tree)
            if self._is_complete_new_extraction(extraction):
                return extraction
            time.sleep(self.config.poll_interval)
        raise TimeoutError(f"DSL not found for query {qid}")

    def _scroll_down(self, check: bool = True) -> None:
        self.hdc.ui_input("swipe", 600, 1800, 600, 500, 600, check=check)

    def _is_complete_new_extraction(self, extraction: DslExtraction) -> bool:
        if not extraction.found:
            return False
        if not is_complete_dsl(extraction.records):
            return False
        fingerprint = dsl_fingerprint(extraction)
        return fingerprint != self.last_dsl_fingerprint


def dsl_fingerprint(extraction: DslExtraction) -> str:
    return json.dumps(extraction.records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

