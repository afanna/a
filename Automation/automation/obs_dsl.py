from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from .config import AutomationConfig, safe_path_name
from .dsl import DslExtraction, dedupe_records, extract_fenced_blocks, is_complete_dsl, repair_and_extract
from .hdc import HdcClient, HdcError, format_command_failure
from .logger import get_logger


RESULT_FIELD_URL_RE = re.compile(r'"result"\s*:\s*"(?P<url>https?://(?:\\.|[^"\\])*)"', re.I)
GEN_WIDGET_RESULT_RE = re.compile(
    r'genWidgetResult\s+result:\s*(?:"(?P<quoted>https?://(?:\\.|[^"\\])*)"|(?P<bare>https?://\S+))',
    re.I,
)
OBS_MD_URL_RE = re.compile(r"https?://[^\s\"<>]+?\.myhuaweicloud\.com[^\s\"<>]*?\.md(?:\?[^\s\"<>]*)?", re.I)
# hilog 日志可能在 URL 后紧跟包裹符号，提取后统一剥离
_URL_TRAILING_STRIP = ")]}>,;'\"\\"
# OBS 签名链接必须以完整的 64 位十六进制签名结尾，否则视为 hilog 行过长被截断
OBS_SIGNATURE_RE = re.compile(r"X-Amz-Signature=[0-9a-fA-F]{64}$")
# 跨 query 持久化的已见 URL 文件，命中即视为残存旧链接拒绝下载
SEEN_URLS_FILENAME = "seen_urls.txt"
_SEEN_URLS_MAX_LINES = 10000
_SEEN_URLS_KEEP_LINES = 5000


def is_complete_obs_url(url: str) -> bool:
    """带签名参数的 OBS 链接必须包含完整签名；截断链接下载必然 403，应跳过等待完整输出。"""
    if "X-Amz-" not in url:
        return True
    return bool(OBS_SIGNATURE_RE.search(url))


def is_obs_markdown_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc.endswith(".myhuaweicloud.com"):
        return False
    if not parsed.path.endswith(".md"):
        return False
    return is_complete_obs_url(url)


@dataclass(frozen=True)
class ObsDslResult:
    extraction: DslExtraction
    url: str
    markdown_path: Path
    hilog_match_path: Path
    elapsed_seconds: float


@dataclass
class ObsHilogStream:
    process: subprocess.Popen[str]
    reader: threading.Thread
    line_queue: queue.Queue[str | None]
    recent_lines: list[str]
    started: float


class ObsDslCollector:
    def __init__(self, config: AutomationConfig, hdc: HdcClient):
        self.config = config
        self.hdc = hdc
        self._log = get_logger("obs_dsl", sn=config.safe_sn or "", log_dir=config.log_dir, debug=config.debug)
        # 跨 query 共享的已见 URL 集合，懒加载自 seen_urls.txt
        self._seen_urls: set[str] | None = None

    def _seen_urls_path(self) -> Path:
        # 跟随 obs_hilog 目录；多设备并行时自动按 SN 隔离，无跨进程竞争
        return self.config.obs_hilog_match_dir / SEEN_URLS_FILENAME

    def _load_seen_urls(self) -> set[str]:
        if self._seen_urls is not None:
            return self._seen_urls
        path = self._seen_urls_path()
        urls: set[str] = set()
        if path.is_file():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > _SEEN_URLS_MAX_LINES:
                lines = lines[-_SEEN_URLS_KEEP_LINES:]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            urls = {line.strip() for line in lines if line.strip()}
        self._seen_urls = urls
        return urls

    def _record_seen_url(self, url: str) -> None:
        seen = self._load_seen_urls()
        if url in seen:
            return
        seen.add(url)
        path = self._seen_urls_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(url + "\n")

    def collect_after_query_sent(
        self,
        qid: str,
        *,
        accept_extraction: Callable[[DslExtraction], bool] | None = None,
    ) -> ObsDslResult:
        stream = self.start_stream(qid)
        return self.collect_from_stream(qid, stream, accept_extraction=accept_extraction)

    def start_stream(self, qid: str) -> ObsHilogStream:
        clear_result = self.hdc.shell("hilog", "-r", timeout=10, check=False)
        if clear_result.returncode != 0:
            self._log.warning("[%s] stage=OBS_HILOG_CLEAR_FAILED error=%s", qid, format_command_failure(clear_result))

        command = self.hdc.command(["shell", "hilog"])
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
        self._log.info("[%s] stage=OBS_HILOG_STREAM_STARTED command=%s", qid, " ".join(command))
        return ObsHilogStream(
            process=process,
            reader=reader,
            line_queue=line_queue,
            recent_lines=[],
            started=time.monotonic(),
        )

    def collect_from_stream(
        self,
        qid: str,
        stream: ObsHilogStream,
        *,
        accept_extraction: Callable[[DslExtraction], bool] | None = None,
    ) -> ObsDslResult:
        timeout = max(0.1, float(self.config.obs_hilog_timeout))
        deadline = stream.started + timeout
        accept_extraction = accept_extraction or (lambda _extraction: True)

        try:
            while time.monotonic() <= deadline:
                try:
                    line = stream.line_queue.get(timeout=0.5)
                except queue.Empty:
                    if stream.process.poll() is not None:
                        break
                    continue
                if line is None:
                    break
                stream.recent_lines.append(line.rstrip("\r\n"))
                if len(stream.recent_lines) > 200:
                    stream.recent_lines.pop(0)

                url = extract_obs_url(line)
                if url:
                    if not is_complete_obs_url(url):
                        # 链接被 hilog 截断，下载必然 403；不记入已见文件，等待完整输出
                        self._log.info("[%s] stage=OBS_URL_TRUNCATED url_tail=%s", qid, url[-80:])
                        continue
                    if url in self._load_seen_urls():
                        # 跨 query 命中历史链接，视为残存旧链接，拒绝下载
                        self._log.info("[%s] stage=OBS_URL_DUPLICATE url=%s", qid, url)
                        continue
                    self._record_seen_url(url)
                    match_path = self._save_hilog_match(qid, line, stream.recent_lines)
                    url_path = self._save_obs_url(qid, url)
                    markdown = self._download_markdown(url)
                    markdown_path = self._save_markdown(qid, markdown)
                    extraction = parse_obs_markdown(qid, markdown)
                    if not is_complete_dsl(extraction.records):
                        raise TimeoutError(f"OBS DSL is incomplete for query {qid}: {markdown_path}")
                    if not accept_extraction(extraction):
                        self._log.info("[%s] stage=OBS_DSL_STALE url=%s markdown=%s match=%s url_file=%s", qid, url, markdown_path, match_path, url_path)
                        continue

                    elapsed = time.monotonic() - stream.started
                    self._log.info(
                        "[%s] stage=OBS_DSL_READY url=%s markdown=%s match=%s url_file=%s elapsed_ms=%d",
                        qid,
                        url,
                        markdown_path,
                        match_path,
                        url_path,
                        int(elapsed * 1000),
                    )
                    self._log.debug("[%s] stage=OBS_DSL_MATCH line=%s", qid, line.rstrip("\r\n"))
                    return ObsDslResult(
                        extraction=extraction,
                        url=url,
                        markdown_path=markdown_path,
                        hilog_match_path=match_path,
                        elapsed_seconds=elapsed,
                    )

            timeout_path = self._save_hilog_snapshot(qid, "TIMEOUT", stream.recent_lines)
            raise TimeoutError(f"OBS markdown URL not found in hilog for query {qid} after {timeout:g}s: {timeout_path}")
        finally:
            self.stop_stream(stream)

    def stop_stream(self, stream: ObsHilogStream) -> None:
        stop_process(stream.process)
        stream.reader.join(timeout=2)

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

    def _save_obs_url(self, qid: str, url: str) -> Path:
        path = timestamped_artifact_path(self.config.obs_hilog_match_dir, qid, ".url")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"qid: {qid}\nurl: {url}\n", encoding="utf-8")
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
    for match in RESULT_FIELD_URL_RE.finditer(line):
        url = normalize_obs_url(match.group("url"))
        if url:
            return url

    for match in GEN_WIDGET_RESULT_RE.finditer(line):
        candidate = match.group("quoted") or match.group("bare")
        url = normalize_obs_url(candidate)
        if url:
            return url

    for match in OBS_MD_URL_RE.finditer(line):
        url = normalize_obs_url(match.group(0))
        if url:
            return url
    return None


def normalize_obs_url(candidate: str) -> str | None:
    url = _clean_url(unescape_log_url(candidate))
    if is_obs_markdown_url(url):
        return url
    return None


def unescape_log_url(value: str) -> str:
    if "\\" not in value:
        return value
    try:
        decoded = json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace("\\/", "/")
    return decoded


def _clean_url(url: str) -> str:
    return url.rstrip(_URL_TRAILING_STRIP)


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
