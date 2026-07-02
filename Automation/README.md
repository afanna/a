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
- `automation/arkts.py`: copy DSL to ArkTS rawfile, build/install/launch ArkTS, screenshot.
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

Configure DevEco SDK and JDK paths through arguments or environment variables:

```powershell
python Automation\main.py --deveco-sdk-home "D:\DevEco\Sdk" --java-home "D:\DevEco\jbr" --render-wait 10 batch
```

The Python runner performs the ArkTS flow directly: `hvigor clean`, `hvigor assembleHap`, HAP output listing, device temp directory creation, `hdc file send`, `bm install -p`, temp directory cleanup, force-stop, and ability start. `JAVA_HOME\bin` is put first in `PATH` so signing uses the DevEco JDK. `--build-timeout` controls local build and install timeouts. `--render-wait` waits after app launch before taking the screenshot.

`ArkTs/build_and_run.bat` mirrors the same flow and can be kept as a manual debugging helper, but automation no longer depends on it.

## Outputs

- DSL files: `dsl/{qid}.jsonl`
- ArkTS rawfile target: `ArkTs/entry/src/main/resources/rawfile/sample.jsonl`

`sample` must remain JSONL. The runner validates every non-empty line before copying DSL into the ArkTS rawfile directory.
- Screenshots: `output/{qid}.jpeg`
