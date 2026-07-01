from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class HdcError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class HdcClient:
    def __init__(self, executable: str = "hdc", default_timeout: float = 30):
        self.executable = executable
        self.default_timeout = default_timeout
        self.env = os.environ.copy()
        self.env["MSYS_NO_PATHCONV"] = "1"

    def run(self, args: Sequence[object], *, timeout: float | None = None, check: bool = True) -> CommandResult:
        command = [self.executable, *[str(arg) for arg in args]]
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=self.env,
            text=True,
            timeout=self.default_timeout if timeout is None else timeout,
        )
        result = CommandResult(tuple(command), completed.returncode, completed.stdout or "", completed.stderr or "")
        if check and result.returncode != 0:
            raise HdcError(format_command_failure(result))
        return result

    def shell(self, *parts: object, timeout: float | None = None, check: bool = True) -> CommandResult:
        return self.run(["shell", *parts], timeout=timeout, check=check)

    def dump_layout(self, local_path: Path, remote_path: str) -> Path:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.shell("uitest", "dumpLayout", "-p", remote_path, timeout=15)
        self.run(["file", "recv", remote_path, str(local_path)], timeout=15)
        return local_path

    def ui_input(self, action: str, *args: object, check: bool = True) -> CommandResult:
        return self.shell("uitest", "uiInput", action, *args, timeout=10, check=check)

    def snapshot_display(self, local_path: Path, remote_path: str) -> Path:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.shell("snapshot_display", "-f", remote_path, timeout=30, check=False)
        if result.returncode != 0:
            self.shell("snapshot_display", remote_path, timeout=30)
        self.run(["file", "recv", remote_path, str(local_path)], timeout=30)
        return local_path


def format_command_failure(result: CommandResult) -> str:
    command = " ".join(result.args)
    return f"Command failed ({result.returncode}): {command}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

