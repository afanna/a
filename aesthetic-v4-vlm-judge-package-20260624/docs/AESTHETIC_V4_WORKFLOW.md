# aesthetic-v4 VLM Judge 工作流

## 路径

先在当前机器上进入包目录：

```bash
cd /ABSOLUTE/PATH/TO/aesthetic-v4-vlm-judge-package-20260624
PACKAGE_ROOT="$(pwd -P)"
```

后续包内文件都用 `$PACKAGE_ROOT/...` 表达，不写任何人的本地固定路径。

## 输入

输入必须是当前机器上的 HTML 文件或 HTML 目录绝对路径：

```text
/ABSOLUTE/PATH/TO/YOUR_HTML_FILE_OR_DIRECTORY
```

包内自测样例：

```text
$PACKAGE_ROOT/input_html/sample_aesthetic_v4_dashboard.html
```

支持一个 HTML 文件，或一个包含 `.html` / `.htm` 文件的目录。目录会递归扫描，并忽略 `.DS_Store`、`._*` 和 `.zip`。

可选 sidecar 元数据：

```text
/ABSOLUTE/PATH/TO/sample.meta.json
/ABSOLUTE/PATH/TO/metadata.json
/ABSOLUTE/PATH/TO/query_instruction.json
```

sidecar 可包含 `query`、`query_text`、`prompt`、`instruction`、`task`、`description`、`target_viewport`、`ui_type` 等字段。

## 默认配置

默认功能全开，HTML 报告除外：

```text
AESTHETIC_V4_SCREENSHOT_MODE=fullpage
AESTHETIC_V4_MANIFEST_VIEWPORT=all
AESTHETIC_V4_VIEWPORT=all
AESTHETIC_V4_ADAPTIVE_VIEWPORTS=on
AESTHETIC_V4_SCORE_BREAKDOWN=on
AESTHETIC_V4_DESIGNER_REVIEW=on
AESTHETIC_V4_OCCLUSION_OVERLAP_CHECK=always_on
AESTHETIC_V4_OUTPUT_JSON=on
AESTHETIC_V4_OUTPUT_HTML=off
```

模型入口使用 Pangu OpenAI-compatible 网关，通过 `PANGU_JUDGE_MODEL` 切换：

```text
GPT 5.5: PANGU_JUDGE_MODEL=gpt-5.5
Gemini 3.5: PANGU_JUDGE_MODEL=gemini-3.5-flash
Claude 4.7: PANGU_JUDGE_MODEL=claude-opus-4-7-thinking
```

## 输出

默认输出 clean JSON：

```text
$PACKAGE_ROOT/outputs/json/index.json
$PACKAGE_ROOT/outputs/json/*.json
```

每个样本 JSON 包含 `extra_info_scores.aesthetics.score`、完整 6 轴 `axis_weighted_scores`、`adaptive_scores.views[]`、设计师评价、`quality_config`、view 级遮挡检测、截图路径和原始 HTML 路径。

需要 HTML 报告时显式开启：

```text
AESTHETIC_V4_OUTPUT_HTML=on
```

HTML 输出：

```text
$PACKAGE_ROOT/runs/aesthetic-v4/report.html
$PACKAGE_ROOT/runs/aesthetic-v4/report.summary.json
$PACKAGE_ROOT/runs/aesthetic-v4/scores.csv
```

## 遮挡检测

遮挡检测固定开启，不提供关闭入口。命中遮挡或重叠时，不改变 rubric 权重，只降低受影响轴分，再按固定权重汇总到总分。

遮挡类型：

```text
text_text
text_graphic
control_nav
layer_zindex
clipping_crop
unknown
```
