# AGENTS.md

## Project Snapshot
Source: Owner-confirmed plus repo evidence.

Automation-screenshot is an end-to-end automation pipeline for Xiaoyi assistant UI generation checks: send a query, extract DSL from the Xiaoyi chat UI, render it through the HarmonyOS ArkTS project, capture screenshots with HDC, optionally score UI aesthetics through Doubao/Volcano Ark, and produce traceable artifacts and reports.

Primary flow:

```text
User query -> Xiaoyi UI detection -> query send -> DSL extraction -> ArkTS build/install/start -> screenshot -> optional aesthetic scoring -> report
```

## Tech Stack
- Python automation code under `Automation/`.
- HarmonyOS ArkTS template project under `ArkTs/`.
- HDC for device control, UI tree dumps, file transfer, app install/start, and screenshots.
- DevEco Studio SDK and DevEco bundled JDK for ArkTS builds and HAP signing.
- Doubao multimodal API through Volcano Ark for optional UI aesthetic scoring.

## Commands
Run commands from the repository root. Use `python` as the validation command; if `python` is not on PATH, report that as an environment blocker instead of silently switching commands.

```powershell
python Automation\main.py one --qid test_weather --query "test"
python Automation\main.py one-from-file --qid q1
python Automation\main.py batch
python Automation\main.py parallel --devices auto
python Automation\main.py aesthetics --input .\output --output .\output
```

Add `--enable-aesthetics --aesthetics-base-url <url> --aesthetics-api-key <key>` only when scoring is required. Never commit API keys.

## Environment Setup
Required:

- Python 3.10+ is documented in README; the owner expects validation commands to use `python`.
- DevEco Studio installed locally, default evidence path `D:/DevEco Studio`.
- HDC available on PATH and at least one connected/debuggable HarmonyOS device or emulator.
- Local complete dependency list exists per owner confirmation, but a root `requirements.txt` was not found during this scan. Ask the owner for the canonical dependency file before installing dependencies.
- Doubao/Volcano Ark credentials are required only for aesthetic scoring.

Environment/config priority is command line arguments, then environment variables, then defaults in code.

## Automation Runbook
Shortest confirmed development path:

1. Read this file and the relevant `agents.d/` file for the task.
2. Confirm environment prerequisites with non-mutating checks such as `python --version` and `hdc list targets`.
3. For a single pipeline run, use `python Automation\main.py one --qid <id> --query <text>`.
4. For regression, use `python Automation\main.py batch` or `python Automation\main.py parallel --devices auto`.
5. Inspect generated artifacts under `dsl/`, `output/`, and `output/{SN}/pipeline.log`.

Risk governance update: previously observed Python runtime risks around logging, timers, batch counters, send-button flow, and no-SN ArkTS template writes have been remediated in code. Do not claim the pipeline is verified until `python` is available and the checks in `agents.d/debug-playbook.md` pass.

## Approved Skills And Tools
- `agent-runbook-distiller`: use when updating this runbook or adding durable setup/build/test/debug knowledge. Safety: autonomous for reading; ask before modifying code or installing packages.
- Project CLI `Automation\main.py`: use for pipeline, parallel, and scoring workflows. Safety: autonomous for normal runs that generate `dsl/`, `output/`, and `Automation/.work/`; ask first before dependency installation, code changes, or secret-bearing scoring runs.
- HDC: use for device checks and diagnostics. Safety: autonomous for `hdc list targets`; ask before disruptive device actions unless the owner has requested a pipeline run.

Detailed tooling inventory is in `agents.d/tooling.md`.

## agents.d Index
- `agents.d/bootstrap.md`: prerequisites, setup, environment variables, and first-run success signals.
- `agents.d/tooling.md`: approved tools, commands, inputs, outputs, and safety levels.
- `agents.d/development-loop.md`: fast checks, slow checks, and verification expectations.
- `agents.d/architecture-map.md`: module boundaries, data flow, and files that change together.
- `agents.d/debug-playbook.md`: symptoms, diagnostics, remediated risks, and remaining verification blockers.
- `agents.d/change-recipes.md`: common change paths and required checks.
- `agents.d/review-handoff.md`: evidence required before human review.
- `agents.d/risk-areas.md`: hard invariants, forbidden actions, secrets, cost, and device risks.
- `agents.d/04-scoring-rules.md`: aesthetic scoring dimensions and thresholds.

## Repository Map
- `Automation/main.py`: CLI entry point.
- `Automation/automation/`: pipeline, HDC, Xiaoyi, DSL, ArkTS, query, UI tree, and logging modules.
- `visual_aesthetics/`: scoring configuration, model adapter, judge API, cache, and report builder.
- `ArkTs/`: source ArkTS template. Treat as protected; multi-device work copies it to `Automation/.work/devices/{SN}/ArkTs`.
- `queries.jsonl`: query case library.
- `dsl/`: generated DSL artifacts, ignored by git.
- `output/`: generated screenshots, logs, scores, and HTML reports, ignored by git.
- `Automation/.work/`: generated working copies and temporary files, ignored by git.

## Development Rules
- Keep changes scoped to the relevant module and follow existing Python type-hint style.
- Preserve UTF-8 and Chinese comments where the surrounding code uses them.
- Do not hardcode credentials, local secrets, API keys, or private account identifiers.
- Treat `ArkTs/` as protected. Only change it after explicit owner approval.
- Keep generated artifacts out of commits.
- If repo evidence and README conflict, prefer source code for current behavior and record unresolved conflicts in the handoff.

## Testing and Verification
Before claiming completion:

```powershell
python --version
python -m py_compile Automation\main.py Automation\automation\pipeline.py Automation\automation\arkts.py Automation\automation\hdc.py Automation\automation\xiaoyi.py
```

For pipeline behavior, run the smallest relevant command only when devices, DevEco, HDC, dependencies, and any required credentials are available:

```powershell
python Automation\main.py one --query "test" --qid "test"
```

Expected success signals: DSL file under `dsl/`, screenshot under `output/`, and no fatal errors in `output/{SN}/pipeline.log` when a device SN is used.

## Debugging Playbook
Use `agents.d/debug-playbook.md` first. Important starting points:

- `python` not found: environment blocker; do not switch to `py` unless the owner approves changing the validation command.
- No HDC devices: run `hdc list targets`, verify USB debugging/emulator, then escalate if still empty.
- DSL extraction fails: inspect Xiaoyi readiness, UI tree dumps, `reply-timeout`, `query-attempt-timeout`, and logs.
- Screenshot too small or missing: inspect `snapshot_display` retries and `output/{SN}/pipeline.log`.
- Aesthetic API fails: verify endpoint/key out of band, increase timeout/retries only with non-secret values.

## Change Recipes
See `agents.d/change-recipes.md` for focused workflows. Common paths:

- CLI parameter changes usually touch `Automation/main.py`, `Automation/automation/config.py`, README/runbook docs, and CLI verification.
- DSL extraction changes usually touch `xiaoyi.py`, `dsl.py`, `ui_tree.py`, and single-query validation.
- ArkTS render/install changes usually touch `arkts.py`, HDC interactions, and device-backed validation.
- Scoring changes usually touch `visual_aesthetics/` and standalone `aesthetics` validation.

## Agent Workflow
1. Read the task-specific runbook file.
2. Inspect nearby code before editing.
3. Make focused changes; do not rewrite unrelated modules.
4. Run the relevant fast check, then the smallest behavior check available.
5. Report commands run, success signals, skipped checks, and remaining risks.

## Human Review Handoff
Include:

- Files changed and why.
- Source labels for any new runbook knowledge: repo-confirmed, owner-confirmed, observed during run, risk judgment, or unknown.
- Commands run and exact result summary.
- Generated artifacts inspected.
- Checks skipped and the blocker.
- Any risk that still needs owner/device/API validation.

## Risk Areas
- `ArkTs/` template changes.
- HAP build/sign/install flow and device commands.
- API credentials and scoring cost.
- Multi-device path isolation by safe SN.
- Runtime verification blockers listed in `agents.d/debug-playbook.md`.

## Do Not
- Do not modify `ArkTs/` directly without explicit approval.
- Do not commit `dsl/`, `output/`, `Automation/.work/`, logs, caches, archives, or screenshots generated during local runs.
- Do not hardcode secrets or commit `.env` files.
- Do not run destructive cleanup outside generated directories without approval.
- Do not push git changes without approval.
- Do not claim automation readiness when `python` is unavailable or py-compile/pipeline checks were skipped.

## Missing Context
- Owner confirmed a local complete dependency list exists, but the canonical root dependency file was not present in this scan.
- Platform-specific generated file requested: `CLAUDE.md` is provided. No `.opencode/` or `GEMINI.md` was requested.
- Observed verification: `python --version` reports Python 3.12.10 and py-compile passes. Device-backed pipeline validation is blocked until `hdc list targets` shows a connected device.

<!-- Codex: prefer rg over slower search tools; preserve user changes; keep edits scoped and verify with python. -->
