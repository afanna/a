# Card Aesthetic Scoring System（卡牌美学评分系统）

> 一个 Python CLI 工具，使用 OCR、计算机视觉和 27 条启发式规则，跨越 6 个设计维度，自动评估卡牌 UI 截图的美学质量——生成 0-100 的分数和 PASS/FAIL 判定。

[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 目录

- [概述](#概述)
- [架构](#架构)
- [快速开始](#快速开始)
- [安装](#安装)
- [使用方法](#使用方法)
  - [CLI 参数参考](#cli-参数参考)
  - [示例](#示例)
  - [评分方案](#评分方案)
  - [批量评分](#批量评分)
  - [规则校验](#规则校验)
- [评分体系](#评分体系)
  - [评分维度](#评分维度)
  - [规则列表](#规则列表)
  - [严重级别](#严重级别)
  - [PASS / FAIL 判定逻辑](#pass--fail-判定逻辑)
- [项目结构](#项目结构)
- [配置说明](#配置说明)
  - [weights.yaml](#weightsyaml)
  - [thresholds.yaml](#thresholdsyaml)
  - [评分方案配置](#评分方案配置)
- [报告](#报告)
- [测试](#测试)
- [CI 集成](#ci-集成)
- [扩展指南](#扩展指南)
- [许可证](#许可证)

## 概述

**card-scorer** 接收一张卡牌 UI 截图和一个用户查询作为输入，运行 OCR 提取、连通域分析和颜色提取流水线，然后评估 **跨越 6 个美学维度的 27 条启发式规则**，最终产出：

- 一个**数值分数**（0-100）
- 一个 **PASS / FAIL 状态**（用于 CI 门禁）
- 一份 **JSON 报告**（机器可读）
- 一份 **HTML 报告**（人工可审阅，内嵌截图）

### 设计理念

- **纯扣分制**——从 100 分开始，每条违规规则扣分。不涉及 ML/LLM；每次扣分都是确定性的、可解释的。
- **高度可配置**——所有阈值、权重和规则启用状态均由外部 YAML/JSON 配置文件驱动。
- **CI 友好**——FAIL 时以退出码 1 退出，适合作为任何 CI 流水线的质量门禁。

### 使用场景

- 卡牌模板变更的 CI/CD 质量门禁
- 已渲染卡牌截图的批量审计
- 设计系统合规性检查
- 发版前的视觉回归筛查

## 架构

```
输入                     提取                      分析                    评分                 输出
------                  ----------                --------                -------              ------

卡牌截图          --->  OCR 提取器          几何分析器                                       JSON 报告
    (PNG/JPG)           (RapidOCR)            - 边缘距离              规则引擎                (report.json)
                        - 文本元素             - 重叠检测              - 27 条规则
用户查询          --->                        - 留白比例              - 6 个维度              HTML 报告
    (文本)              连通域提取器           - 溢出检测              - 扣分系统              (report.html)
                        (OpenCV)              - 视觉中心              - FAIL 检查
可选 DSL          --->  - 连通域元素           - 象限密度                                      控制台输出
    (JSON)                                                             规则注册中心             - 分数 + 状态
                        颜色提取器            一致性分析器              - JSON 元数据           - 主要问题表格
                        (KMeans)              - 对齐聚类              - 评分方案               - 退出码
                        - 主色调               - 间距方差
                        - HSV 信息            - 字号节奏
                                              - 组件节奏              规则手册
                        关键词提取器           - 图标/文字比例         - 启用/禁用
                        (jieba)               - 边距一致性            - 方案覆盖
                        - 关键词               - 网格对齐
                                                                      配置 (YAML)
                        DSL 解析器            层级分析器               - weights.yaml
                        - 解析 JSON            - 视觉重心偏移          - thresholds.yaml
                        - 遍历树               - 密度均衡
                                              - 字号层级

                                              美学分析器
                                              - 颜色冲突
                                              - 对比度 (WCAG)
                                              - 高饱和度
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 对单张卡牌评分
python -m card_scorer.cli.main --image test.png --query "天气"

# 3. 批量评分所有素材
python scripts/batch_score.py

# 4. 校验规则一致性
python scripts/validate_rules.py
```

## 安装

### 环境要求

- **Python** >= 3.11
- **支持平台**：Windows、macOS、Linux

### 从源码安装

```bash
git clone <仓库地址>
cd Aesthetic-test
pip install -r requirements.txt
```

### 验证安装

```bash
python -m card_scorer.cli.main --help
```

预期输出：

```
Usage: card-scorer [OPTIONS] COMMAND [ARGS]...

  Card Aesthetic Scoring System - Automatically filter ugly cards.

Commands:
  score  Score a card screenshot for aesthetic quality.
```

> **注意：** 首次运行时，RapidOCR 会自动将 ONNX 模型文件下载到 `~/.rapidocr/`。无需安装 PaddlePaddle。

## 使用方法

### CLI 参数参考

| 参数 | 简写 | 必填 | 说明 | 默认值 |
|--------|-------|----------|-------------|---------|
| `--image` | `-i` | **是** | 卡牌截图路径（PNG/JPG） | — |
| `--query` | `-q` | 否 | 查询文本或 `.txt` 文件路径 | `""` |
| `--dsl` | `-d` | 否 | DSL JSON 文件路径（启用结构规则） | `""` |
| `--output` | `-o` | 否 | 报告输出目录 | `report` |
| `--profile` | `-p` | 否 | 评分方案名称 | `default` |
| `--verbose` | `-v` | 否 | 启用调试日志 | `false` |

### 示例

```bash
# 基本评分
python -m card_scorer.cli.main --image card.png --query "上海天气"

# 从文件读取查询
python -m card_scorer.cli.main --image card.png --query query.txt

# 附带 DSL 结构分析
python -m card_scorer.cli.main --image card.png --query "天气" --dsl card_layout.json

# 自定义输出目录
python -m card_scorer.cli.main -i card.png -q "天气" -o results/

# 严格方案（全部规则，生产环境用）
python -m card_scorer.cli.main -i card.png -q "天气" -p strict

# 快速方案（仅关键规则，速度快）
python -m card_scorer.cli.main -i card.png -q "天气" -p quick

# 调试模式
python -m card_scorer.cli.main -i card.png -q "天气" -v
```

### 评分方案

| 方案 | 启用的模块 | 适用场景 |
|---------|----------------|----------|
| `default` | 全部 6 个模块，27 条规则 | 日常使用 |
| `strict` | 全部 6 个模块，27 条规则 | 生产环境质量门禁 |
| `quick` | 仅 `information` + `layout`（约 8 条规则） | 快速预检，仅 FATAL/MAJOR 规则 |

### 批量评分

```bash
python scripts/batch_score.py
python scripts/batch_score.py --input batch_test/ --output reports/batch/
```

对于输入目录中的每个 `.png` 文件，脚本会自动查找配套文件（`<名称>_query.txt`、`<名称>_dsl.json`）并运行完整的评分流水线。生成 `summary.csv` 和每张卡牌的 JSON 报告。

**目录结构：**
```
batch_test/           # 待测试的卡片图片（默认输入目录）
reports/batch/        # 批量评分结果（默认输出目录）
├── summary.csv       # 汇总表格
└── <卡片名>/
    └── report.json   # 每张卡片的详细报告
```

### 规则校验

```bash
python scripts/validate_rules.py
```

检查内容：
1. 所有 JSON 中定义的规则是否都有 Python 实现
2. 所有 Python 实现的规则是否都有 JSON 元数据
3. 规则 ID 是否唯一
4. 严重级别和扣分值是否合法
5. JSON 与代码中的模块名称是否一致
6. 评分方案配置引用的模块和规则是否合法

## 评分体系

### 评分维度

系统采用**纯扣分模型**：从 100 分开始，每条违规规则扣分。

| 维度 | 最大扣分 | 优先级 | 说明 |
|-----------|:------------:|:--------:|-------------|
| **information**（信息完整性） | 25 分 | P0 | 内容完整性、意图匹配、截断检测 |
| **layout**（布局与留白） | 20 分 | P0-P1 | 边缘边距、重叠、留白、溢出 |
| **consistency**（视觉一致性） | 20 分 | P1 | 对齐、间距、字号/组件节奏、网格 |
| **color**（色彩和谐度） | 15 分 | P0-P2 | 颜色数量、对比度（WCAG）、饱和度、色相冲突 |
| **hierarchy**（视觉层级） | 10 分 | P1-P2 | 视觉重心、密度均衡、字号层级 |
| **structure**（结构规范） | 10 分 | P2 | 基于 DSL：嵌套、空容器、圆角、装饰 |

### 规则列表

| 规则 ID | 名称 | 维度 | 严重级别 | 最大扣分 | 说明 |
|---------|------|-----------|----------|:------------:|-------------|
| R1.1 | 信息完整性 | information | FATAL | 10.0 | OCR 文本中缺失意图相关的实体信息 |
| R1.2 | 文本截断 | information | FATAL | 8.0 | OCR 置信度过低或文本以省略号结尾 |
| R1.3 | 信息冗余 | information | MINOR | 5.0 | 检测到近重复文本块 |
| R1.4 | 关键实体缺失 | information | MAJOR | 7.0 | 卡牌上未检测到文本或视觉元素 |
| R2.1 | 贴边检测 | layout | MAJOR | 5.0 | 元素距卡牌边缘过近（< 16px） |
| R2.2 | 元素重叠 | layout | FATAL | 8.0 | 边界框重叠 |
| R2.3 | 留白比例 | layout | MINOR | 5.0 | 留白比例超出 20%-70% 范围 |
| R2.4 | 元素溢出 | layout | FATAL | 8.0 | 元素超出卡牌边界 |
| R3.1 | 颜色过多 | color | MINOR | 5.0 | 主色超过 5 种 |
| R3.2 | 对比度不足 | color | MAJOR | 5.0 | 文字-背景对比度低于 WCAG AA 标准（4.5:1） |
| R3.3 | 高饱和度 | color | MINOR | 3.0 | 检测到过高饱和度的颜色 |
| R3.4 | 配色冲突 | color | MAJOR | 5.0 | 互补色冲突（如红-绿） |
| R4.1 | 视觉重心偏移 | hierarchy | MINOR | 4.0 | 视觉重心偏离几何中心过多 |
| R4.2 | 密度均衡 | hierarchy | MINOR | 3.0 | 象限密度比超过 3:1 |
| R4.3 | 尺寸层级 | hierarchy | MINOR | 3.0 | 标题/正文字号比超出 1.2-2.5 |
| VC-1 | 对齐一致性 | consistency | MAJOR | 6.0 | 对齐轴过多或离群率过高 |
| VC-2 | 间距一致性 | consistency | MAJOR | 5.0 | 元素间距变异系数过高 |
| VC-3 | 字号节奏 | consistency | MINOR | 4.0 | 超过 4 种不同字号级别 |
| VC-4 | 组件节奏 | consistency | MINOR | 4.0 | 组件间距不规则 |
| VC-5 | 图标比例 | consistency | MINOR | 3.0 | 图标面积超出卡牌面积的 2%-15% |
| VC-6 | 图文比例 | consistency | MINOR | 3.0 | 文字/图片面积比超出 0.3-0.8 |
| VC-7 | 边距一致性 | consistency | MINOR | 3.0 | 左右边距变化超过阈值 |
| VC-8 | 网格对齐 | consistency | MINOR | 3.0 | 不足 50% 的元素吸附到隐式网格 |
| R5.1 | 嵌套深度 | structure | MINOR | 3.0 | DSL 嵌套深度超过 5 层 |
| R5.2 | 空容器 | structure | MINOR | 3.0 | DSL 树中存在空容器节点 |
| R5.3 | 圆角一致性 | structure | MINOR | 2.0 | 超过 3 种不同的圆角级别 |
| R5.4 | 装饰过多 | structure | MINOR | 2.0 | 超过 3 个装饰性元素 |

> **注意：** 结构规则（R5.1-R5.4）需要通过 `--dsl` 参数输入 DSL JSON。如未提供，这些规则将自动通过。

### 严重级别

| 严重级别 | 含义 | 影响 |
|----------|---------|--------|
| **FATAL** | 致命违规 | 触发 FAIL 状态，总分上限锁定为 60 |
| **MAJOR** | 严重问题 | 参与扣分 |
| **MINOR** | 轻微问题 | 参与扣分 |

### PASS / FAIL 判定逻辑

```
score = max(0, 100 - sum(所有扣分))

if 任何 FATAL 规则触发:
    status = FAIL
    score = min(score, 60)     # 上限锁定为 fail_cap
else:
    status = PASS
```

- **退出码 0** = PASS
- **退出码 1** = FAIL（兼容 CI）

## 项目结构

### 📁 目录总览

```
Aesthetic-test/
├── 📦 核心代码包
│   └── card_scorer/              # 主 Python 包
│
├── ⚙️ 配置文件
│   └── configs/                  # 所有配置文件（YAML/JSON）
│
├── 🧪 测试文件
│   └── tests/                    # 测试套件
│
├── 🔧 工具脚本
│   └── scripts/                  # 批量评分、规则校验等工具
│
├── 📊 测试数据
│   ├── batch_test/               # 批量测试输入目录
│   └── reports/                  # 批量测试输出目录
│
└── 📄 文档文件
    ├── README.md                 # 本文档
    ├── SCORING_FORMULAS.md       # 扣分公式完整文档
    ├── BUG_FIX_R1.1.md          # R1.1 规则修复报告
    └── FIXES_P0_P1.md           # 系统修复总结（P0/P1）
```

---

### 📂 详细文件说明

#### 🏠 根目录文件

| 文件 | 功能 | 说明 |
|------|------|------|
| `pyproject.toml` | 包元数据配置 | 定义项目名称、版本、依赖、入口点、pytest 配置 |
| `requirements.txt` | Python 依赖列表 | 所有第三方库（opencv-python, rapidocr-onnxruntime, scikit-learn 等） |
| `.gitlab-ci.yml` | GitLab CI 流水线 | 自动化测试 + 评分流水线定义 |
| `ci.bat` | Windows CI 脚本 | 本地快速运行测试和评分 |
| `.gitignore` | Git 忽略规则 | 排除缓存、报告、临时文件 |

---

#### 📦 `card_scorer/` - 主代码包

**核心模块：**

| 文件/目录 | 功能 | 关键内容 |
|-----------|------|----------|
| `models.py` | 数据模型定义 | `ScoringContext`, `ScoringReport`, `RuleResult`, `DimensionScore` |
| `__init__.py` | 包初始化 | 版本号导出 |

**子包结构：**

```
card_scorer/
│
├── cli/                          # 命令行接口
│   └── main.py                   # Typer CLI 入口，参数解析，退出码控制
│
├── engine/                       # 评分引擎
│   ├── context.py                # 流水线编排器：OCR → 连通域 → 分析器 → 特征提取
│   ├── scorer.py                 # 评分引擎：规则执行 → 扣分累加 → FAIL 判定
│   └── fail_checker.py           # FAIL 判定逻辑：检查 FATAL 规则触发
│
├── rules/                        # 27 条规则实现（6 个维度）
│   ├── base.py                   # Rule 基类：_pass(), _fail(), evaluate() 抽象方法
│   ├── registry.py               # 规则注册器：@register_rule 装饰器 + RuleBook 加载
│   ├── information.py            # R1.1-R1.4：信息完整性（意图匹配、截断、冗余）
│   ├── layout.py                 # R2.1-R2.4：布局与留白（贴边、重叠、留白、溢出）
│   ├── color.py                  # R3.1-R3.4：色彩和谐（颜色数量、对比度、饱和度、冲突）
│   ├── hierarchy.py              # R4.1-R4.3：视觉层级（重心、密度、字号）
│   ├── consistency.py            # VC-1 至 VC-8：视觉一致性（对齐、间距、节奏、网格）
│   └── structure.py              # R5.1-R5.4：结构规范（DSL 嵌套、空容器、圆角）
│
├── analyzers/                    # 特征计算分析器
│   ├── __init__.py               # 统一导入接口
│   ├── geometry.py               # 几何分析：边距、重叠、留白、溢出、视觉重心、象限密度
│   ├── consistency.py            # 一致性分析：对齐聚类、间距 CV、字号/组件节奏、网格对齐
│   ├── hierarchy.py              # 层级分析：视觉重心偏移、密度均衡、字号层级比
│   ├── aesthetics.py             # 美学分析：颜色冲突、WCAG 对比度、HSV 饱和度
│   └── intent.py                 # 意图分类器：查询 → 意图 → 实体匹配（11 种意图类型）
│
├── extractors/                   # 图像/DSL 提取器
│   ├── ocr_extractor.py          # RapidOCR 文本提取：文本内容 + bbox + 置信度
│   ├── component_extractor.py    # OpenCV 连通域分析：非文本元素 bbox
│   ├── color_extractor.py        # KMeans 主色提取：RGB + HSV + 占比
│   └── dsl_extractor.py          # DSL JSON 解析：树遍历、嵌套深度、空容器检测
│
├── reports/                      # 报告生成器
│   ├── json_report.py            # JSON 报告生成器：机器可读格式
│   └── html_report.py            # HTML 报告生成器：内嵌图片 + 可视化分数
│
└── configs/                      # 配置加载器
    └── loader.py                 # Config 单例：加载 YAML，提供 threshold() 方法
```

---

#### ⚙️ `configs/` - 配置文件

**核心配置：**

| 文件 | 功能 | 关键参数 |
|------|------|----------|
| `weights.yaml` | 维度权重分配 | 6 个维度的最大扣分（总计 100 分）+ `base_score` + `fail_cap` |
| `thresholds.yaml` | 检测阈值大全 | 所有规则的判断阈值（边距 16px、IoU 0.05、CV 0.3 等）|

**评分方案（`profiles/`）：**

| 文件 | 启用模块 | 适用场景 |
|------|----------|----------|
| `default.yaml` | 全部 6 个维度 | 日常使用 |
| `strict.yaml` | 全部 6 个维度 | 生产环境质量门禁 |
| `quick.yaml` | 仅 information + layout | 快速预检（仅 FATAL/MAJOR 规则）|

**规则元数据（`rules/`）：**

每个维度一个 JSON 文件，定义规则的 ID、名称、严重级别、最大扣分等元数据：

```
rules/
├── information_rules.json    # R1.1-R1.4 (4 条)
├── layout_rules.json         # R2.1-R2.4 (4 条)
├── color_rules.json          # R3.1-R3.4 (4 条)
├── hierarchy_rules.json      # R4.1-R4.3 (3 条)
├── consistency_rules.json    # VC-1 至 VC-8 (8 条)
└── structure_rules.json      # R5.1-R5.4 (4 条)
```

---

#### 🔧 `scripts/` - 工具脚本

| 脚本 | 功能 | 输出 |
|------|------|------|
| `batch_score.py` | 批量评分工具 | `summary.csv` + 每张卡片的 JSON/HTML 报告 |
| `validate_rules.py` | 规则一致性校验 | 检查 JSON 元数据与 Python 实现的一致性 |

**使用方法：**
```bash
# 批量评分（默认 batch_test/ → reports/batch/）
python scripts/batch_score.py

# 自定义输入输出目录
python scripts/batch_score.py --input my_cards/ --output my_reports/

# 规则校验
python scripts/validate_rules.py
```

---

#### 🧪 `tests/` - 测试套件

**测试结构：**

| 文件/目录 | 功能 | 测试数量 |
|-----------|------|----------|
| `conftest.py` | Pytest 共享夹具 | `make_ctx()`, `make_text()`, `make_comp()`, `make_color()` |
| `fixtures/` | 测试数据 | 真实卡片图片 + query.txt |
| `test_rules_information.py` | R1.1-R1.4 测试 | ~10 个测试 |
| `test_rules_layout.py` | R2.1-R2.4 测试 | ~12 个测试 |
| `test_rules_color.py` | R3.1-R3.4 测试 | ~10 个测试 |
| `test_rules_hierarchy.py` | R4.1-R4.3 测试 | ~8 个测试 |
| `test_rules_consistency.py` | VC-1 至 VC-8 测试 | ~15 个测试 |
| `test_rules_structure.py` | R5.1-R5.4 测试 | ~8 个测试 |
| `test_engine_scorer.py` | 端到端评分测试 | ~5 个测试 |
| `test_extractors.py` | 提取器测试 | ~8 个测试 |
| `test_analyzers.py` | 分析器测试 | ~12 个测试 |

**总计：** 20+ 测试文件，~100 个测试用例

---

#### 📊 `batch_test/` - 批量测试目录（默认输入）

**文件命名规则：**
```
batch_test/
├── card1.png              # 卡片截图（必需）
├── card1_query.txt        # 查询文本（可选）
├── card1_dsl.json         # DSL 结构（可选）
├── card2.png
├── card2_query.txt
└── ...
```

**说明：**
- 脚本自动匹配 `<名称>.png` + `<名称>_query.txt` + `<名称>_dsl.json`
- 如果缺少 query/dsl 文件，使用空字符串作为输入

---

#### 📈 `reports/` - 报告输出目录（默认输出）

**批量评分输出结构：**
```
reports/batch/
├── summary.csv            # 汇总表格（name, score, status, fatal, major, minor）
├── card1/
│   ├── report.json        # JSON 详细报告
│   └── report.html        # HTML 可视化报告（内嵌图片）
├── card2/
│   ├── report.json
│   └── report.html
└── ...
```

---

#### 📄 文档文件

| 文件 | 内容 | 用途 |
|------|------|------|
| `README.md` | 项目文档（本文件） | 安装指南、使用方法、配置说明 |
| `SCORING_FORMULAS.md` | 扣分公式完整文档 | 每条规则的判断条件、计算公式、阈值参数、扣分逻辑、代码示例 |
| `BUG_FIX_R1.1.md` | R1.1 规则修复报告 | AUDIO_DEVICE 意图新增、GENERAL 判断加强、实体匹配优化 |
| `FIXES_P0_P1.md` | 系统修复总结 | P0/P1 优先级问题修复（小样本保护、DSL 状态标注） |

---

### 🔍 关键数据流

```
1. 输入解析
   card.png + query.txt + card_dsl.json
            ↓
   
2. 特征提取 (extractors/)
   → ocr_extractor: TextElement[]
   → component_extractor: ComponentElement[]
   → color_extractor: ColorInfo[]
   → dsl_extractor: DSL Tree
            ↓
   
3. 特征分析 (analyzers/)
   → geometry: edge_distances, overlaps, whitespace_ratio
   → consistency: alignment, spacing, font_rhythm
   → hierarchy: visual_center, density_balance
   → aesthetics: color_conflicts, min_contrast
            ↓
   
4. 规则评分 (rules/)
   → 27 条规则 × evaluate(ctx)
   → RuleResult[] (passed, score_delta, severity)
            ↓
   
5. 分数计算 (engine/scorer.py)
   → 累加扣分：total = 100 - Σ(deductions)
   → FAIL 判定：if FATAL triggered → cap at 60
            ↓
   
6. 报告生成 (reports/)
   → JSON: report.json (机器可读)
   → HTML: report.html (人工审阅)
```

---

### 📌 快速导航

| 想要... | 查看文件 |
|---------|----------|
| 了解扣分逻辑 | [`SCORING_FORMULAS.md`](SCORING_FORMULAS.md) |
| 修改阈值 | [`configs/thresholds.yaml`](configs/thresholds.yaml) |
| 添加新规则 | [`card_scorer/rules/`](card_scorer/rules/) + [扩展指南](#扩展指南) |
| 调整评分方案 | [`configs/profiles/`](configs/profiles/) |
| 查看测试用例 | [`tests/`](tests/) |
| 批量测试 | [`scripts/batch_score.py`](scripts/batch_score.py) |

## 配置说明

### weights.yaml

定义 100 分的分配和各维度优先级：

```yaml
dimensions:
  information:  { name: "信息完整性", max_deduction: 25, priority: "P0" }
  layout:       { name: "布局与留白", max_deduction: 20, priority: "P0-P1" }
  consistency:  { name: "视觉一致性", max_deduction: 20, priority: "P1" }
  color:        { name: "色彩和谐度", max_deduction: 15, priority: "P0-P2" }
  hierarchy:    { name: "视觉层级",   max_deduction: 10, priority: "P1-P2" }
  structure:    { name: "结构规范",   max_deduction: 10, priority: "P2" }
fail_cap: 60
base_score: 100
```

### thresholds.yaml

包含按类别组织的所有检测阈值：`information`、`layout`、`consistency`、`color`、`hierarchy`、`structure`、`ocr`、`connected_components`。所有阈值均通过 `cfg.threshold(section, key)` 访问——无硬编码。

### 评分方案配置

评分方案控制哪些规则处于激活状态，定义在 `configs/profiles/` 中的 YAML 文件：

```yaml
# 示例：quick.yaml
name: quick
enabled_modules: [information, layout]
disabled_modules: [color, hierarchy, consistency, structure]
disabled_rules: []
enabled_rules: []
```

通过 `--profile <名称>` 使用：

```bash
python -m card_scorer.cli.main -i card.png -q "天气" -p quick
```

## 报告

### JSON 报告（`report.json`）

```json
{
  "total_score": 85.0,
  "status": "PASS",
  "fail_triggered": false,
  "metadata": {
    "image_path": "card.png",
    "query": "天气",
    "image_size": "800x600",
    "text_count": 12,
    "component_count": 5,
    "color_count": 4,
    "profile": "default"
  },
  "dimensions": [
    {
      "dimension": "information",
      "name": "信息完整性",
      "max_deduction": 25,
      "actual_deduction": 5.0,
      "score": 20.0,
      "rules": [...]
    }
  ],
  "deductions": [
    {
      "rule_id": "R2.1",
      "rule_name": "贴边检测",
      "score_delta": -5.0,
      "severity": "major",
      "explanation": "2 个元素距卡片边缘不足 16px",
      "suggestion": "增加元素到边缘的间距至少 16px"
    }
  ]
}
```

### HTML 报告（`report.html`）

自包含的 HTML 文件，包含：
- 内嵌 base64 截图
- 分数圆环（PASS 为绿色，FAIL 为红色）
- 带颜色编码进度条的维度细分
- 问题列表（含严重级别、扣分、解释和修复建议）

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=card_scorer --cov-report=html

# 运行指定测试文件
pytest tests/test_rules_information.py -v
```

**测试结构：**
- **20 个测试文件**，覆盖规则、分析器、提取器、引擎、CLI、报告和模型
- **共享夹具**在 `tests/conftest.py` 中：`make_ctx()`、`make_text()`、`make_comp()`、`make_color()` 工厂函数
- **测试数据**：`tests/fixtures/weather_01.png` + `weather_01_query.txt`

## CI 集成

### GitLab CI

项目自带的 `.gitlab-ci.yml` 定义了两个阶段的流水线：

1. **test**——安装依赖，运行 pytest 并生成覆盖率报告
2. **score**——对 `tests/fixtures/` 中所有 PNG 文件评分，将报告发布为制品

### Windows CI

```bash
# 仅运行测试
ci.bat

# 运行测试 + 对示例卡牌评分
ci.bat --score test.png --query "天气"
```

### 退出码

| 退出码 | 含义 |
|:---------:|---------|
| `0` | PASS——所有 FATAL 规则均通过 |
| `1` | FAIL——至少一条 FATAL 规则触发 |

可在任何 CI 系统中作为质量门禁使用：

```yaml
# 示例：GitHub Actions、Jenkins 等
- run: python -m card_scorer.cli.main --image build/card.png --query "天气" --profile strict
  # PASS 时退出码为 0，FAIL 时为 1
```

## 扩展指南

### 添加新规则

1. 在 `card_scorer/rules/` 下对应维度的模块中创建规则类：

```python
@register_rule
class MyNewRule(Rule):
    rule_id = "R6.1"
    rule_name = "我的新规则"
    dimension = "information"
    severity = Severity.MINOR
    max_deduction = 3.0

    def evaluate(self, ctx: ScoringContext) -> RuleResult:
        if violation_detected:
            return self._fail(
                deduction=3.0,
                evidence={...},
                explanation="...",
                suggestion="..."
            )
        return self._pass()
```

2. 在 `configs/rules/<维度>_rules.json` 中添加 JSON 元数据。
3. 运行 `python scripts/validate_rules.py` 验证一致性。
4. 在 `tests/test_rules_<维度>.py` 中添加测试。

### 添加新分析器

1. 在 `card_scorer/analyzers/` 中创建新分析器，实现 `analyze(ctx, image)` 函数。
2. 将计算结果填充到 `ctx.features` 中。
3. 在 `card_scorer/engine/context.py` 的 `build_context()` 中调用它。

### 添加新评分方案

在 `configs/profiles/` 中创建 YAML 文件：

```yaml
name: my-profile
enabled_modules: [information, layout]
disabled_modules: []
disabled_rules: ["VC-3"]
enabled_rules: []
description: "自定义方案"
```

通过 `--profile my-profile` 使用：

```bash
python -m card_scorer.cli.main -i card.png -q "天气" -p my-profile
```

## 许可证

MIT
