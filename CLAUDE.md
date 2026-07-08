# CLAUDE.md

## Project Overview

Automation-screenshot automates Xiaoyi assistant UI validation: send a query, extract DSL, render through HarmonyOS ArkTS, capture screenshots with HDC, optionally score UI aesthetics with Doubao/Volcano Ark, and generate reports.

Read `AGENTS.md` first. Detailed operational guidance lives in `agents.d/`.

## Tech Stack

- Python automation under `Automation/`.
- HarmonyOS ArkTS template under `ArkTs/`.
- DevEco Studio SDK/JDK and hvigor for HAP builds.
- HDC for device automation and screenshots.
- Doubao/Volcano Ark multimodal API for optional scoring.

## Critical Commands

```powershell
python --version
python -m py_compile Automation\main.py Automation\automation\pipeline.py Automation\automation\arkts.py Automation\automation\hdc.py Automation\automation\xiaoyi.py
python Automation\main.py one --qid test --query "test"
python Automation\main.py batch
python Automation\main.py parallel --devices auto
python Automation\main.py aesthetics --input .\output --output .\output
```

If `python` is not on PATH, stop and report the environment blocker.

## Code Style & Conventions

- Keep Python type hints on public/new function signatures.
- Preserve UTF-8 and Chinese comments where surrounding code uses them.
- Keep CLI flags, config defaults, README, and `agents.d/01-commands.md` synchronized.
- Do not hardcode API keys or local secrets.

## Workflow Preferences

- Do not modify `ArkTs/` without explicit owner approval.
- Generated `dsl/`, `output/`, and `Automation/.work/` artifacts must not be committed.
- Ask before installing dependencies; owner says a complete local dependency list exists, but no root dependency file was found in this scan.
- Ask before running paid/API scoring or disruptive device actions.

## Architecture Notes

- CLI entry: `Automation/main.py`.
- Orchestration: `Automation/automation/pipeline.py`.
- Device wrapper: `Automation/automation/hdc.py`.
- Xiaoyi UI and DSL collection: `Automation/automation/xiaoyi.py`, `dsl.py`, `ui_tree.py`.
- ArkTS build/install/screenshot: `Automation/automation/arkts.py`.
- Scoring: `visual_aesthetics/`.

Risk governance update: previously observed runtime risks have been remediated, including logger wiring, timers/counters, send-button flow, batch summary, and no-SN ArkTS working-copy isolation. `python --version` and py-compile now pass; the pipeline still needs device-backed validation when HDC reports a connected target.
