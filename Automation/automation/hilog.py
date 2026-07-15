from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import AutomationConfig, safe_path_name
from .hdc import HdcClient, HdcError, format_command_failure


@dataclass(frozen=True)
class HilogCaptureResult:
    qid: str
    path: Path
    elapsed_seconds: float


class HilogCollector:
    def __init__(self, config: AutomationConfig, hdc: HdcClient):
        self.config = config
        self.hdc = hdc

    def capture(self, qid: str) -> HilogCaptureResult:
        seconds = max(0.1, float(self.config.hilog_capture_seconds))
        output_path = self._output_path(qid)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        setup_errors = self._prepare_hilog()
        command = self.hdc.command(["shell", "hilog"])
        started = time.monotonic()
        stdout = ""
        stderr = ""

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                env=self.hdc.env,
                text=True,
                timeout=seconds,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            stdout = decode_timeout_output(exc.stdout)
            stderr = decode_timeout_output(exc.stderr)
        except FileNotFoundError as exc:
            raise HdcError(f"HDC executable not found: {self.hdc.executable}") from exc

        elapsed = time.monotonic() - started
        content = build_hilog_file_content(
            qid=qid,
            seconds=seconds,
            command=command,
            setup_errors=setup_errors,
            stdout=stdout,
            stderr=stderr,
        )
        output_path.write_text(content, encoding="utf-8")
        return HilogCaptureResult(qid=qid, path=output_path, elapsed_seconds=elapsed)

    def _prepare_hilog(self) -> list[str]:
        setup_commands = [
            ("power-shell setmode 602",),
            ("hilog", "-p", "off"),
            ("hilog", "-Q", "pidoff"),
            ("hilog", "-w", "start"),
            ("hilog", "-Q", "domainoff"),
        ]

        errors: list[str] = []
        for parts in setup_commands:
            result = self.hdc.shell(*parts, timeout=10, check=False)
            if result.returncode != 0:
                errors.append(format_command_failure(result))
        return errors

    def _output_path(self, qid: str) -> Path:
        timestamp = time.strftime("%Y%m%d%H%M%S")
        millis = int((time.time() % 1) * 1000)
        filename = f"{timestamp}{millis:03d}-{safe_path_name(qid)}.txt"
        return self.config.hilog_output_dir / filename


def decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def build_hilog_file_content(
    *,
    qid: str,
    seconds: float,
    command: list[str],
    setup_errors: list[str],
    stdout: str,
    stderr: str,
) -> str:
    lines = [
        f"qid: {qid}",
        f"capture_seconds: {seconds:g}",
        f"command: {' '.join(command)}",
        "",
    ]
    if setup_errors:
        lines.append("setup_errors:")
        lines.extend(setup_errors)
        lines.append("")
    if stderr:
        lines.append("STDERR:")
        lines.append(stderr.rstrip())
        lines.append("")
    lines.append("STDOUT:")
    lines.append(stdout.rstrip())
    lines.append("")
    return "\n".join(lines)
