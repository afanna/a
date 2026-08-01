# DSL 美学校验器

一个零第三方依赖、无需模型、无需截图、无需联网的 HarmonyOS A2UI / GenUI DSL 静态美学风险检查器。

输入 DSL，输出可定位、可解释的中文问题与机器证据。它主要检查能够从 DSL 几何、文字和组件关系中静态证明的三类问题：

1. 内容或文字重叠
2. 文字区域拥挤
3. 文字/控件贴边

核心原则：**证据不足时不猜。** `clear` 只表示当前静态规则没有发现可证明的问题，不等于最终视觉验收通过。

## 1. 运行环境

- Python `3.10+`
- 不需要 `pip install`
- 不读取 PNG、HTML、模型结果或网络
- 生产入口：`dsl_aesthetic.py`
- 核心实现：`validate_aesthetic.py`

检查环境：

```bash
python3 --version
python3 dsl_aesthetic.py --help
```

## 2. 输入是什么

输入必须是包含 A2UI/GenUI 消息的文本，支持三种形式。

### 2.1 JSONL

每行一个 JSON object。推荐生产环境使用这种格式。

```jsonl
{"version":"v0.9","createSurface":{"surfaceId":"demo","catalogId":"ohos.a2ui.extended.catalog","width":146,"height":146}}
{"version":"v0.9","updateComponents":{"surfaceId":"demo","root":"root","components":[{"id":"root","component":"Column","children":["title"],"styles":{"width":146,"height":146,"padding":12}},{"id":"title","component":"Text","content":"今日待办","styles":{"width":100,"height":24,"fontSize":16,"maxLines":1}}]}}
{"version":"v0.9","updateDataModel":{"surfaceId":"demo","path":"/","value":{}}}
```

### 2.2 JSON 数组

将上述消息放在一个 JSON 数组中也可以。

```json
[
  {"version":"v0.9","createSurface":{"surfaceId":"demo","width":146,"height":146}},
  {"version":"v0.9","updateComponents":{"surfaceId":"demo","root":"root","components":[]}}
]
```

### 2.3 Markdown `genui` 代码块

脚本会自动抽取第一段 `genui` fenced block。

````markdown
```genui
{"version":"v0.9","createSurface":{"surfaceId":"demo","width":146,"height":146}}
```
````

### 输入前提

DSL 应至少包含：

- `createSurface`：画布宽高
- `updateComponents`：根组件、组件列表、父子关系和 styles
- 动态文字需要相应 `updateDataModel`，否则相关规则会输出 `undetermined`

本工具不是协议完整性校验器。进入美学校验前，DSL 应先通过业务已有的 A2UI/GenUI schema 与协议校验。

## 3. 如何运行

### 最快体验

检查自带问题样本：

```bash
python3 dsl_aesthetic.py examples/issue-checkbox-gap.jsonl
```

检查自带正常样本：

```bash
python3 dsl_aesthetic.py examples/clear-checkbox-gap.jsonl
```

### 检查自己的 DSL 文件

```bash
python3 dsl_aesthetic.py /path/to/card.jsonl
```

输出 JSON：

```bash
python3 dsl_aesthetic.py /path/to/card.jsonl --format json
```

从标准输入读取：

```bash
python3 dsl_aesthetic.py - --format json < /path/to/card.jsonl
```

CI 严格模式：只要出现 warning 就返回非零退出码。

```bash
python3 dsl_aesthetic.py /path/to/card.jsonl --format json --strict
```

查看完整内部诊断和四态规则判定：

```bash
python3 dsl_aesthetic.py /path/to/card.jsonl --format json --scope internal
```

### 全部参数

```text
python3 dsl_aesthetic.py [path|-]
  --format text|json          输出格式，默认 text
  --scope public|internal     默认 public，仅改变诊断展示范围，不降低门禁状态
  --strict                    warning 也返回退出码 1
  --allow-undetermined        允许 needs_review 返回退出码 0
  --include-contrast          启用可静态证明的文字/背景对比度
  --include-heuristics        启用颜色、层级、密度等探索性代理规则
  --normal-min 4.5            普通文字对比度阈值
  --large-min 3.0             大文字对比度阈值
  --critical-min 3.0          关键文字最低对比度阈值
```

## 4. 输出是什么

### 4.1 文本输出

适合人工查看：

```text
status: pass_with_warnings

问题1：文字/控件贴边
等级：WARNING
代码：AESTHETIC_TEXT_ICON_GAP_LOW
位置：/updateComponents/components/0
说明：文字与相邻图标或勾选框之间缺少可辨的背景间隔。
当前：{"containerId":"root","gap":0.0,...}
期望：{"minimumGap":4.0}
建议：将文字与图标、勾选框之间的有效间距增加到至少 4vp。
```

### 4.2 JSON 输出

适合系统集成、CI、批处理和生成 HTML 报告。顶层结构：

```json
{
  "status": "pass_with_warnings",
  "analysisProfile": "three_visible_evidence",
  "outputScope": "public",
  "summary": {
    "errorCount": 0,
    "warningCount": 1,
    "needsReviewCount": 0,
    "publicDiagnosticCount": 1,
    "internalDiagnosticCount": 0
  },
  "diagnostics": [
    {
      "label": "文字/控件贴边",
      "code": "AESTHETIC_TEXT_ICON_GAP_LOW",
      "jsonPointer": "/updateComponents/components/0",
      "actual": {"containerId": "root", "gap": 0.0},
      "expected": {"minimumGap": 4.0}
    }
  ],
  "internalDiagnostics": [],
  "ruleAssessments": [
    {
      "ruleId": "checkbox_text_clearance",
      "verdict": "issue",
      "certainty": "proven_static_geometry",
      "componentIds": ["root"],
      "reasons": []
    }
  ]
}
```

每条 `diagnostics` 包含：

- `label`：公开中文问题名
- `code`：稳定机器诊断码
- `severity`：`error` 或 `warning`
- `jsonPointer`：问题在 DSL 中的位置
- `message`：问题说明
- `actual`：实际测量或结构证据，通常包含组件 ID、间距或边界
- `expected`：规则要求
- `fixHint`：修复建议

`ruleAssessments` 用于描述规则是否真的具备判断条件：

- `issue`：有静态证据证明存在问题
- `clear`：规则适用，且静态证据证明未发现问题
- `undetermined`：规则适用，但动态值或布局无法静态闭合，必须复核
- `not_applicable`：当前 DSL 没有该规则需要检查的结构

### 4.3 status 与退出码

| status | 含义 | 默认退出码 |
|---|---|---:|
| `pass` | 没有公开问题，也没有未知项 | 0 |
| `pass_with_warnings` | 发现 warning；默认用于人工修正 | 0，使用 `--strict` 时为 1 |
| `needs_review` | 存在动态或不可静态证明的关键项 | 1，使用 `--allow-undetermined` 时为 0 |
| `fail` | 输入读取失败、DSL 前提失败或存在 error | 1 |

`--scope public` 只把非公开诊断移入 `internalDiagnostics`；底层分析产生的
`fail`、`needs_review` 和退出码不会被展示层降级。显式启用的对比度或探索性
规则仍然遵守 fail-closed 门禁。

推荐 CI 使用：

```bash
python3 dsl_aesthetic.py card.jsonl --format json --strict > result.json
```

## 5. 这个脚本主要检测什么

### 5.1 内容或文字重叠

主要检测：

- 固定 Row、Column、List 子项合计尺寸超过容器内容框
- 固定文字框装不下静态或可解析动态文字
- 大字号 CJK 文字与下一行发生可证明的字形区域相交
- Stack 不同分支中的 Text 与 Image 矩形相交
- Stack 内 Row/Column 包装层、`start/center/end/spaceBetween` 和绘制顺序
- 2×2、2×4、numeric root 与 `matchParent` 可求解画布
- 动态单行按钮中孤立 CJK 单字片段与长正文拼接造成的裁切风险

### 5.2 文字区域拥挤

主要检测：

- 固定高度文字堆叠缺少垂直呼吸空间
- 相邻大字号 CJK/混合数字文字有效间距小于 `4vp`
- 至少 3 个可见字符的稳定单行文案，估算宽度超过可用宽度 `120%`
- 固定区域内文本层级过密、与后续分隔或说明文字黏连

### 5.3 文字/控件贴边

主要检测：

- 文字与 Image、Checkbox 等图标有效间距小于 `4vp`
- Checkbox 按 `20vp` 可见绘制内盒计算后挤压文字或相邻行列
- 相邻圆角胶囊/控件有效 gap 小于 `2vp`
- 圆角表面内部文字、按钮与左右边缘留白不足
- Button 或圆角 Text 的固定内容框无法同时容纳字号、行数和 padding
- 当前 StyleMapper 不生效的数组/异常 spacing 导致实际 padding 归零
- 固定 `spaceBetween` Row 按容器剩余宽度计算后的真实净间距不足

### 可选探索性检查

默认关闭，使用参数显式启用：

- `--include-contrast`：文字与可静态证明背景的对比度
- `--include-heuristics`：色彩角色、渐变复杂度、字体层级、圆角/描边/阴影一致性、表面嵌套、信息密度和视觉层级代理

这些探索性结果不应直接当成最终设计结论；但显式启用后，`error` 和
`undetermined` 仍会分别触发 `fail` 和 `needs_review`。

## 6. 不检测什么

这个脚本不能替代真实 Render 或视觉 Agent，默认不负责：

- 图片内部内容、图片中文字、图片真实颜色
- 字体文件、最终 shaping、fallback 和设备渲染差异
- 无法解析的动态数据最终会有多长
- 任意绝对定位、动画中间帧或未建模容器的像素级关系
- “好不好看”“够不够高级”“风格是否统一”等主观判断
- A2UI 协议、业务语义、跳转、事件完整性的全面校验

遇到这些情况，输出应为 `undetermined/needs_review`，或者留给真实渲染 PNG、设备截图与人工验收。

## 7. 推荐集成方式

### Python 子进程

```python
import json
import subprocess

process = subprocess.run(
    ["python3", "dsl_aesthetic.py", "card.jsonl", "--format", "json", "--strict"],
    text=True,
    capture_output=True,
    check=False,
)
report = json.loads(process.stdout)
print(process.returncode, report["status"], report["diagnostics"])
```

### Shell 批处理

```bash
for file in cards/*.jsonl; do
  python3 dsl_aesthetic.py "$file" --format json --strict > "$file.aesthetic.json" || true
done
```

批处理时不要只看退出码；同时保存 JSON 中的 `status`、`diagnostics`、`ruleAssessments` 和 `summary`。

## 8. 构建本地交付包

在源码目录执行：

```bash
python3 build_cli_package.py
```

生成：

```text
dist/
├── dsl-aesthetic-validator-0.6.2/
└── dsl-aesthetic-validator-0.6.2.zip
```

交付包只包含：README、manifest、入口脚本、核心校验器、两份输入示例和带 SHA-256 的 `PACKAGE-MANIFEST.json`。构建过程使用 allowlist，并拒绝个人绝对路径、密钥标记、`.env/.db/.pem/.key` 与 AppleDouble 文件。

解压后的冒烟测试：

```bash
cd dsl-aesthetic-validator-0.6.2
python3 dsl_aesthetic.py examples/issue-checkbox-gap.jsonl --format json
python3 dsl_aesthetic.py examples/clear-checkbox-gap.jsonl --format json
```

## 9. 源码仓库验证

以下命令属于维护者门禁，不是使用校验器的前置条件：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
python3 validate_dsl_agent_calibration.py \
  --audit output/validate-report-final-20260719/dsl-calibration-audit.json
python3 validate_adversarial_generalization.py \
  --audit output/adversarial-generalization-20260721/audit.json \
  --html output/adversarial-generalization-20260721/index.html
```

当前基线：

- 自动化测试：190/190
- DSL 人类区域校准：14/14
- 红蓝队合成泛化：70/70，31 组变形关系
- 五个关键规则族均覆盖 `issue/clear/undetermined/not_applicable`

这些结果表示当前攻击矩阵通过，不表示任意未来 DSL 或视觉 Agent 已获得完整能力。

## 10. 文件说明

| 文件 | 用途 |
|---|---|
| `dsl_aesthetic.py` | 稳定 CLI 入口 |
| `validate_aesthetic.py` | 零依赖核心实现 |
| `examples/*.jsonl` | 可直接运行的问题/正常输入 |
| `manifest.json` | 版本、能力和包内入口合同；源码维护工具单列在 `sourceRepository` |
| `build_cli_package.py` | allowlist 本地打包与隐私审计 |
| `tests/` | 自动化回归 |
| `validate_adversarial_generalization.py` | 红蓝队泛化门禁 |
| `validate_dsl_agent_calibration.py` | 14 例区域绑定回归门禁 |

视觉 Agent、PNG 校准和 HTML 对齐页是规则研发辅助链路，不是该 CLI 的运行依赖，也不能改变 DSL-only 输出。
