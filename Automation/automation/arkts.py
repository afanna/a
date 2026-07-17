from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from .config import AutomationConfig
from .hdc import HdcClient
from .logger import get_logger


class ArkTsRunner:
    def __init__(self, config: AutomationConfig, hdc: HdcClient):
        self.config = config
        self.hdc = hdc
        self._log = get_logger("arkts", sn=config.safe_sn or "", log_dir=config.log_dir, debug=config.debug)

    def render(self, qid: str, dsl_path: Path) -> Path:
        self.ensure_arkts_workspace()
        self.copy_dsl_to_rawfile(dsl_path)
        self.build_and_run()
        time.sleep(self.config.render_wait)
        output = self.config.screenshot_path_for(qid)
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
        records = load_dsl_records(dsl_path)
        self.config.rawfile_target.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.rawfile_target, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return self.config.rawfile_target

    def ensure_arkts_workspace(self) -> None:
        source = self.config.source_arkts_dir
        target = self.config.arkts_dir
        if not source.exists():
            raise FileNotFoundError(f"ArkTS source project does not exist: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source,
            target,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("build", ".hvigor", ".idea", ".gradle", "node_modules"),
        )

    def build_and_run(self) -> None:
        env = self.build_env()
        self.run_hvigor("clean", env)
        self.run_hvigor("assembleHap", env)
        self.print_hap_outputs()

        if not self.config.signed_hap_path.exists():
            self._log.error("Signed HAP not found: %s", self.config.signed_hap_path)
            raise FileNotFoundError(f"Signed HAP was not generated: {self.config.signed_hap_path}")

        remote_dir = f"/data/local/tmp/tmp_{self.remote_temp_suffix()}"
        remote_hap = f"{remote_dir}/{self.config.signed_hap_path.name}"
        try:
            self.hdc.shell("mkdir", "-p", remote_dir, timeout=30)
            hap_size = self.config.signed_hap_path.stat().st_size / (1024 * 1024) if self.config.signed_hap_path.exists() else 0
            self._log.info("hdc file send start: %.1fMB", hap_size)
            t_push = time.monotonic()
            self.hdc.run(["file", "send", self.config.signed_hap_path, remote_hap], timeout=self.config.build_timeout)
            self._log.info("hdc file send done: %.1fs", time.monotonic() - t_push)
            self._log.info("bm install start")
            t_install = time.monotonic()
            self.hdc.shell("bm", "install", "-p", remote_dir, timeout=self.config.build_timeout)
            self._log.info("bm install done: %.1fs", time.monotonic() - t_install)
        finally:
            self.hdc.shell("rm", "-rf", remote_dir, timeout=30, check=False)

        self.hdc.shell("aa", "force-stop", self.config.bundle_name, timeout=30, check=False)
        self.hdc.shell(
            "aa",
            "start",
            "-a",
            self.config.ability_name,
            "-b",
            self.config.bundle_name,
            "-m",
            self.config.module_name,
            timeout=30,
        )

    def remote_temp_suffix(self) -> str:
        safe_sn = self.config.safe_sn or "default"
        return f"{safe_sn}_{os.getpid()}_{datetime.now().strftime('%H%M%S%f')}"

    def build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        deveco_sdk_home = config_path_or_env(self.config.deveco_sdk_home, "DEVECO_SDK_HOME")
        if deveco_sdk_home is None:
            deveco_sdk_home = discover_deveco_sdk_home(self.config.hvigor_executable)
        java_home = config_path_or_env(self.config.java_home, "JAVA_HOME")
        if java_home is None:
            java_home = discover_java_home(self.config.hvigor_executable)
        if deveco_sdk_home is None:
            raise RuntimeError("DEVECO_SDK_HOME is not configured. Pass --deveco-sdk-home or set the environment variable.")
        if java_home is None:
            raise RuntimeError("JAVA_HOME is not configured. Pass --java-home or set the environment variable.")
        if not deveco_sdk_home.exists():
            raise RuntimeError(f"DEVECO_SDK_HOME does not exist: {deveco_sdk_home}")
        if not java_home.exists():
            raise RuntimeError(f"JAVA_HOME does not exist: {java_home}")

        java_bin = java_home / "bin"
        java_executable = java_bin / ("java.exe" if os.name == "nt" else "java")
        if not java_executable.exists():
            raise RuntimeError(f"JAVA_HOME does not contain a Java executable: {java_executable}")

        path_parts = [str(java_bin)]
        toolchains = deveco_sdk_home / "toolchains"
        if toolchains.exists():
            path_parts.append(str(toolchains))
        path_parts.append(env.get("PATH", ""))

        env["DEVECO_SDK_HOME"] = str(deveco_sdk_home)
        env["JAVA_HOME"] = str(java_home)
        env["PATH"] = os.pathsep.join(path_parts)
        return env

    def run_hvigor(self, action: str, env: Mapping[str, str]) -> None:
        command = hvigor_command(self.config.arkts_dir, action, self.config.hvigor_executable)
        run_local_command(command, self.config.arkts_dir, env, self.config.build_timeout)

    def print_hap_outputs(self) -> None:
        print(f"HAP output directory: {self.config.hap_output_dir}")
        for hap in sorted(self.config.hap_output_dir.glob("*.hap")):
            print(f"HAP: {hap}")


def config_path_or_env(value: Path | None, env_name: str) -> Path | None:
    if value is not None:
        return value
    raw_value = os.environ.get(env_name)
    if not raw_value:
        return None
    return Path(raw_value)


def discover_deveco_studio_home(hvigor_executable: Path | None = None) -> Path | None:
    for env_name in ("DEVECO_STUDIO_HOME", "DevEco Studio"):
        raw_value = os.environ.get(env_name)
        if raw_value:
            candidate = Path(raw_value.split(os.pathsep)[0])
            if candidate.exists():
                if candidate.name == "bin" and candidate.parent.name == "DevEco Studio":
                    return candidate.parent
                return candidate

    executable = hvigor_executable or find_hvigor_executable_from_path()
    if executable is None:
        return None
    executable_path = Path(executable)
    parents = list(executable_path.parents)
    for parent in parents:
        if parent.name == "DevEco Studio":
            return parent
    return None


def discover_deveco_sdk_home(hvigor_executable: Path | None = None) -> Path | None:
    studio_home = discover_deveco_studio_home(hvigor_executable)
    if studio_home is None:
        return None
    candidate = studio_home / "sdk"
    return candidate if candidate.exists() else None


def discover_java_home(hvigor_executable: Path | None = None) -> Path | None:
    studio_home = discover_deveco_studio_home(hvigor_executable)
    if studio_home is None:
        return None
    candidate = studio_home / "jbr"
    return candidate if candidate.exists() else None


def find_hvigor_executable_from_path() -> Path | None:
    for name in ("hvigorw.bat", "hvigorw", "hvigor.bat", "hvigor"):
        executable = shutil.which(name)
        if executable:
            return Path(executable)
    return None


def hvigor_command(arkts_dir: Path, action: str, executable_override: Path | None = None) -> list[str]:
    executable = executable_override or find_hvigor_executable(arkts_dir)
    if os.name == "nt":
        return ["cmd", "/c", "call", str(executable), action]
    return [str(executable), action]


def find_hvigor_executable(arkts_dir: Path) -> Path | str:
    for name in ("hvigorw.bat", "hvigorw", "hvigrow.bat", "hvigrow", "hvigor.bat", "hvigor"):
        candidate = arkts_dir / name
        if candidate.exists():
            return candidate
    for name in ("hvigorw.bat", "hvigorw", "hvigor.bat", "hvigor"):
        executable = shutil.which(name)
        if executable:
            return executable
    return "hvigorw.bat" if os.name == "nt" else "hvigorw"


def run_local_command(command: Sequence[str], cwd: Path, env: Mapping[str, str], timeout: float) -> None:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=dict(env),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout} seconds: {' '.join(command)}") from exc
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def validate_dsl_array_file(path: Path) -> None:
    load_dsl_records(path)


def load_dsl_records(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    try:
        value = json.loads(text)
    except json.JSONDecodeError as array_exc:
        try:
            records = load_jsonl_records(text, path)
        except ValueError as jsonl_exc:
            raise ValueError(f"Invalid DSL file at {path}: {array_exc}; {jsonl_exc}") from array_exc
    else:
        if not isinstance(value, list):
            raise ValueError(f"DSL file must be a JSON array or JSONL objects: {path}")
        records = value

    validate_dsl_records(records, path)
    return records


def load_jsonl_records(text: str, path: Path) -> list[dict]:
    records: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL record at line {line_no}: {exc}") from exc
        records.append(value)
    if not records:
        raise ValueError("No JSONL records found")
    return records


def validate_dsl_records(records: list[dict], path: Path) -> None:
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError(f"DSL record must be a JSON object at {path}[{index}]")
