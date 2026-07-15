from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .arkts import ArkTsRunner
from .card_crop import CardCropper, load_card_crop_config
from .config import AutomationConfig
from .hdc import HdcClient, HdcError
from .hilog import HilogCollector
from .logger import get_logger
from .queries import QueryCase, load_queries
from .xiaoyi import QueryResult, XiaoyiClient


@dataclass(frozen=True)
class RenderResult:
    qid: str
    dsl_path: Path
    screenshot_path: Path
    card_path: Path | None = None


class AutomationPipeline:
    def __init__(self, config: AutomationConfig, aesthetics_config=None):
        self.config = config
        self._log = get_logger("pipeline", sn=config.safe_sn or "", log_dir=config.log_dir, debug=config.debug)
        hdc_log = get_logger("hdc", sn=config.safe_sn or "", log_dir=config.log_dir, debug=config.debug)
        self.hdc = HdcClient(config.hdc, sn=config.sn, logger=hdc_log)
        self.xiaoyi = XiaoyiClient(config, self.hdc)
        self.arkts = ArkTsRunner(config, self.hdc)
        self.hilog = HilogCollector(config, self.hdc)
        self.card_cropper = self._create_card_cropper() if self._should_crop_cards() else None

    def run_one(self, case: QueryCase) -> RenderResult:
        """Run one query through DSL extraction, render, screenshot, and card crop."""
        query_result = self.xiaoyi.collect_dsl_for_query(case.qid, case.query)
        screenshot = self.arkts.render(case.qid, query_result.dsl_path)
        card_path = self._crop_card(case.qid, screenshot)
        self._delete_intermediate_screenshot(case.qid, screenshot)
        return RenderResult(case.qid, query_result.dsl_path, screenshot, card_path)

    def run_batch(self, queries_path: Path | None = None) -> list[RenderResult]:
        """Run all queries, then render screenshots and crop cards."""
        t0 = time.monotonic()
        cases = load_queries(queries_path or self.config.queries_path)

        dsl_fail = 0
        query_results = self.collect_dsls(queries_path, log_summary=False)
        dsl_fail = len(cases) - len(query_results)

        render_results = self.render_dsl_files(
            [result.dsl_path for result in query_results],
            log_summary=False,
        )
        render_fail = len(query_results) - len(render_results)

        total_elapsed = time.monotonic() - t0
        self._log.info("=" * 60)
        self._log.info(
            "BATCH SUMMARY: total=%d dsl_ok=%d dsl_fail=%d render_ok=%d render_fail=%d card_ok=%d card_fail=%d total_time=%.1fs",
            len(cases),
            len(query_results),
            dsl_fail,
            len(render_results),
            render_fail,
            sum(1 for result in render_results if result.card_path is not None),
            sum(1 for result in render_results if result.card_path is None),
            total_elapsed,
        )
        self._log.info("=" * 60)
        return render_results

    def collect_dsls(self, queries_path: Path | None = None, *, log_summary: bool = True) -> list[QueryResult]:
        """Send all queries and save DSL files without rendering."""
        t0 = time.monotonic()
        cases = load_queries(queries_path or self.config.queries_path)
        query_results: list[QueryResult] = []
        failed = 0
        for case in cases:
            try:
                query_results.append(self.xiaoyi.collect_dsl_for_query(case.qid, case.query))
            except (TimeoutError, HdcError) as exc:
                failed += 1
                self._log.error("DSL failed: qid=%s error=%s", case.qid, exc)
                self._capture_failure_hilog(case.qid)
                continue

        if log_summary:
            self._log.info(
                "DSL SUMMARY: total=%d ok=%d failed=%d total_time=%.1fs",
                len(cases),
                len(query_results),
                failed,
                time.monotonic() - t0,
            )
        return query_results

    def render_dsl_dir(self, dsl_dir: Path | None = None) -> list[RenderResult]:
        """Render every DSL file under a directory, then screenshot and optionally crop."""
        directory = dsl_dir or self.config.dsl_dir
        dsl_files = sorted(directory.glob("*.jsonl"))
        if not dsl_files:
            self._log.error("No DSL files found: %s", directory)
            return []
        return self.render_dsl_files(dsl_files)

    def render_dsl_files(
        self,
        dsl_files: list[Path],
        *,
        log_summary: bool = True,
    ) -> list[RenderResult]:
        t0 = time.monotonic()
        render_fail = 0
        render_results: list[RenderResult] = []
        for dsl_path in dsl_files:
            qid = qid_from_dsl_path(dsl_path, self.config.safe_sn)
            try:
                screenshot = self.arkts.render(qid, dsl_path)
            except Exception as exc:
                render_fail += 1
                self._log.error("Render failed: qid=%s dsl=%s error=%s", qid, dsl_path, exc)
                continue
            card_path = self._crop_card(qid, screenshot)
            self._delete_intermediate_screenshot(qid, screenshot)
            render_results.append(RenderResult(qid, dsl_path, screenshot, card_path))

        if log_summary:
            self._log.info(
                "RENDER SUMMARY: total=%d ok=%d failed=%d card_ok=%d card_fail=%d total_time=%.1fs",
                len(dsl_files),
                len(render_results),
                render_fail,
                sum(1 for result in render_results if result.card_path is not None),
                sum(1 for result in render_results if result.card_path is None),
                time.monotonic() - t0,
            )
        return render_results

    def _should_crop_cards(self) -> bool:
        return self.config.enable_card_crop

    def _create_card_cropper(self) -> CardCropper:
        config_path = self.config.card_crop_config or self.config.default_card_crop_config_path
        return CardCropper(load_card_crop_config(config_path))

    def _capture_failure_hilog(self, qid: str) -> None:
        if not self.config.hilog_on_dsl_failure:
            return
        try:
            result = self.hilog.capture(qid)
        except Exception as exc:
            self._log.error("Hilog capture failed: qid=%s error=%s", qid, exc)
            return
        self._log.info(
            "Hilog captured: qid=%s path=%s elapsed=%.1fs",
            qid,
            result.path,
            result.elapsed_seconds,
        )

    def _crop_card(self, qid: str, screenshot: Path) -> Path | None:
        if not self.card_cropper:
            return None

        try:
            result = self.card_cropper.crop(
                screenshot,
                self.config.output_dir,
                output_path=self.config.card_screenshot_path_for(qid),
                debug=self.config.card_crop_debug,
                debug_dir=self.config.card_crop_debug_dir,
            )
        except Exception as exc:
            self._log.error("Card crop failed: qid=%s screenshot=%s error=%s", qid, screenshot, exc)
            return None

        self._log.info(
            "Card crop done: qid=%s type=%s box=%s output=%s",
            qid,
            result.card_type,
            result.box,
            result.card_path,
        )
        return result.card_path

    def _delete_intermediate_screenshot(self, qid: str, screenshot: Path) -> None:
        try:
            screenshot.unlink(missing_ok=True)
        except OSError as exc:
            self._log.error("Failed to delete intermediate screenshot: qid=%s screenshot=%s error=%s", qid, screenshot, exc)
            return
        self._log.info("Intermediate screenshot deleted: qid=%s screenshot=%s", qid, screenshot)


def qid_from_dsl_path(path: Path, safe_sn: str | None = None) -> str:
    qid = path.stem
    if safe_sn and qid.startswith(f"{safe_sn}_"):
        return qid[len(safe_sn) + 1 :]
    return qid
