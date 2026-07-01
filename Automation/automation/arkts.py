from __future__ import annotations

import shutil
import subprocess
import time
import json
import os
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
        self.hdc.snapshot_display(output, self.config.remote_snapshot)
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

        completed = subprocess.run(
            command,
            cwd=str(self.config.arkts_dir),
            check=False,
            text=True,
            input="\n",
            capture_output=True,
            timeout=self.config.build_timeout,
        )

        if completed.returncode != 0:
            raise RuntimeError(
                f"ArkTS build/run failed with exit code {completed.returncode}: {script}\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )


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
