# Aesthetic_Rule_Check · A2UI 卡片纯规则美学评分

本目录是**纯规则**的 A2UI 卡片美学评分包，从源项目完整复制进本仓库，
自包含、无外部目录依赖，可随仓库一起分享到 GitHub。

- 不调用任何外部模型 / API，全部本地计算。
- 输入：卡片截图（必需）+ DSL 文件（可选）+ query 文本（可选）。
- 输出：0–100 总分（含封顶 cap 机制）、等级、各维度分、扣分项清单，
  以及单样本 `result.json` + `report.html`（内嵌 base64 图片）。

## 目录结构

```
Aesthetic_Rule_Check/
├── aesthetic_rule_check/   # 评分包（api/config/deductions/dsl/fusion/metrics/...）
└── config/                 # 评分配置
    ├── metrics.yaml        # 各指标阈值与理想区间
    └── score.yaml          # 维度权重、等级线、封顶规则
```

## 用法

由自动化流水线自动调用（`Automation/config/automation.json` 中
`enable_rule_check: true`），也可以单独使用：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("Aesthetic_Rule_Check").resolve()))
from aesthetic_rule_check import evaluate_card

result = evaluate_card(
    image_path="output/weather_card_01.png",       # 卡片截图
    dsl_path="dsl/weather_card_01.jsonl",          # 可选
    query="创建一张包含深圳天气信息的小卡片。",       # 可选
    output_dir="output/reports/weather_card_01",   # 传入则写 result.json + report.html
    config_dir="Aesthetic_Rule_Check/config",      # 可选，缺省用包旁 config/
)
print(result.overall, result.grade)
```

## 依赖

```
numpy>=1.26
opencv-python>=4.8
PyYAML>=6.0
rapidocr_onnxruntime>=1.3
```

首次运行 rapidocr 会自动加载本地 OCR 模型，耗时较长属正常现象。
