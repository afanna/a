from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

@dataclass(frozen=True)
class AutomationConfig:
    project_root: Path
    hdc: str = "hdc"
    sn: str | None = None
    artifact_namespace: str | None = None
    remote_dump: str = "/data/local/tmp/current_ui_tree.json"
    remote_snapshot: str = "/data/local/tmp/snapshot_display.jpeg"
    ready_timeout: float = 60
    post_query_wait: float = 30
    query_attempt_timeout: float = 90
    query_max_attempts: int = 3
    dsl_source: str = "obs"
    obs_hilog_timeout: float = 400
    obs_download_timeout: float = 15
    obs_markdown_dir_override: Path | None = None
    obs_hilog_match_dir_override: Path | None = None
    poll_interval: float = 2
    scroll_limit: int = 12
    render_wait: float = 5
    build_timeout: float = 300
    deveco_sdk_home: Path | None = None
    java_home: Path | None = None
    render_project_dir: Path = Path("A2UI_Render")
    render_work_dir_name: str | None = None
    rawfile_target_rel: Path = Path("entry/src/main/resources/rawfile/test.json")
    hap_output_dir_rel: Path = Path("entry/build/default/outputs/default")
    signed_hap_name: str = "entry-default-signed.hap"
    hvigor_executable: Path | None = None
    bundle_name: str = "com.example.myapplication"
    ability_name: str = "EntryAbility"
    module_name: str = "entry"
    screenshot_min_bytes: int = 1000
    screenshot_retries: int = 3
    screenshot_write_wait: float = 1
    context_clear_enabled: bool = False
    context_clear_points: tuple[tuple[int, int], ...] = ((1150, 255),)
    context_clear_wait: float = 1
    hilog_on_dsl_failure: bool = True
    hilog_capture_seconds: float = 5
    hilog_output_dir_override: Path | None = None
    enable_card_crop: bool = True
    enable_rule_check: bool = False
    card_crop_config: Path | None = None
    rule_check_config_dir: Path | None = None
    card_crop_debug: bool = False
    debug: bool = False

    @property
    def queries_path(self) -> Path:
        return self.project_root / "queries.jsonl"

    @property
    def dsl_dir(self) -> Path:
        if self.safe_artifact_namespace:
            return self.project_root / "dsl" / self.safe_artifact_namespace
        return self.project_root / "dsl"

    @property
    def output_dir(self) -> Path:
        if self.safe_artifact_namespace:
            return self.project_root / "output" / self.safe_artifact_namespace
        return self.project_root / "output"

    @property
    def log_dir(self) -> Path:
        base = self.project_root / "Automation" / ".work" / "logs"
        namespace = self.safe_artifact_namespace or self.safe_sn
        if namespace:
            return base / namespace
        return base

    @property
    def source_arkts_dir(self) -> Path:
        return resolve_project_path(self.project_root, self.render_project_dir)

    @property
    def arkts_dir(self) -> Path:
        name = self.render_work_dir_name or self.render_project_dir.name or "render_project"
        return self.work_dir / safe_path_name(name)

    @property
    def rawfile_target(self) -> Path:
        return self.arkts_dir / self.rawfile_target_rel

    @property
    def hap_output_dir(self) -> Path:
        return self.arkts_dir / self.hap_output_dir_rel

    @property
    def signed_hap_path(self) -> Path:
        return self.hap_output_dir / self.signed_hap_name

    @property
    def work_dir(self) -> Path:
        base = self.project_root / "Automation" / ".work"
        if self.safe_sn:
            return base / "devices" / self.safe_sn
        return base

    @property
    def safe_sn(self) -> str | None:
        if not self.sn:
            return None
        return safe_path_name(self.sn)

    @property
    def safe_artifact_namespace(self) -> str | None:
        if not self.artifact_namespace:
            return None
        return safe_path_name(self.artifact_namespace)

    def artifact_stem(self, qid: str) -> str:
        return safe_path_name(qid)

    def dsl_path_for(self, qid: str) -> Path:
        return self.dsl_dir / f"{self.artifact_stem(qid)}.jsonl"

    def screenshot_path_for(self, qid: str) -> Path:
        return self.screenshot_output_dir / f"{self.artifact_stem(qid)}.jpeg"

    def card_screenshot_path_for(self, qid: str) -> Path:
        return self.card_output_dir / f"{self.artifact_stem(qid)}.png"

    @property
    def card_output_dir(self) -> Path:
        return self.output_dir

    @property
    def screenshot_output_dir(self) -> Path:
        return self.output_dir / "Screenshot"

    @property
    def card_crop_debug_dir(self) -> Path:
        return self.log_dir / "card_crop_debug"

    @property
    def hilog_output_dir(self) -> Path:
        if self.hilog_output_dir_override:
            return self.hilog_output_dir_override
        return self.output_dir / "logs"

    @property
    def obs_markdown_dir(self) -> Path:
        if self.obs_markdown_dir_override:
            return self.obs_markdown_dir_override
        return self.output_dir / "obs_md"

    @property
    def obs_hilog_match_dir(self) -> Path:
        if self.obs_hilog_match_dir_override:
            return self.obs_hilog_match_dir_override
        return self.output_dir / "obs_hilog"

    @property
    def default_card_crop_config_path(self) -> Path:
        return self.project_root / "Automation" / "config" / "card_crop.json"

    @property
    def default_rule_check_config_dir(self) -> Path:
        return self.project_root / "Aesthetic_Rule_Check" / "config"

    @property
    def rule_report_dir(self) -> Path:
        return self.output_dir / "reports"

    def rule_report_dir_for(self, qid: str) -> Path:
        return self.rule_report_dir / self.artifact_stem(qid)
    
    @property
    def scores_jsonl_path(self) -> Path:
        """审美打分结果jsonl路径"""
        return self.rule_report_dir / "model_scores.jsonl"
    
    @property
    def report_html_path(self) -> Path:
        """审美可视化报告路径"""
        return self.rule_report_dir / "model_report.html"

def safe_path_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return cleaned or "item"


def resolve_project_path(project_root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return project_root / value
