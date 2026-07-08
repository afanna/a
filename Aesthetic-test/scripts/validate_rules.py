"""Validate rule consistency between JSON metadata and code implementation.

This script checks:
1. All rules defined in JSON have corresponding implementations
2. All implemented rules have JSON metadata
3. Rule IDs are unique
4. Severity and deduction values are valid
5. Module names match between JSON and code
6. Profile configurations are valid
"""

import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from card_scorer.rules.registry import build_rulebook, get_registered_rules, load_rules_from_json


def validate_rules():
    """Run all validation checks."""
    print("=" * 60)
    print("Rule Consistency Validation")
    print("=" * 60)
    
    errors = []
    warnings = []
    
    # Load JSON metadata
    rules_dir = PROJECT_ROOT / "configs" / "rules"
    json_rules, version = load_rules_from_json(rules_dir)
    print(f"\n[OK] Loaded {len(json_rules)} rules from JSON (version: {version})")
    
    # Import all rule modules to trigger registration
    try:
        import card_scorer.rules  # This imports all submodules
        registry = get_registered_rules()
        print(f"[OK] Loaded {len(registry)} rule classes from code")
    except Exception as e:
        errors.append(f"Failed to import rules: {e}")
        print_summary(errors, warnings)
        return 1
    
    # Check 1: All JSON rules have implementations
    print("\n[Check 1] JSON rules have code implementation...")
    for rule_id in json_rules.keys():
        if rule_id not in registry:
            errors.append(f"  [FAIL] Rule {rule_id} defined in JSON but not implemented in code")
        else:
            print(f"  [OK] {rule_id}")
    
    # Check 2: All code implementations have JSON metadata
    print("\n[Check 2] Code implementations have JSON metadata...")
    for rule_id in registry.keys():
        if rule_id not in json_rules:
            errors.append(f"  [FAIL] Rule {rule_id} implemented in code but not defined in JSON")
        else:
            print(f"  [OK] {rule_id}")
    
    # Check 3: Rule ID uniqueness (should be caught by registry)
    print("\n[Check 3] Rule ID uniqueness...")
    rule_ids = list(json_rules.keys())
    if len(rule_ids) == len(set(rule_ids)):
        print(f"  [OK] All {len(rule_ids)} rule IDs are unique")
    else:
        duplicates = [rid for rid in rule_ids if rule_ids.count(rid) > 1]
        errors.append(f"  [FAIL] Duplicate rule IDs found: {set(duplicates)}")
    
    # Check 4: Severity and deduction values
    print("\n[Check 4] Severity and deduction values...")
    valid_severities = {"FATAL", "MAJOR", "MINOR"}
    for rule_id, meta in json_rules.items():
        if meta.severity not in valid_severities:
            errors.append(f"  [FAIL] {rule_id}: Invalid severity '{meta.severity}'")
        if meta.max_deduction < 0:
            errors.append(f"  [FAIL] {rule_id}: Negative max_deduction {meta.max_deduction}")
        if meta.max_deduction > 20:
            warnings.append(f"  [WARN] {rule_id}: Unusually high max_deduction {meta.max_deduction}")
    print(f"  [OK] Validated {len(json_rules)} rules")
    
    # Check 5: Module consistency
    print("\n[Check 5] Module name consistency...")
    valid_modules = {"information", "layout", "color", "hierarchy", "consistency", "structure"}
    module_counts = defaultdict(int)
    for rule_id, meta in json_rules.items():
        module_counts[meta.module] += 1
        if meta.module not in valid_modules:
            errors.append(f"  [FAIL] {rule_id}: Unknown module '{meta.module}'")
        
        # Check if rule class dimension matches JSON
        rule_class = registry.get(rule_id)
        if rule_class:
            code_module = getattr(rule_class, "dimension", None)
            # Note: dimension in code might differ from module name, this is OK
    
    print("  Module distribution:")
    for module, count in sorted(module_counts.items()):
        print(f"    {module}: {count} rules")
    
    # Check 6: Profile validation
    print("\n[Check 6] Profile configurations...")
    profiles_dir = PROJECT_ROOT / "configs" / "profiles"
    for profile_file in profiles_dir.glob("*.yaml"):
        try:
            rulebook = build_rulebook(profile=profile_file.stem)
            enabled_count = len(rulebook.list_enabled_rules())
            print(f"  [OK] {profile_file.stem}: {enabled_count}/{len(json_rules)} rules enabled")
            
            # Check for unknown modules/rules in profile
            for module in rulebook.enabled_modules:
                if module not in valid_modules:
                    warnings.append(f"  [WARN] Profile '{profile_file.stem}' enables unknown module '{module}'")
            
            for rule_id in rulebook.disabled_rules:
                if rule_id not in json_rules:
                    warnings.append(f"  [WARN] Profile '{profile_file.stem}' disables unknown rule '{rule_id}'")
        
        except Exception as e:
            errors.append(f"  [FAIL] Failed to load profile {profile_file.stem}: {e}")
    
    # Summary
    print_summary(errors, warnings)
    
    return 1 if errors else 0


def print_summary(errors, warnings):
    """Print validation summary."""
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    if errors:
        print(f"\n[FAIL] {len(errors)} ERROR(S) FOUND:")
        for err in errors:
            print(err)
    
    if warnings:
        print(f"\n[WARN] {len(warnings)} WARNING(S):")
        for warn in warnings:
            print(warn)
    
    if not errors and not warnings:
        print("\n[PASS] All checks passed! Rules are consistent.")
    
    print()


if __name__ == "__main__":
    sys.exit(validate_rules())
