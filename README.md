# Xiaoyi UI Render Automation

这是一个用于 HarmonyOS 卡片生成链路的数据采集和渲染自动化工具。

当前主流程已经调整为：

```text
Query -> 小艺生成 DSL -> 提取 DSL -> ArkTS 渲染 -> 截图 -> 裁切卡片 -> 停止
```

普通自动化流程不再自动执行规则评分或视觉模型评分。最终 `output` 目录只保留裁切后的卡片图，文件名使用 query id，例如：

```text
output/weather_card_01.png
```

完整截图只作为中间产物使用，裁切完成后会自动删除。日志、裁切 debug 图和临时工作目录会写入 `Automation/.work/`，避免污染最终数据目录。

## 适用场景

- 批量向小艺发送 query，提取生成的 DSL。
- 使用 ArkTS 工程自动渲染 DSL。
- 从整屏截图中裁切出卡片图片。
- 为后续规则评分、视觉教师评分、规则标定迭代准备干净数据。
- 多设备并行采集 DSL 和卡片图片。

## 环境要求

- Python 3.10+
- DevEco Studio，本机默认路径参考 `Automation/config/automation.json`
- HDC 可用，并且设备或模拟器已开启调试
- HarmonyOS ArkTS 工程可正常构建、签名、安装

验证环境：

```powershell
python --version
hdc list targets
```

## 快速开始

### 1. 准备 query

在项目根目录维护 `queries.jsonl`，每行一个用例：

```json
{"qid": "weather_card_01", "query": "生成一个天气卡片，展示今天温度、天气状态和未来三小时趋势"}
{"qid": "todo_card_01", "query": "生成一个待办事项卡片，展示今天的三个待办和完成进度"}
```

`qid` 会作为最终卡片图片文件名的一部分，请保持唯一、稳定、可读。

### 2. 单条运行

```powershell
python Automation\main.py one --qid weather_card_01 --query "生成一个天气卡片"
```

成功后主要产物：

```text
dsl/weather_card_01.jsonl
output/weather_card_01.png
```

### 3. 从 queries.jsonl 跑单条

```powershell
python Automation\main.py one-from-file --qid weather_card_01
```

### 4. 批量运行

```powershell
python Automation\main.py batch
```

指定 query 文件：

```powershell
python Automation\main.py batch --queries .\queries.jsonl
```

### 5. 多设备并行

自动发现在线设备：

```powershell
python Automation\main.py parallel --devices auto
```

指定设备：

```powershell
python Automation\main.py parallel --devices SN1,SN2 --max-workers 2
```

多设备模式下产物会按设备隔离，避免互相覆盖。

## 命令说明

### `one`

发送一条 query，提取 DSL，渲染截图，并裁切卡片。

```powershell
python Automation\main.py one --qid test_weather --query "生成一个天气卡片"
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--qid` | 用例 ID，默认 `manual` |
| `--query` | 发送给小艺的 query，必填 |
| `--sn` | 指定设备 SN |
| `--debug` | 开启详细日志 |

### `one-from-file`

从 `queries.jsonl` 中按 `qid` 找到一条用例并运行。

```powershell
python Automation\main.py one-from-file --qid weather_card_01
```

### `batch`

批量运行 query 文件中的全部用例。

```powershell
python Automation\main.py batch --queries .\queries.jsonl
```

### `collect-dsl`

只发送 query 并保存 DSL，不渲染、不截图、不裁切。

```powershell
python Automation\main.py collect-dsl --queries .\queries.jsonl
```

### `render-dsl-dir`

渲染已有 DSL 文件，截图后裁切卡片。

```powershell
python Automation\main.py render-dsl-dir --dsl-dir .\dsl
```

### `crop-card`

单独裁切已有截图。这个命令适合调试裁切坐标。

```powershell
python Automation\main.py crop-card --input .\output\raw.jpeg --output .\output\raw_card.png --card-crop-debug
```

也可以裁切目录内所有图片：

```powershell
python Automation\main.py crop-card --input .\output --output .\output\cards --card-crop-debug
```

### `aesthetics`

独立视觉评分命令。它不会在普通自动化流程中自动执行，只用于你手动对已有图片生成视觉评分报告。

```powershell
python Automation\main.py aesthetics `
  --input .\output `
  --output .\output `
  --enable-aesthetics `
  --aesthetics-base-url "你的模型接口地址" `
  --aesthetics-api-key "你的API Key"
```

不要把 API key 写入代码或提交到 Git。

## 输出目录

单设备默认输出：

```text
项目根目录/
├── dsl/
│   └── {qid}.jsonl                 # 提取到的 DSL
├── output/
│   └── {qid}.png                   # 裁切后的卡片图，最终保留
└── Automation/
    └── .work/
        ├── logs/
        │   └── pipeline.log        # 运行日志
        ├── logs/card_crop_debug/   # 裁切红框 debug 图，仅开启 debug 时生成
        └── devices/                # 多设备 ArkTS 工作副本
```

多设备或指定 artifact namespace 时，会按设备 SN 隔离，例如：

```text
dsl/{SN}/{SN}_{qid}.jsonl
output/{SN}/{SN}_{qid}.png
Automation/.work/logs/{SN}/pipeline.log
```

## 裁切坐标配置

裁切配置文件：

```text
Automation/config/card_crop.json
```

当前已经改成绝对坐标模式，可以直接填写开发者选项里看到的屏幕坐标。

核心字段：

```json
{
  "crop_box_2x2": { "x1": 364, "y1": 97, "x2": 920, "y2": 577 },
  "crop_box_2x4": { "x1": 95, "y1": 97, "x2": 1192, "y2": 577 },
  "detect_box": { "x1": 0, "y1": 97, "x2": 1280, "y2": 577 },
  "card_type": "auto"
}
```

含义：

| 字段 | 说明 |
| --- | --- |
| `crop_box_2x2` | 2x2 小卡片裁切框 |
| `crop_box_2x4` | 2x4 宽卡片裁切框 |
| `detect_box` | `auto` 模式下判断卡片类型的检测区域 |
| `card_type` | `auto`、`2x2`、`2x4` |

坐标说明：

```text
(x1, y1) = 左上角
(x2, y2) = 右下角
```

如果你想强制裁 2x4：

```json
"card_type": "2x4"
```

如果你想让程序自动判断：

```json
"card_type": "auto"
```

配置文件支持 `//` 和 `/* ... */` 注释，也兼容 UTF-8 BOM。

## 运行配置

主配置文件：

```text
Automation/config/automation.json
```

配置优先级：

```text
命令行参数 > Automation/config/automation.json > 环境变量或代码默认值
```

当前关键默认值：

| 配置 | 当前默认 | 说明 |
| --- | --- | --- |
| `context_clear_enabled` | `false` | 是否在每条 DSL 保存成功后清理小艺上下文 |
| `context_clear_points` | `[{ "x": 1150, "y": 255 }]` | 清理上下文点击坐标 |
| `enable_card_crop` | `true` | 截图后自动裁切卡片 |
| `enable_rule_check` | `false` | 普通流程不执行规则评分 |
| `card_crop_config` | `Automation/config/card_crop.json` | 裁切坐标配置 |

上下文清理说明：

默认不会清理上下文。需要开启时，有两种方式。

方式一，临时通过命令行开启：

```powershell
python Automation\main.py one --qid weather_card_01 --query "生成一个天气卡片" --enable-context-clear
```

方式二，在 `Automation/config/automation.json` 中长期开启：

```json
"context_clear_enabled": true,
"context_clear_points": [{ "x": 1150, "y": 255 }],
"context_clear_wait": 1
```

这表示每条 query 的 DSL 保存成功后，程序会点击屏幕坐标 `(1150, 255)` 来清理小艺上下文。

## 日志

日志默认写入：

```text
Automation/.work/logs/pipeline.log
```

多设备时：

```text
Automation/.work/logs/{SN}/pipeline.log
```

开启详细日志：

```powershell
python Automation\main.py batch --debug
```

排查问题时优先搜索：

```text
ERROR
WARNING
```

## 项目结构

```text
Automation-screenshot/
├── Automation/
│   ├── main.py                     # CLI 入口
│   ├── automation/
│   │   ├── pipeline.py             # 主流程编排
│   │   ├── xiaoyi.py               # 小艺交互与 DSL 提取
│   │   ├── arkts.py                # ArkTS 构建、安装、启动、截图
│   │   ├── card_crop.py            # 卡片裁切
│   │   ├── hdc.py                  # HDC 封装
│   │   ├── dsl.py                  # DSL 解析与保存
│   │   ├── queries.py              # query 文件读取
│   │   └── logger.py               # 日志
│   ├── config/
│   │   ├── automation.json         # 主运行配置
│   │   └── card_crop.json          # 裁切坐标配置
│   └── .work/                      # 临时工作目录和日志
├── A2UI_Render/                    # HarmonyOS 渲染工程模板
├── Aesthetic_Rule_Check/           # 规则评分项目，普通流程不自动调用
├── visual_aesthetics/              # 独立视觉评分模块
├── dsl/                            # DSL 产物
├── output/                         # 最终卡片图片
├── queries.jsonl                   # query 用例库
└── README.md
```

## 常见问题

### 找不到设备

```powershell
hdc list targets
```

如果没有设备，检查 USB 调试、模拟器状态、HDC 环境变量。

### DSL 提取失败

优先检查：

- 小艺是否处于可输入状态
- query 是否已经发送成功
- 网络是否导致小艺回复超时
- `Automation/.work/logs/pipeline.log` 中是否有 `ERROR`

必要时可以在 `Automation/config/automation.json` 中调大：

```json
"post_query_wait": 30,
"query_attempt_timeout": 90,
"query_max_attempts": 3
```

### 裁切位置不对

打开 `Automation/config/card_crop.json`，按开发者选项看到的坐标修改：

```json
"crop_box_2x2": { "x1": 364, "y1": 97, "x2": 920, "y2": 577 }
```

调试时运行：

```powershell
python Automation\main.py crop-card --input .\output\raw.jpeg --output .\output\raw_card.png --card-crop-debug
```

红框 debug 图会帮助确认裁切框位置。

### 为什么没有评分报告

这是当前设计：普通流程只负责生成 DSL 和裁切卡片，不再自动评分。

后续迭代要做“视觉教师报告 + 规则报告 + 自动比对 + 参数建议”时，建议在新项目或独立迭代脚本里消费这里生成的：

```text
dsl/
output/
queries.jsonl
```

### 中间截图去哪了

中间截图用于裁切，裁切完成后会删除。最终只保留：

```text
output/{qid}.png
```

## 开发验证

修改 Python 代码后至少运行：

```powershell
python -m py_compile Automation\main.py Automation\automation\pipeline.py Automation\automation\arkts.py Automation\automation\hdc.py Automation\automation\xiaoyi.py Automation\automation\card_crop.py
```

有设备时再跑最小链路：

```powershell
python Automation\main.py one --qid test --query "生成一个测试卡片"
```

成功信号：

- `dsl/test.jsonl` 存在
- `output/test.png` 存在
- `Automation/.work/logs/pipeline.log` 没有致命错误

## 注意事项

- 不要提交 API key、`.env`、日志、截图、缓存和临时工作目录。
- `A2UI_Render/` 是渲染模板工程，改动前需要明确确认。
- 普通流程不调用视觉模型，也不调用规则评分。
- `aesthetics` 命令只用于手动离线评测已有图片。
- 规则迭代和视觉教师标定建议作为后续独立项目处理。
