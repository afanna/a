from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Local test-machine configuration.
# Update this one path if DevEco Studio is installed somewhere else.
LOCAL_DEVECO_STUDIO_HOME = Path("D:/DevEco Studio")
LOCAL_DEVECO_SDK_HOME = LOCAL_DEVECO_STUDIO_HOME / "sdk"
LOCAL_JAVA_HOME = LOCAL_DEVECO_STUDIO_HOME / "jbr"


@dataclass(frozen=True)
class AutomationConfig:
    project_root: Path
    hdc: str = "hdc"
    remote_dump: str = "/data/local/tmp/current_ui_tree.json"
    remote_snapshot: str = "/data/local/tmp/snapshot_display.jpeg"
    ready_timeout: float = 60
    reply_timeout: float = 120
    extract_delay: float = 30
    post_query_wait: float = 30
    query_attempt_timeout: float = 90
    query_max_attempts: int = 3
    poll_interval: float = 2
    scroll_limit: int = 12
    render_wait: float = 5
    build_timeout: float = 300
    deveco_sdk_home: Path | None = LOCAL_DEVECO_SDK_HOME
    java_home: Path | None = LOCAL_JAVA_HOME
    bundle_name: str = "yyx.test.test"
    ability_name: str = "EntryAbility"
    module_name: str = "entry"
    screenshot_min_bytes: int = 1000
    screenshot_retries: int = 3
    screenshot_write_wait: float = 1

    @property
    def queries_path(self) -> Path:
        return self.project_root / "queries.jsonl"

    @property
    def dsl_dir(self) -> Path:
        return self.project_root / "dsl"

    @property
    def output_dir(self) -> Path:
        return self.project_root / "output"

    @property
    def arkts_dir(self) -> Path:
        return self.project_root / "ArkTs"

    @property
    def rawfile_target(self) -> Path:
        return self.arkts_dir / self.module_name / "src" / "main" / "resources" / "rawfile" / "sample.jsonl"

    @property
    def hap_output_dir(self) -> Path:
        return self.arkts_dir / self.module_name / "build" / "default" / "outputs" / "default"

    @property
    def signed_hap_path(self) -> Path:
        return self.hap_output_dir / f"{self.module_name}-default-signed.hap"

    @property
    def work_dir(self) -> Path:
        return self.project_root / "Automation" / ".work"
