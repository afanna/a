# 小艺 DSL 自动化

本目录包含 Python 主流程，用于执行：

`query -> DSL 提取 -> ArkTS rawfile 复制 -> 构建安装启动 -> 截图 -> 卡片裁切 -> 纯规则美学评分`

当前实现以 Python 为主，保持流程简单、模块化、可维护。

## 目录结构

- `main.py`：命令行入口。
- `automation/hdc.py`：HDC 命令封装。
- `automation/ui_tree.py`：UI 树解析、控件定位和打分。
- `automation/xiaoyi.py`：等待小艺就绪、发送 query、等待回复、提取 DSL。
- `automation/dsl.py`：DSL 关键词搜索、JSON 修复和保存。
- `automation/obs_dsl.py`：从 hilog 中提取 OBS Markdown 链接、下载并解析 genui DSL。
- `automation/arkts.py`：复制 DSL 到 ArkTS rawfile，构建、安装、启动 ArkTS，并截图。
- `automation/pipeline.py`：单条和批量流程编排。
- `automation/card_crop.py`：截图中的卡片区域裁切。
- `Aesthetic_Rule_Check/`：本地纯规则美学评分，不调用外部模型。

## 命令

直接运行一条 query：

```powershell
python Automation\main.py one --qid q_manual --query "你的 query"
```

从 `queries.jsonl` 按 id 运行一条 query：

```powershell
python Automation\main.py one-from-file --qid q1
```

批量模式：

```powershell
python Automation\main.py batch
```

批量模式会先发送所有 query 并收集 DSL 文件；全部 DSL 收集完成后，再逐条渲染、截图、裁切卡片并执行本地规则评分。

指定单台设备运行：

```powershell
python Automation\main.py batch --sn "你的设备SN"
```

多设备并行模式会自动发现所有 HDC 设备，每台设备都会完整执行一遍 `queries.jsonl`：

```powershell
python Automation\main.py parallel --devices auto
```

也可以手动指定设备列表：

```powershell
python Automation\main.py parallel --devices "SN1,SN2" --max-workers 2
```

DevEco SDK 和 JDK 路径可以通过 `Automation/automation/config.py` 顶部的本机配置区维护，也可以通过参数或环境变量覆盖：

```powershell
python Automation\main.py --deveco-sdk-home "D:\DevEco Studio\sdk" --java-home "D:\DevEco Studio\jbr" --render-wait 10 batch
```

也可以把公共参数放在子命令后面：

```powershell
python Automation\main.py batch --deveco-sdk-home "D:\DevEco Studio\sdk" --java-home "D:\DevEco Studio\jbr" --render-wait 10
```

注意：`--deveco-sdk-home` 和 `--java-home` 只是运行参数，不是单独的“设置环境”命令；每次运行仍然需要带 `one`、`one-from-file` 或 `batch` 子命令。

Python runner 会直接执行 ArkTS 流程：`hvigor clean`、`hvigor assembleHap`、打印 HAP 输出目录、创建设备临时目录、`hdc file send`、force-stop、`bm uninstall -n <bundle>`、`bm install -p`、清理临时目录、force-stop、`aa start` 启动 Ability。`JAVA_HOME\bin` 会被放到 `PATH` 最前面，确保签名工具使用 DevEco JDK。`--build-timeout` 控制本地构建和安装超时，`--render-wait` 控制应用启动后等待多久再截图。

## 输出

- DSL 文件：`dsl/{qid}.jsonl`
- OBS Markdown 原文：`output/obs_md/{timestamp}-{qid}.md`
- OBS URL 命中日志：`output/obs_hilog/{timestamp}-{qid}.txt`
- 渲染工程 rawfile 目标：`A2UI_Render/entry/src/main/resources/rawfile/test.json`

DSL 当前按 JSON 数组文件校验，并复制到配置中的渲染工程 rawfile 目标。
- 完整截图：`output/Screenshot/{qid}.jpeg`
- 裁切卡片：`output/card/{qid}.png`
- DSL 最终失败 hilog：`output/logs/{timestamp}-{qid}.txt`
- 纯规则评分报告：`output/reports/report.html`
- 单条详情报告：`output/reports/{qid}/report.html`
- 纯规则评分结果：`output/reports/summary.json`

使用 `parallel` 时，输出会按设备隔离：

- DSL 文件：`dsl/{safe_sn}/{qid}.jsonl`
- OBS Markdown 原文：`output/{safe_sn}/obs_md/{timestamp}-{qid}.md`
- OBS URL 命中日志：`output/{safe_sn}/obs_hilog/{timestamp}-{qid}.txt`
- 渲染工程工作副本：`Automation/.work/devices/{safe_sn}/A2UI_Render`
- 完整截图：`output/{safe_sn}/Screenshot/{qid}.jpeg`
- 裁切卡片：`output/{safe_sn}/card/{qid}.png`
- DSL 最终失败 hilog：`output/{safe_sn}/logs/{timestamp}-{qid}.txt`
- 纯规则评分报告：`output/{safe_sn}/reports/report.html`

## DSL 失败日志

当某条 query 连续重试后仍没有生成 DSL 时，自动化会抓取一段设备 hilog，便于后续分析小艺侧失败原因。默认抓取 5 秒，文件名为 `时间戳-query名.txt`，默认保存到 `output/logs`。

配置位置：`Automation/config/automation.json`

```json
"dsl_source": "obs",
"obs_hilog_timeout": 400,
"obs_download_timeout": 15,
"obs_markdown_dir": null,
"obs_hilog_match_dir": null,
"hilog_on_dsl_failure": true,
"hilog_capture_seconds": 5,
"hilog_output_dir": null
```

`dsl_source` 默认使用 OBS 方案：发送 query 后清理 hilog 缓冲，启动 `hdc shell hilog` 流式读取，匹配 OBS `.md` 链接并下载解析其中的 `genui` 代码块。需要回到旧 UI 树提取时可设为 `ui`；需要 OBS 失败后尝试旧方案时可设为 `auto`。

## 常用命令

以下命令默认在项目根目录 `C:\Users\afan\Desktop\Automation-screenshot` 下执行。

### 全流程执行

批量发送 query、提取 DSL、构建渲染、截图、裁切、纯规则评分：

```powershell
python Automation\main.py batch
```

多设备并行全流程：

```powershell
python Automation\main.py parallel --devices auto
```

指定多设备：

```powershell
python Automation\main.py parallel --devices "SN1,SN2" --max-workers 2
```

### 仅批量发送 Query 提取 DSL

```powershell
python Automation\main.py collect-dsl
```

指定 query 文件：

```powershell
python Automation\main.py collect-dsl --queries queries.jsonl
```

### 单独批量渲染 DSL 并截图

渲染 `dsl` 目录下所有 `.jsonl` 文件并截图：

```powershell
python Automation\main.py render-dsl-dir --dsl-dir dsl
```

渲染后同时裁切卡片：

```powershell
python Automation\main.py render-dsl-dir --dsl-dir dsl --enable-card-crop
```

### 单独批量裁切

裁切 `output` 目录下已有截图：

```powershell
python Automation\main.py crop-card --input output --output output
```

### 单独批量模型评分

对 `output` 目录下图片批量评分并生成报告：

```powershell
python Automation\main.py aesthetics --input output --output output
```

### 单独纯规则评分

对已经裁切好的卡片图执行本地纯规则评分：

```powershell
python Aesthetic_Rule_Check\main.py --input-dir output\card --dsl-dir dsl --out output\reports
```
