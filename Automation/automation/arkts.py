from __future__ import annotations

import shutil
import subprocess
import time
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
        self.config.rawfile_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dsl_path, self.config.rawfile_target)
        return self.config.rawfile_target

    def build_and_run(self) -> None:
        script = self.config.build_script
        if not script.exists():
            raise FileNotFoundError(f"ArkTS build script not found: {script}")
        if script.suffix.lower() == ".bat":
            command = ["cmd", "/c", str(script)]
        else:
            command = [str(script)]
        completed = subprocess.run(command, cwd=str(self.config.arkts_dir), check=False, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"ArkTS build/run failed with exit code {completed.returncode}: {script}")

