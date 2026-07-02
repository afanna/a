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

If `ArkTs/build_and_run` runs render work and then ends with `pause`, keep the default waits or tune them:

```powershell
python Automation\main.py --build-wait 60 --render-wait 5 batch
```

`--build-wait` is the minimum time to let build/install/start/render script work run before automation sends Enter for the trailing pause. If the script is still busy, it can keep running until `--build-timeout`. `--render-wait` waits after the script exits before taking the screenshot.

`ArkTs/build_and_run.bat` is the default Windows script. Fill `DEVECO_SDK_HOME` and `JAVA_HOME` at the top after the real ArkTS project is checked in. It cleans first, builds the signed HAP, pushes it to a device-local temp directory, installs with `bm install -p`, cleans the temp directory, then force-stops and launches the target ability.

## Outputs

- DSL files: `dsl/{qid}.jsonl`
- ArkTS rawfile target: `ArkTs/entry/src/main/resources/rawfile/sample.jsonl`

`sample` must remain JSONL. The runner validates every non-empty line before copying DSL into the ArkTS rawfile directory.
- Screenshots: `output/{qid}.jpeg`
