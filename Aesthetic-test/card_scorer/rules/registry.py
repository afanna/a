"""Rule registry and automatic rule collection system.

This module provides:
- RuleBook: Loads rule metadata from JSON files
- Rule registry: Automatically discovers and registers rule classes
- Profile support: Enable/disable rules and modules dynamically
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Registry to collect all rule classes
_RULE_REGISTRY: dict[str, type] = {}

def register_rule(cls: type) -> type:
    """Decorator to register a rule class.
    
    Usage:
        @register_rule
        class MyRule(Rule):
            rule_id = "R1.1"
            ...
    """
    rule_id = getattr(cls, "rule_id", None)
    if not rule_id:
        raise ValueError(f"Rule class {cls.__name__} must define 'rule_id' attribute")
    
    if rule_id in _RULE_REGISTRY:
        existing = _RULE_REGISTRY[rule_id]
        raise ValueError(f"Duplicate rule_id '{rule_id}': {cls.__name__} vs {existing.__name__}")
    
    _RULE_REGISTRY[rule_id] = cls
    return cls


def get_registered_rules() -> dict[str, type]:
    """Get all registered rule classes."""
    return _RULE_REGISTRY.copy()


@dataclass
class RuleMetadata:
    """Rule metadata from JSON."""
    id: str
    name: str
    module: str
    dimension: str
    severity: str
    max_deduction: float
    enabled: bool
    description: str = ""


@dataclass
class RuleBook:
    """Rule configuration loaded from JSON files and profiles."""
    rules: dict[str, RuleMetadata]
    rules_version: str
    profile_name: str
    enabled_modules: list[str]
    disabled_modules: list[str] = field(default_factory=list)
    disabled_rules: list[str] = field(default_factory=list)
    enabled_rules: list[str] = field(default_factory=list)

    def module_enabled(self, module: str) -> bool:
        """Check if a module is enabled."""
        return module in self.enabled_modules and module not in self.disabled_modules

    def rule_enabled(self, rule_id: str) -> bool:
        """Check if a specific rule is enabled."""
        rule = self.rules.get(rule_id)
        if not rule:
            return True
        
        if rule_id in self.disabled_rules:
            return False
        
        if self.enabled_rules and rule_id not in self.enabled_rules:
            return False
        
        return rule.enabled and self.module_enabled(rule.module)

    def get_rule_metadata(self, rule_id: str) -> RuleMetadata | None:
        """Get metadata for a specific rule."""
        return self.rules.get(rule_id)

    def list_enabled_rules(self) -> list[str]:
        """List all enabled rule IDs."""
        return [rid for rid in self.rules.keys() if self.rule_enabled(rid)]

    def metadata(self) -> dict[str, Any]:
        """Get RuleBook metadata for reporting."""
        return {
            "rules_version": self.rules_version,
            "profile": self.profile_name,
            "enabled_modules": self.enabled_modules,
            "disabled_modules": self.disabled_modules,
            "disabled_rules": self.disabled_rules,
            "enabled_rules": self.enabled_rules,
            "total_rules": len(self.rules),
            "enabled_rule_count": len(self.list_enabled_rules()),
        }


def load_rules_from_json(rules_dir: Path) -> tuple[dict[str, RuleMetadata], str]:
    """Load all rule metadata from JSON files in the rules directory."""
    rules: dict[str, RuleMetadata] = {}
    versions: set[str] = set()
    
    for json_file in sorted(rules_dir.glob("*_rules.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Failed to load {json_file.name}: {e}")
            continue
        
        if data.get("rules_version"):
            versions.add(str(data["rules_version"]))
        
        for rule_data in data.get("rules", []):
            if not isinstance(rule_data, dict) or "id" not in rule_data:
                continue
            
            rule_id = str(rule_data["id"])
            rules[rule_id] = RuleMetadata(
                id=rule_id,
                name=str(rule_data.get("name", rule_id)),
                module=str(rule_data.get("module", "")),
                dimension=str(rule_data.get("dimension", "未分类")),
                severity=str(rule_data.get("severity", "MINOR")),
                max_deduction=float(rule_data.get("max_deduction", 0.0)),
                enabled=bool(rule_data.get("enabled", True)),
                description=str(rule_data.get("description", "")),
            )
    
    version = "+".join(sorted(versions)) if versions else "unknown"
    return rules, version


def load_profile(profile: str, profiles_dir: Path) -> dict[str, Any]:
    """Load a validation profile from YAML or JSON."""
    path = Path(profile)
    
    # If it's not a file path, look in profiles directory
    if not path.suffix:
        yaml_path = profiles_dir / f"{profile}.yaml"
        json_path = profiles_dir / f"{profile}.json"
        
        if yaml_path.exists():
            path = yaml_path
        elif json_path.exists():
            path = json_path
        else:
            raise FileNotFoundError(f"Profile not found: {profile}")
    
    if not path.exists():
        raise FileNotFoundError(f"Profile file not found: {path}")
    
    if path.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        return json.loads(path.read_text(encoding="utf-8"))


DEFAULT_MODULES = ["information", "layout", "color", "hierarchy", "consistency", "structure"]
DEFAULT_PROFILE = "default"


def build_rulebook(
    profile: str = DEFAULT_PROFILE,
    enabled_modules: list[str] | None = None,
    disabled_modules: list[str] | None = None,
    enabled_rules: list[str] | None = None,
    disabled_rules: list[str] | None = None,
    rules_dir: Path | None = None,
    profiles_dir: Path | None = None,
) -> RuleBook:
    """Build a RuleBook from profile and overrides."""
    if rules_dir is None:
        rules_dir = Path(__file__).parent.parent.parent / "configs" / "rules"

    if profiles_dir is None:
        profiles_dir = Path(__file__).parent.parent.parent / "configs" / "profiles"
    
    # Load rule metadata
    rules, rules_version = load_rules_from_json(rules_dir)
    
    # Load profile (if it exists)
    try:
        profile_data = load_profile(profile, profiles_dir)
    except FileNotFoundError:
        # Use default if profile doesn't exist
        profile_data = {"name": profile, "enabled_modules": DEFAULT_MODULES}
    
    # Build module list
    modules = list(enabled_modules or profile_data.get("enabled_modules", DEFAULT_MODULES))
    disabled = list(disabled_modules or profile_data.get("disabled_modules", []))
    
    # Build rule lists
    profile_disabled_rules = list(profile_data.get("disabled_rules", []))
    final_disabled_rules = profile_disabled_rules + list(disabled_rules or [])
    final_enabled_rules = list(enabled_rules or profile_data.get("enabled_rules", []))
    
    rulebook = RuleBook(
        rules=rules,
        rules_version=rules_version,
        profile_name=str(profile_data.get("name", profile)),
        enabled_modules=modules,
        disabled_modules=disabled,
        disabled_rules=final_disabled_rules,
        enabled_rules=final_enabled_rules,
    )
    
    return rulebook
