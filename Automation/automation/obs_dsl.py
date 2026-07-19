from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import AutomationConfig, safe_path_name
from .dsl import DslExtraction, dedupe_records, extract_fenced_blocks, is_complete_dsl, repair_and_extract
from .hdc import HdcClient, HdcError, format_command_failure
from .logger import get_logger


GEN_WIDGET_RESULT_RE = re.compile(r"genWidgetResult\s+result:(\S+)")
OBS_MD_URL_RE = re.compile(r"https?://[^\s]+\.myhuaweicloud\.com[^\s]+\.md[^\s]*")


@dataclass(frozen=True)
class ObsDslResult:
    extraction: DslExtraction
    url: str
    markdown_path: Path
    hilog_match_path: Path
    elapsed_seconds: float


class ObsDslCollector:
    def __init__(self, config: AutomationConfig, hdc: HdcClient):
        self.config = config
        self.hdc = hdc
        self._log = get_logger("obs_dsl", sn=config.safe_sn or "", log_dir=config.log_dir, debug=config.debug)

    def collect_after_query_sent(self, qid: str) -> ObsDslResult:
        started = time.monotonic()
        clear_result = self.hdc.shell("hilog", "-r", timeout=10, check=False)
        if clear_result.returncode != 0:
            self._log.warning("[%s] stage=OBS_HILOG_CLEAR_FAILED error=%s", qid, format_command_failure(clear_result))

        url, matched_line, match_path = self._wait_for_obs_url(qid)
        markdown = self._download_markdown(url)
        markdown_path = self._save_markdown(qid, markdown)
        extraction = parse_obs_markdown(qid, markdown)
        if not is_complete_dsl(extraction.records):
            raise TimeoutError(f"OBS DSL is incomplete for query {qid}: {markdown_path}")

        elapsed = time.monotonic() - started
        self._log.info(
            "[%s] stage=OBS_DSL_READY url=%s markdown=%s match=%s elapsed_ms=%d",
            qid,
            url,
            markdown_path,
            match_path,
            int(elapsed * 1000),
        )
        self._log.debug("[%s] stage=OBS_DSL_MATCH line=%s", qid, matched_line)
        return ObsDslResult(
            extraction=extraction,
            url=url,
            markdown_path=markdown_path,
            hilog_match_path=match_path,
            elapsed_seconds=elapsed,
        )

    def _wait_for_obs_url(self, qid: str) -> tuple[str, str, Path]:
        command = self.hdc.command(["shell", "hilog"])
        timeout = max(0.1, float(self.config.obs_hilog_timeout))
        deadline = time.monotonic() + timeout
        line_queue: queue.Queue[str | None] = queue.Queue()

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=self.hdc.env,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise HdcError(f"HDC executable not found: {self.hdc.executable}") from exc

        reader = threading.Thread(target=_read_process_lines, args=(process, line_queue), daemon=True)
        reader.start()
        recent_lines: list[str] = []

        try:
            while time.monotonic() <= deadline:
                try:
                    line = line_queue.get(timeout=0.5)
                except queue.Empty:
                    if process.poll() is not None:
                        break
                    continue
                if line is None:
                    break
                recent_lines.append(line.rstrip("\r\n"))
                if len(recent_lines) > 200:
                    recent_lines.pop(0)

                url = extract_obs_url(line)
                if url:
                    match_path = self._save_hilog_match(qid, line, recent_lines)
                    return url, line.rstrip("\r\n"), match_path

            timeout_path = self._save_hilog_snapshot(qid, "TIMEOUT", recent_lines)
            raise TimeoutError(f"OBS markdown URL not found in hilog for query {qid} after {timeout:g}s: {timeout_path}")
        finally:
            stop_process(process)
            reader.join(timeout=2)

    def _download_markdown(self, url: str) -> str:
        timeout = max(0.1, float(self.config.obs_download_timeout))
        with urllib.request.urlopen(url, timeout=timeout) as response:
            content = response.read()
        return content.decode("utf-8-sig", errors="replace")

    def _save_markdown(self, qid: str, markdown: str) -> Path:
        path = timestamped_artifact_path(self.config.obs_markdown_dir, qid, ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return path

    def _save_hilog_match(self, qid: str, matched_line: str, recent_lines: list[str]) -> Path:
        path = timestamped_artifact_path(self.config.obs_hilog_match_dir, qid, ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"qid: {qid}",
            f"command: {' '.join(self.hdc.command(['shell', 'hilog']))}",
            "",
            "MATCHED_LINE:",
            matched_line.rstrip(),
            "",
            "RECENT_LINES:",
        ]
        lines.extend(line.rstrip() for line in recent_lines)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return path

    def _save_hilog_snapshot(self, qid: str, reason: str, recent_lines: list[str]) -> Path:
        path = timestamped_artifact_path(self.config.obs_hilog_match_dir, f"{qid}-{reason.lower()}", ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"qid: {qid}",
            f"reason: {reason}",
            f"command: {' '.join(self.hdc.command(['shell', 'hilog']))}",
            "",
            "RECENT_LINES:",
        ]
        lines.extend(line.rstrip() for line in recent_lines)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return path


def _read_process_lines(process: subprocess.Popen[str], line_queue: queue.Queue[str | None]) -> None:
    try:
        if process.stdout is None:
            return
        for line in process.stdout:
            line_queue.put(line)
    finally:
        line_queue.put(None)


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def extract_obs_url(line: str) -> str | None:
    result_match = GEN_WIDGET_RESULT_RE.search(line)
    if result_match:
        candidate = result_match.group(1)
        url_match = OBS_MD_URL_RE.search(candidate)
        if url_match:
            return url_match.group(0)
        if candidate.startswith(("http://", "https://")):
            return candidate

    url_match = OBS_MD_URL_RE.search(line)
    if url_match:
        return url_match.group(0)
    return None


def parse_obs_markdown(qid: str, markdown: str) -> DslExtraction:
    genui_blocks = extract_fenced_blocks(markdown, "genui")
    source = "\n".join(genui_blocks).strip()
    records = repair_and_extract(source) if source else []

    if not is_complete_dsl(records):
        source = markdown
        records = repair_and_extract(markdown)

    return DslExtraction(qid=qid, records=dedupe_records(records), source_text=source)


def timestamped_artifact_path(directory: Path, qid: str, suffix: str) -> Path:
    timestamp = time.strftime("%Y%m%d%H%M%S")
    millis = int((time.time() % 1) * 1000)
    filename = f"{timestamp}{millis:03d}-{safe_path_name(qid)}{suffix}"
    return directory / filename
