from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import json
import os
from subprocess import TimeoutExpired
from pathlib import Path

from .config import AutomationConfig
from .hdc import HdcClient


class ArkTsRunner:
    def __init__(self, config: AutomationConfig, hdc: HdcClient):
        self.config = config
        self.hdc = hdc

    def render(self, qid: str, dsl_path: Path) -> Path:
        self.copy_dsl_to_rawfile(dsl_path)
        self.build_and_run()
        time.sleep(self.config.render_wait)
        output = self.config.output_dir / f"{qid}.jpeg"
        self.hdc.snapshot_display(
            output,
            self.config.remote_snapshot,
            min_bytes=self.config.screenshot_min_bytes,
            retries=self.config.screenshot_retries,
            write_wait=self.config.screenshot_write_wait,
        )
        return output

    def copy_dsl_to_rawfile(self, dsl_path: Path) -> Path:
        if not dsl_path.exists():
            raise FileNotFoundError(dsl_path)
        if dsl_path.suffix.lower() != ".jsonl":
            raise ValueError(f"DSL file must be JSONL: {dsl_path}")
        validate_dsl_array_file(dsl_path)
        self.config.rawfile_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dsl_path, self.config.rawfile_target)
        return self.config.rawfile_target

    def build_and_run(self) -> None:
        script = self.config.build_script
        if not script.exists():
            raise FileNotFoundError(f"ArkTS build script not found: {script}")

        command = (
            ["cmd", "/c", "call", str(script)]
            if os.name == "nt" and script.suffix.lower() in {"", ".bat", ".cmd"}
            else [str(script)]
        )

        total_timeout = max(self.config.build_timeout, self.config.build_wait)
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as stdout_file, tempfile.TemporaryFile(
            "w+", encoding="utf-8", errors="replace"
        ) as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=str(self.config.arkts_dir),
                text=True,
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
            )

            try:
                process.wait(timeout=self.config.build_wait)
            except TimeoutExpired as exc:
                write_stdin_line(process)
                remaining_timeout = max(self.config.build_pause_grace, total_timeout - self.config.build_wait)
                try:
                    process.wait(timeout=remaining_timeout)
                except TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=self.config.build_pause_grace)
                    except TimeoutExpired:
                        process.kill()
                        process.wait()
                    stdout, stderr = read_process_output(stdout_file, stderr_file)
                    raise RuntimeError(
                        f"ArkTS build/run timed out after {total_timeout} seconds: {script}\n"
                        f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                    ) from exc

            stdout, stderr = read_process_output(stdout_file, stderr_file)
            if process.returncode != 0:
                raise RuntimeError(
                    f"ArkTS build/run failed with exit code {process.returncode}: {script}\n"
                    f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                )


def write_stdin_line(process: subprocess.Popen) -> None:
    if process.stdin is None or process.stdin.closed:
        return
    try:
        process.stdin.write("\n")
        process.stdin.flush()
    except OSError:
        return


def read_process_output(stdout_file, stderr_file) -> tuple[str, str]:
    stdout_file.seek(0)
    stderr_file.seek(0)
    return stdout_file.read(), stderr_file.read()


def validate_dsl_array_file(path: Path) -> None:
    with open(path, "r", encoding="utf-8") as f:
        try:
            value = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid DSL array file at {path}: {exc}") from exc

    if not isinstance(value, list):
        raise ValueError(f"DSL file must be a JSON array: {path}")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"DSL array item must be a JSON object at {path}[{index}]")
