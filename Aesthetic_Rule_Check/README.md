# Aesthetic Rule Check

纯规则 HarmonyOS 卡片美学检测模块。

本模块只做本地规则检测，不调用外部模型、不调用 VLM、不读取 Query 做语义判断。截图用于布局、视觉设计、设计一致性评分；DSL 只用于信息完整性评分；Query 仅写入报告作为追溯信息。

## 安装依赖

从项目根目录执行：

```powershell
pip install -r Aesthetic_Rule_Check\requirements.txt
```

## 单条检测

```powershell
python Aesthetic_Rule_Check\main.py --image C:\path\to\card.png --dsl Aesthetic_Rule_Check\dsl\q1.jsonl --query "今天北京天气" --out Aesthetic_Rule_Check\reports\q1
```

输出：

- `Aesthetic_Rule_Check\reports\q1\result.json`
- `Aesthetic_Rule_Check\reports\q1\report.html`

`--dsl` 可以不传，也可以传不存在的路径；程序不会中断，信息完整性会按 0 分处理，并在报告 `warnings` 中记录原因。

## 批量检测

图片放在一个目录中，DSL 文件按图片同名匹配。例如：

```text
inputs/
  q1.png
  q2.png
dsl/
  q1.jsonl
  q2.jsonl
```

执行：

```powershell
python Aesthetic_Rule_Check\main.py --input-dir C:\path\to\inputs --dsl-dir Aesthetic_Rule_Check\dsl --out Aesthetic_Rule_Check\reports\batch
```

输出：

- `Aesthetic_Rule_Check\reports\batch\index.html`
- `Aesthetic_Rule_Check\reports\batch\report.html`
- `Aesthetic_Rule_Check\reports\batch\summary.json`
- `Aesthetic_Rule_Check\reports\batch\q1\result.json`
- `Aesthetic_Rule_Check\reports\batch\q1\report.html`
- `Aesthetic_Rule_Check\reports\batch\q2\result.json`
- `Aesthetic_Rule_Check\reports\batch\q2\report.html`

批量参数：

| 参数 | 说明 |
| --- | --- |
| `--input-dir` | 输入图片目录，支持 `.png/.jpg/.jpeg/.bmp/.webp` |
| `--dsl-dir` | DSL 目录，按图片文件名匹配 `.jsonl` 或 `.json` |
| `--recursive` | 递归扫描输入目录 |
| `--out` | 批量输出目录 |
| `--query` | 批量写入报告的追溯文本，不参与评分 |

## 命令参数

| 参数 | 模式 | 说明 |
| --- | --- | --- |
| `--image` | 单条 | 单张卡片截图路径 |
| `--input-dir` | 批量 | 批量图片目录；和 `--image` 二选一 |
| `--dsl` | 单条 | 单张 DSL 路径；缺失时信息完整性为 0 |
| `--dsl-dir` | 批量 | 批量 DSL 目录，按图片 stem 匹配 |
| `--query` | 通用 | 只记录到报告，不参与评分 |
| `--out` | 通用 | 输出目录 |
| `--config` | 通用 | 配置目录，默认 `Aesthetic_Rule_Check/config` |
| `--print-json` | 通用 | 将结果 JSON 输出到控制台 |

## 评分维度

总分为 0~100，按维度加权平均：

```text
overall = sum(dimension_score * dimension_weight) / sum(dimension_weight)
```

默认维度权重在 `config/score.yaml` 中：

| 维度 | 权重 | 数据来源 | 评价内容 |
| --- | ---: | --- | --- |
| 信息完整性 | 20 | DSL + OCR | DSL 中必要显示文字是否出现在截图里 |
| 布局美学 | 30 | Screenshot | 留白、边距、间距、密度、重叠、溢出 |
| 视觉设计 | 35 | Screenshot | 色彩、对比、焦点、重心、图文比例、阅读路径、层级 |
| 设计一致性 | 15 | Screenshot | 对齐、字号节奏、组件尺寸、圆角、Padding、图标尺寸、网格、风格简洁度 |

当前不做场景契合度评分，因为本模块目标是纯美学规则检测，不把评分中心放在 Query 意图理解上。

## 计算公式

### 信息完整性

信息完整性只回答一个问题：DSL 要显示的信息，最终有没有显示。

从 DSL 的 `updateComponents` 中提取 `Text/Button/Label/Title/Subtitle/RichText/TextField` 等组件的 `content/text/label/title/subtitle` 字段；如果字段是 `{ "path": "/..." }`，会从 `updateDataModel` 中按 JSON Pointer 取值；如果是 `${/path}` 或 `$__dataModel.xxx` 表达式，会尽量解析为 DataModel 文本。

| Metric | 公式 | 说明 |
| --- | --- | --- |
| `coverage` | `score = 100 * matched / required` | 必要文字匹配率 |
| `truncation` | `score = 100 * (1 - truncation_rate)` | 部分匹配、疑似省略、低 OCR 可信度越多分越低 |
| `duplicate` | `score = 100 * (1 - duplicate_rate)` | OCR 中重复文字越多分越低 |

维度分：

```text
information = 0.7 * coverage + 0.2 * truncation + 0.1 * duplicate
```

没有 DSL、DSL 文件不存在、DSL 无必要展示文本、或截图无 OCR 文本时，信息完整性为 0。

### 布局美学

布局只看空间关系，不看颜色、不看文字内容。

| Metric | 公式 | 说明 |
| --- | --- | --- |
| `whitespace` | `score = Gaussian(1 - occupied_area / card_area, mean, sigma)` | 留白是否适中 |
| `margin_consistency` | `score = 100 * exp(-cv_k * CV(edge_distances))` | 四周边距是否有秩序 |
| `spacing_rhythm` | `score = 100 * exp(-cv_k * CV(vertical_gaps))` | 垂直间距是否形成节奏 |
| `density` | `score = Gaussian(occupied_area / card_area, mean, sigma)` | 元素密度是否适中 |
| `overlap` | `score = max(0, 100 - penalty_k * max_iou)` | 元素是否互相遮挡 |
| `overflow` | `score = max(0, 100 - penalty_k * overflow)` | 元素是否超出卡片边界 |

`Gaussian(x, mean, sigma)`：

```text
100 * exp(-((x - mean)^2) / (2 * sigma^2))
```

样本不足的指标会标记为 `skipped`，不参与维度加权，避免空白图或元素极少时虚高。

### 视觉设计

视觉设计看第一眼的观感，包括色彩、对比、焦点和层级。

| Metric | 公式 | 说明 |
| --- | --- | --- |
| `color_harmony` | `mean(Gaussian(color_count), Gaussian(avg_lab_distance))` | 主色数量和颜色距离是否协调 |
| `contrast` | `100 / (1 + exp(-k * (min_contrast - target)))` | 文字最小对比度是否达标 |
| `visual_focus` | `Gaussian(max_visual_weight / sum_visual_weight, mean, sigma)` | 是否有明确视觉焦点 |
| `visual_balance` | `Gaussian(weighted_center_offset, 0, sigma)` | 视觉重心是否偏移 |
| `text_image_ratio` | `Gaussian(text_area / occupied_area, mean, sigma)` | 图文比例是否舒适 |
| `reading_flow` | `100 - path_norm * 18 - backtracks * 12` | 阅读路径是否顺畅 |
| `hierarchy` | `Gaussian(Gini(text_visual_weight), mean, sigma)` | 文字层级是否清晰 |

无 OCR 文本时，文字对比、图文比例、阅读路径、层级等文本相关指标给 0，避免空白截图虚高。

视觉权重用于 `visual_focus` 和 `visual_balance`：

```text
text_weight = area * element_weight * contrast_factor * font_factor
other_weight = area * element_weight
```

其中 `contrast_factor` 来自 OCR 文本对比度，`font_factor` 来自 OCR 文本框高度估算的字号，`element_weight` 在 `config/metrics.yaml` 的 `visual.element_weights` 中配置。

### 设计一致性

一致性当前采用纯规则下较稳定可观测的替代指标。字体族、图标风格、圆角、装饰一致性后续可以继续增强，但现阶段不强行做不可靠判断。

| Metric | 公式 | 说明 |
| --- | --- | --- |
| `alignment` | `100 * mean(edge_snap_ratio, center_snap_ratio)` | 元素左边缘和中心线是否对齐 |
| `typography_rhythm` | `Gaussian(font_size_level_count, levels_mean, levels_sigma)` | 字号层级数量是否稳定 |
| `component_size` | `100 * exp(-cv_k * CV(component_area))` | 组件尺寸是否统一 |
| `grid` | `100 * mean(x_snap_ratio, y_snap_ratio)` | 元素坐标是否落在相近网格线上 |
| `corner_radius_consistency` | `100 * exp(-penalty_k * max(0, unique_radius_count - ideal_unique))` | 估算圆角种类是否统一 |
| `padding_consistency` | `100 * exp(-cv_k * CV(padding_values))` | 按钮/标签内部 padding 是否统一 |
| `icon_size_consistency` | `100 * exp(-cv_k * CV(icon_size))` | 图标尺寸是否统一 |
| `style_simplicity` | `Gaussian(dominant_color_count, color_count_mean, color_count_sigma)` | 主色数量是否简洁 |

组件样本不足时，相关指标会 `skipped`，不参与维度加权。

圆角、Padding、图标尺寸都来自截图检测出的视觉元素特征，不读取 DSL 的 `styles.borderRadius`、`styles.padding` 或 `Image.src`。

## 配置怎么改

配置文件支持 YAML 注释，直接手动改：

- `config/score.yaml`：改四个一级维度权重和等级阈值。
- `config/metrics.yaml`：改每个 metric 的权重、理想值、容忍度和扣分敏感度。

常见调整：

| 目标 | 修改方式 |
| --- | --- |
| 更重视视觉设计 | 调高 `score.yaml` 中 `visual.weight` |
| 更重视信息完整性 | 调高 `score.yaml` 中 `information.weight` |
| 留白评分更宽松 | 调大 `metrics.yaml` 中 `layout.whitespace.sigma` |
| 更偏好空一些的卡片 | 调大 `layout.whitespace.mean` |
| 边距不齐扣得更重 | 调大 `layout.margin_consistency.cv_k` |
| 文字相似度匹配更宽松 | 调低 `information.text_match_similarity` |
| 对比度要求更高 | 调大 `visual.contrast.target` |

## 自动化集成接口

后续集成到 `Automation` 流程时，直接调用：

```python
from aesthetic_rule_check import evaluate_card

result = evaluate_card(
    image_path="card.png",
    dsl_path="q1.jsonl",
    query="今天北京天气",
    output_dir="reports/q1",
)
```

返回值是 `EvaluationResult`，可通过 `result.to_dict()` 转成 JSON。

当前 `Automation` 主流程已接入本模块，默认输出位置：

- 卡片图：`output/card/{qid}.png`
- 批量报告：`output/reports/report.html`
- 详情报告：`output/reports/{qid}/report.html`
- 批量结果：`output/reports/summary.json`

## 新增规则

新增规则只需要新增一个 metric 文件，不需要改注册表。

示例：新增 `aesthetic_rule_check/metrics/shadow.py`：

```python
from ..models import MetricResult
from .base import BaseMetric, MetricContext, register_metric


@register_metric
class ShadowMetric(BaseMetric):
    name = "shadow"
    dimension = "visual"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        score = 100.0
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=score,
            value=None,
            ideal=None,
            formula="custom rule",
            details={"config": cfg},
        )
```

然后在 `config/metrics.yaml` 中添加：

```yaml
visual:
  metrics:
    shadow:
      weight: 5
```

如果新增指标没有配置正权重，报告会提示“指标权重未配置为正数”。
