# 附录 A Metric 技术规范（Metric Specification）

Version 2.0

---

# A.1 编写规范

系统中的所有 Metric 必须遵循统一规范。

禁止：

每个 Metric 自己设计接口。

所有 Metric：

必须继承统一接口。

例如：

```python
class BaseMetric:

    def evaluate(
        self,
        context: MetricContext
    ) -> MetricResult:
        ...
```

---

# A.2 Metric 输入

所有 Metric 使用统一输入对象：

```python
MetricContext
```

包含：

```python
class MetricContext:

    query: str

    dsl: dict

    screenshot: np.ndarray

    card_bbox: Rect

    text_blocks: List[TextBlock]

    icon_blocks: List[IconBlock]

    image_blocks: List[ImageBlock]

    colors: List[Color]

    layout_graph: LayoutGraph
```

所有 Detector：

负责生成 Context。

Metric 不允许重新 OCR。

---

# A.3 Metric 输出

统一输出：

```python
MetricResult
```

定义：

```python
class MetricResult:

    name:str

    score:float

    value:float

    ideal:float

    deviation:float

    confidence:float

    formula:str

    details:dict
```

例如：

```json
{
    "name":"Whitespace",
    "score":94.2,
    "value":0.46,
    "ideal":0.42,
    "deviation":0.04,
    "formula":"Gaussian",
    "confidence":0.98
}
```

---

# A.4 Metric 生命周期

每个 Metric：

执行流程固定：

```
Context

↓

读取数据

↓

计算Metric Value

↓

计算Deviation

↓

数学模型

↓

Score

↓

MetricResult
```

禁止：

直接返回：

Pass/Fail。

---

# A.5 Metric 分类

目前系统共有：

20 个 Metric。

分为：

Layout

Visual

Consistency

Information

Intent

五大类。

---

Layout：

Whitespace

Margin

Spacing

Balance

Overflow

Overlap

Visual：

Contrast

Color Harmony

Color Richness

Visual Focus

Visual Balance

Visual Hierarchy

Consistency：

Alignment

Grid

Spacing Consistency

Icon Ratio

Typography Rhythm

Information：

OCR Coverage

Entity Coverage

Intent：

Intent Fitness

Visual Priority

Reading Flow

---

# A.6 Metric 命名规范

统一：

```
Metric名称

↓

Python类

↓

文件名
```

例如：

Whitespace

↓

WhitespaceMetric

↓

whitespace_metric.py

全部保持一致。

---

# A.7 配置读取

所有参数：

必须来自：

yaml。

例如：

```yaml
Whitespace:

    mean:0.42

    sigma:0.10
```

Metric：

禁止：

硬编码。

---

# A.8 Explain规范

每个 Metric：

必须能够生成：

Explain。

例如：

```json
{
    "Metric":"Whitespace",

    "Current":0.46,

    "Ideal":0.42,

    "Deviation":0.04,

    "Formula":"Gaussian",

    "Score":94.2
}
```

HTML：

直接展示。

无需再次计算。

---

# A.9 Confidence

每个 Metric：

必须输出：

Confidence。

例如：

OCR：

可信度：

0.92

颜色：

可信度：

0.98

最终：

Metric Confidence：

```
min(

Detector Confidence

)
```

用于：

提醒人工审核。

不会影响：

Score。

---

# A.10 单元测试规范

每个 Metric：

至少包含：

正常样本

边界样本

异常样本

三类测试。

例如：

Whitespace：

```
正常：

0.42

Score≈100

留白过少：

0.08

Score≈20

留白过多：

0.83

Score≈25
```

所有 Metric：

必须达到：

100%

自动测试覆盖。

---

# A.11 性能要求

单个 Metric：

计算时间：

```
<10ms
```

全部 Metric：

```
<200ms
```

OCR：

除外。

支持：

批量评分。

---

# A.12 可扩展性

新增 Metric：

只允许：

新增一个文件。

例如：

```
shadow_metric.py
```

不得：

修改：

Fusion。

Report。

Judge。

满足：

开放封闭原则（OCP）。
