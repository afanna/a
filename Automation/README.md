# Xiaoyi DSL Automation

Python-first automation for:

`query -> DSL extraction -> ArkTS rawfile copy -> build/install/run -> snapshot`

The design stays efficient, simple, modular, and decoupled. Shell scripts under `scripts/` are only historical logic references.

## Layout

- `main.py`: command line entry.
- `automation/hdc.py`: minimal HDC boundary.
- `automation/ui_tree.py`: UI tree parsing and locator scoring.
- `automation/xiaoyi.py`: wait ready, send query, wait reply, extract DSL.
- `automation/dsl.py`: DSL keyword search and JSONL persistence.
- `automation/arkts.py`: copy DSL to ArkTS rawfile, call build script, screenshot.
- `automation/pipeline.py`: single and batch orchestration.

## Commands

Run one query directly:

```powershell
python Automation\main.py one --qid q_manual --query "your query"
```

Run one query from `queries.jsonl`:

```powershell
python Automation\main.py one-from-file --qid q1
```

Batch mode:

```powershell
python Automation\main.py batch
```

Batch mode first sends all queries and extracts all DSL files. Only after all DSL files are collected does it render each case and save screenshots.

## Outputs

- DSL files: `dsl/{qid}.jsonl`
- ArkTS rawfile target: `ArkTs/entry/src/main/resources/rawfile/sample.jsonl`

`sample` must remain JSONL. The runner validates every non-empty line before copying DSL into the ArkTS rawfile directory.
- Screenshots: `output/{qid}.jpeg`
