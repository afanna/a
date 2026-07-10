# aesthetic-v4 VLM Judge Package

这个包用于把本地 HTML 渲染成截图，再用 aesthetic-v4 VLM Judge 输出结构化设计质量评价。默认输出 clean JSON；需要浏览器报告时可以显式开启 HTML 输出。

## 路径约定

不要复制其他人的本地路径。先在当前机器上进入这个包所在目录，并设置包根目录：

```bash
cd /ABSOLUTE/PATH/TO/aesthetic-v4-vlm-judge-package-20260624
PACKAGE_ROOT="$(pwd -P)"
```

`PACKAGE_ROOT` 展开后就是当前机器上的包根目录绝对路径。后续命令都使用它。

## 输入

真实输入必须是当前机器上的绝对路径。支持两类输入：

- HTML 文件或 HTML 目录。
- PNG/JPG 截图图片。

```text
/ABSOLUTE/PATH/TO/YOUR_HTML_FILE_OR_DIRECTORY
/ABSOLUTE/PATH/TO/YOUR_SCREENSHOT.png
```

包内自测样例：

```bash
"$PACKAGE_ROOT/input_html/sample_aesthetic_v4_dashboard.html"
```

HTML 输入会渲染桌面端和移动端长截图。图片输入会跳过 HTML 渲染，直接按单图评分。输入目录会递归扫描 `.html` / `.htm`，并忽略 `.DS_Store`、`._*` 和 `.zip`。

可选 sidecar 元数据：

```text
/ABSOLUTE/PATH/TO/sample.meta.json
/ABSOLUTE/PATH/TO/metadata.json
/ABSOLUTE/PATH/TO/query_instruction.json
```

sidecar 可包含 `query`、`query_text`、`prompt`、`instruction`、`task`、`description`、`target_viewport`、`ui_type` 等字段。

## 配置

复制配置模板：

```bash
cp "$PACKAGE_ROOT/config/aesthetic-v4.env.example" "$PACKAGE_ROOT/config/aesthetic-v4.env"
```

在本机配置文件里填写私有 key：

```text
$PACKAGE_ROOT/config/aesthetic-v4.env
```

模型入口使用 Pangu OpenAI-compatible API。第一次使用时只需要在 `config/aesthetic-v4.env` 里填好 `PANGU_API_KEY`；之后传入 HTML 或 PNG/JPG 图片，就可以直接输出 clean JSON。

默认 Pangu 配置通过 `PANGU_JUDGE_MODEL` 切换模型：

```text
GPT 5.5: PANGU_JUDGE_MODEL=gpt-5.5
Gemini 3.5: PANGU_JUDGE_MODEL=gemini-3.5-flash
Claude 4.7: PANGU_JUDGE_MODEL=claude-opus-4-7-thinking
```

## API 调用方式

这里的 API 指 Pangu 模型网关 API，不是需要单独启动的 HTTP 服务。本包对外调用入口是 `pipeline/run_aesthetic_v4.sh`；脚本内部会调用 Pangu OpenAI-compatible chat completions API。

只需要配置一次：

```text
PANGU_BASE_URL=http://43.139.21.243:4000
PANGU_API_KEY=
PANGU_JUDGE_MODEL=claude-opus-4-7-thinking
```

同事正常使用时不需要直接调用 Pangu 脚本，也不需要手写 `curl`。把 key 和模型写进 `config/aesthetic-v4.env` 后，运行下面的主命令即可。

默认质量配置：

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

## 执行流程

一次运行会按顺序完成：

1. 如果输入是 HTML 文件或目录，生成 `manifest.jsonl`，再用 Playwright 渲染桌面端和移动端长截图。
2. 如果输入是 PNG/JPG 图片，跳过 HTML 渲染，直接把图片送入评分。
3. 调用 Pangu API，得到 aesthetic-v4 评分、6 轴分数、设计师评价和遮挡检测。
4. HTML 输入会聚合 mobile/web 结果，默认取较低视口作为保守总分；图片输入按单图输出。
5. 导出 clean JSON 到 `outputs/json`。
6. 自动校验 clean JSON 结构。
7. 如果 `AESTHETIC_V4_OUTPUT_HTML=on`，额外生成 HTML 报告。

## 安装依赖

```bash
cd "$PACKAGE_ROOT/pipeline"
npm install
python3 -m pip install -r "$PACKAGE_ROOT/pipeline/requirements.txt"
```

## 运行

运行真实模型，输入 HTML 文件或 HTML 目录：

```bash
cd "$PACKAGE_ROOT"
AESTHETIC_V4_RUN_DIR="$PACKAGE_ROOT/runs/aesthetic-v4" \
bash "$PACKAGE_ROOT/pipeline/run_aesthetic_v4.sh" \
/ABSOLUTE/PATH/TO/YOUR_HTML_FILE_OR_DIRECTORY
```

运行真实模型，输入 PNG/JPG 图片：

```bash
cd "$PACKAGE_ROOT"
AESTHETIC_V4_RUN_DIR="$PACKAGE_ROOT/runs/aesthetic-v4" \
bash "$PACKAGE_ROOT/pipeline/run_aesthetic_v4.sh" \
/ABSOLUTE/PATH/TO/YOUR_SCREENSHOT.png
```

指定模型：

```bash
cd "$PACKAGE_ROOT"
PANGU_JUDGE_MODEL=gpt-5.5 \
AESTHETIC_V4_RUN_DIR="$PACKAGE_ROOT/runs/aesthetic-v4" \
bash "$PACKAGE_ROOT/pipeline/run_aesthetic_v4.sh" \
/ABSOLUTE/PATH/TO/YOUR_HTML_FILE_OR_DIRECTORY
```

只检查流程，不调用真实模型：

```bash
cd "$PACKAGE_ROOT"
AESTHETIC_V4_RUN_DIR="$PACKAGE_ROOT/runs/aesthetic-v4" \
bash "$PACKAGE_ROOT/pipeline/run_aesthetic_v4.sh" \
--mock \
"$PACKAGE_ROOT/input_html/sample_aesthetic_v4_dashboard.html"
```

## 默认 JSON 输出

默认 clean JSON 输出：

```text
$PACKAGE_ROOT/outputs/json/index.json
$PACKAGE_ROOT/outputs/json/*.json
```

内部运行文件：

```text
$PACKAGE_ROOT/runs/aesthetic-v4/manifest.jsonl
$PACKAGE_ROOT/runs/aesthetic-v4/screenshots/render_manifest.jsonl
$PACKAGE_ROOT/runs/aesthetic-v4/scores.jsonl
$PACKAGE_ROOT/runs/aesthetic-v4/score_cache.jsonl
```

如果要把 clean JSON 输出到其他绝对路径：

```bash
cd "$PACKAGE_ROOT"
AESTHETIC_V4_JSON_OUT_DIR=/ABSOLUTE/PATH/TO/json \
AESTHETIC_V4_JSON_INDEX=/ABSOLUTE/PATH/TO/json/index.json \
AESTHETIC_V4_RUN_DIR="$PACKAGE_ROOT/runs/aesthetic-v4" \
bash "$PACKAGE_ROOT/pipeline/run_aesthetic_v4.sh" \
/ABSOLUTE/PATH/TO/YOUR_HTML_FILE_OR_DIRECTORY
```

## 可选 HTML 输出

需要 HTML 报告时开启：

```bash
cd "$PACKAGE_ROOT"
AESTHETIC_V4_OUTPUT_HTML=on \
AESTHETIC_V4_RUN_DIR="$PACKAGE_ROOT/runs/aesthetic-v4" \
bash "$PACKAGE_ROOT/pipeline/run_aesthetic_v4.sh" \
/ABSOLUTE/PATH/TO/YOUR_HTML_FILE_OR_DIRECTORY
```

HTML 输出：

```text
$PACKAGE_ROOT/runs/aesthetic-v4/report.html
$PACKAGE_ROOT/runs/aesthetic-v4/report.summary.json
$PACKAGE_ROOT/runs/aesthetic-v4/scores.csv
```

需要人工质检聚合页时：

```bash
python3 "$PACKAGE_ROOT/pipeline/scripts/build_manual_qc.py" \
--index "$PACKAGE_ROOT/outputs/json/index.json" \
--out "$PACKAGE_ROOT/manual_qc/index.html"
```

人工质检页输出：

```text
$PACKAGE_ROOT/manual_qc/index.html
```

## JSON 格式

所有对外 JSON 分数都按 100 分制输出。`score` 表示 100 分制分数；`weighted_contribution_100 = score * weight`。

### index.json

`index.json` 是入口索引，负责列出本次输出的所有样本 JSON：

```json
{
  "schema_version": 1,
  "record_count": 1,
  "records": [
    {
      "id": "sample_id",
      "qid": "sample_id",
      "html_path": "/ABSOLUTE/PATH/TO/input.html",
      "json_path": "/ABSOLUTE/PATH/TO/outputs/json/sample_id.json",
      "score": 63.8,
      "aggregate_view": "mobile",
      "occlusion_overlap_check": {
        "detected": true,
        "status": "fail",
        "failed_views": ["web"],
        "passed_views": ["mobile"]
      },
      "screenshots": [
        "/ABSOLUTE/PATH/TO/mobile.png",
        "/ABSOLUTE/PATH/TO/web.png"
      ]
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `schema_version` | clean JSON 索引结构版本。 |
| `record_count` | 本次输出的样本数量。 |
| `records[]` | 每个样本一条索引记录。 |
| `records[].id` | 样本内部 id。 |
| `records[].qid` | 面向检索和对齐的样本 id。 |
| `records[].html_path` | 被评估 HTML 的绝对路径。 |
| `records[].json_path` | 该样本 clean JSON 的绝对路径。 |
| `records[].score` | 汇总后的 100 分制美学分数。 |
| `records[].aggregate_view` | 汇总分采用的视口，通常是 `mobile` 或 `web`。 |
| `records[].occlusion_overlap_check` | 遮挡/重叠检测汇总，只列通过和失败的视口。 |
| `records[].screenshots` | 本次评估使用的截图绝对路径。 |

### 单样本 JSON

下面是单样本 JSON 的结构骨架。数组 item 只展示字段形状；实际输出中 `aesthetic_rubric`、`extra_info_scores.aesthetics.axis_weighted_scores`、`adaptive_scores.views[].axis_weighted_scores` 都固定包含完整 6 个维度。

```json
{
  "schema_version": 1,
  "id": "sample_dashboard",
  "qid": "sample_dashboard",
  "profile": "aesthetic_v4",
  "rubric_version": "aesthetic_static_v1",
  "html_path": "/ABSOLUTE/PATH/TO/input.html",
  "status": "scored",
  "quality_config": {
    "adaptive_viewports": "on",
    "designer_review": "on",
    "occlusion_overlap_check": "always_on",
    "score_breakdown": "on"
  },
  "aesthetic_rubric": [
    {
      "id": "visual_impact_originality",
      "display_id": "A1",
      "name": "视觉冲击 / 原创性",
      "weight": 0.3,
      "weight_percent": 30,
      "desc": "该维度的评价说明",
      "score_rule": "该维度的 100 分制评分规则",
      "hard_fail": false
    }
  ],
  "extra_info_scores": {
    "aesthetics": {
      "score": 63.8,
      "status": "success",
      "aggregate_strategy": "mobile_web_min",
      "aggregate_view": "mobile",
      "axis_weighted_scores": [
        {
          "id": "visual_impact_originality",
          "display_id": "A1",
          "name": "视觉冲击 / 原创性",
          "score": 70,
          "weight": 0.3,
          "weighted_contribution_100": 21
        }
      ]
    }
  },
  "adaptive_scores": {
    "enabled": true,
    "strategy": "mobile_web_min",
    "aggregate_view": "mobile",
    "views": [
      {
        "view": "mobile",
        "score": 63.8,
        "axis_weighted_scores": [
          {
            "id": "visual_impact_originality",
            "display_id": "A1",
            "name": "视觉冲击 / 原创性",
            "score": 70,
            "weight": 0.3,
            "weighted_contribution_100": 21
          }
        ],
        "designer_review": {
          "pros": ["主题明确，信息结构基本清楚。"],
          "cons": ["移动端底部区域拥挤，基础可用性分偏低。"],
          "suggestions": ["增加底部留白，减少核心按钮和导航的视觉冲突。"]
        },
        "occlusion_overlap_check": {
          "status": "pass",
          "detected": false,
          "types": [],
          "affected_axes": [],
          "findings": []
        }
      },
      {
        "view": "web",
        "score": 71.2,
        "axis_weighted_scores": [
          {
            "id": "visual_impact_originality",
            "display_id": "A1",
            "name": "视觉冲击 / 原创性",
            "score": 76,
            "weight": 0.3,
            "weighted_contribution_100": 22.8
          }
        ],
        "designer_review": {
          "pros": ["桌面端层级更稳定，视觉重心更清楚。"],
          "cons": ["右上角浮层遮挡筛选按钮，影响基础可用性和局部层级。"],
          "suggestions": ["调整浮层 z-index 和间距，确保按钮文字和操作区域完整可见。"]
        },
        "occlusion_overlap_check": {
          "status": "fail",
          "detected": true,
          "types": ["control_nav", "layer_zindex"],
          "affected_axes": ["composition_hierarchy", "basic_usability"],
          "findings": [
            {
              "type": "control_nav",
              "severity": "medium",
              "target": "右上角筛选按钮",
              "evidence": "浮层导航遮住了筛选按钮文字，按钮状态不可稳定识别。",
              "affected_axes": ["basic_usability", "composition_hierarchy"]
            }
          ],
          "score_impact": {
            "affected_axis_breakdown": [
              {
                "id": "composition_hierarchy",
                "display_id": "A2",
                "name": "构图层级",
                "score_after_occlusion": 72,
                "weight": 0.2,
                "weighted_loss_100": 1.2
              }
            ],
            "total_weighted_loss_100": 2.4
          }
        }
      }
    ]
  },
  "occlusion_overlap_check": {
    "status": "fail",
    "detected": true,
    "failed_views": ["web"],
    "passed_views": ["mobile"]
  },
  "links": {
    "html": "/ABSOLUTE/PATH/TO/input.html",
    "screenshots": [
      "/ABSOLUTE/PATH/TO/mobile.png",
      "/ABSOLUTE/PATH/TO/web.png"
    ]
  }
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `schema_version` | 单样本 clean JSON 结构版本。 |
| `id` / `qid` | 样本 id；`qid` 用于跨文件对齐。 |
| `profile` | 当前评价 profile，固定为 aesthetic-v4 体系。 |
| `rubric_version` | 当前评分维度版本。 |
| `html_path` | 被评估 HTML 的绝对路径。 |
| `status` | 样本评分状态；成功时为 `scored`。 |
| `quality_config` | 本次运行的质量开关；默认长图、自适应、设计师评价、权重明细、遮挡检测都开启。 |
| `aesthetic_rubric[]` | 固定 6 个美学维度的定义。每个 item 描述维度 id、展示 id、名称、权重、说明和评分规则。 |
| `extra_info_scores.aesthetics.score` | 汇总后的最终 100 分制美学分数。 |
| `extra_info_scores.aesthetics.status` | 美学评分是否成功。 |
| `extra_info_scores.aesthetics.aggregate_strategy` | 多视口汇总策略；默认 `mobile_web_min`，取 mobile/web 中较低结果作为保守总分。 |
| `extra_info_scores.aesthetics.aggregate_view` | 最终汇总分来自哪个视口。 |
| `axis_weighted_scores[]` | 固定 6 个维度的分数明细。`score` 是该维度 100 分制分数；`weight` 是权重；`weighted_contribution_100 = score * weight`。 |
| `adaptive_scores.enabled` | 是否开启自适应视口评分。 |
| `adaptive_scores.views[]` | 每个视口一条记录，通常包含 `mobile` 和 `web`。 |
| `adaptive_scores.views[].score` | 该视口的 100 分制美学分数。 |
| `adaptive_scores.views[].designer_review` | 设计师口吻评价，包含优点、问题和建议。 |
| `adaptive_scores.views[].occlusion_overlap_check` | 该视口的遮挡/重叠检测结果。通过为 `pass`，失败为 `fail`。 |
| `score_impact` | 只在某个视口遮挡失败时出现，说明受影响维度、遮挡后的维度分、权重和损失分。 |
| `occlusion_overlap_check` | 顶层遮挡汇总，只列 `failed_views` 和 `passed_views`，不替代 view 级详情。 |
| `links.html` | 被评估 HTML 的绝对路径。 |
| `links.screenshots[]` | 本次评分截图的绝对路径。 |

固定 6 个维度：

| display_id | id | name | weight |
| --- | --- | --- | --- |
| A1 | `visual_impact_originality` | 视觉冲击 / 原创性 | 0.30 |
| A2 | `composition_hierarchy` | 构图层级 | 0.20 |
| A3 | `typography` | 字体表现 | 0.15 |
| A4 | `color_material` | 色彩与材质 | 0.15 |
| A5 | `detail_finish` | 细节完成度 | 0.15 |
| A6 | `basic_usability` | 基础可用性 | 0.05 |
