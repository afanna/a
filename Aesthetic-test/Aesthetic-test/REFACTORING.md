# 重构总结：规则元数据与代码解耦

## 完成的改动

### 1. 规则元数据 JSON 化（configs/rules/）

创建了 6 个规则元数据文件，包含全部 27 条规则：
- `information_rules.json` (4 条规则)
- `layout_rules.json` (4 条规则)
- `color_rules.json` (4 条规则)
- `hierarchy_rules.json` (3 条规则)
- `consistency_rules.json` (8 条规则)
- `structure_rules.json` (4 条规则)

每条规则包含：
```json
{
  "id": "R1.1",
  "name": "信息完整性",
  "module": "information",
  "dimension": "信息完整性",
  "severity": "FATAL",
  "max_deduction": 10.0,
  "enabled": true,
  "description": "检查意图特定实体是否出现在 OCR 文本中"
}
```

### 2. 规则注册机制（card_scorer/rules/registry.py）

**核心组件：**
- `@register_rule` 装饰器：自动收集规则类
- `RuleBook` 类：管理规则元数据和启用状态
- `build_rulebook()` 函数：从 profile 构建 RuleBook
- `get_registered_rules()` 函数：获取所有已注册规则

**使用方法：**
```python
from card_scorer.rules.registry import register_rule

@register_rule
class MyNewRule(Rule):
    rule_id = "R5.1"
    ...
```

所有现有规则类已添加 `@register_rule` 装饰器。

### 3. Profile 支持（configs/profiles/）

创建了 3 个预定义 profile：
- `default.yaml` - 启用所有规则
- `strict.yaml` - 严格模式（生产环境）
- `quick.yaml` - 仅检查 FATAL 和 MAJOR 问题

**Profile 结构：**
```yaml
name: default
enabled_modules:
  - information
  - layout
  - color
  - hierarchy
  - consistency
  - structure
disabled_modules: []
disabled_rules: []
enabled_rules: []
```

### 4. 统一的测试工厂（tests/conftest.py）

提供 pytest fixtures 消除重复代码：
- `make_ctx()` - 创建 ScoringContext
- `make_text()` - 创建 TextElement
- `make_comp()` - 创建 ComponentElement
- `make_color()` - 创建 ColorInfo
- `assert_rule_passed()` - 断言规则通过
- `assert_rule_failed()` - 断言规则失败

**测试示例：**
```python
def test_my_rule(make_ctx, make_text):
    ctx = make_ctx(
        query="测试",
        text_elements=[make_text(0, 0, 100, 20, "Hello")]
    )
    result = MyRule().evaluate(ctx)
    assert_rule_passed(result)
```

### 5. Scorer 重构（card_scorer/engine/scorer.py）

- 使用 `build_rulebook()` 动态加载规则
- 只实例化启用的规则
- 支持 `profile` 参数

**使用方法：**
```python
from card_scorer.engine.scorer import score

report = score(ctx, profile="strict")
```

### 6. CLI 更新

添加 `--profile` 参数：
```bash
python -m card_scorer.cli.main --image test.png --query "天气" --profile strict
```

### 7. 规则自校验脚本（scripts/validate_rules.py）

验证以下内容：
1. JSON 定义的规则是否有代码实现
2. 代码实现的规则是否有 JSON 元数据
3. Rule ID 唯一性
4. Severity 和 deduction 值合法性
5. 模块名称一致性
6. Profile 配置有效性

## 添加新规则的步骤（现在只需 3 步）

### 旧流程（繁琐）：
1. 创建规则类
2. 在 `get_rules()` 手动注册
3. 写测试类
4. 复制 `_ctx()` / `_text()` 等辅助函数
5. 更新 `scorer.py` 导入

### 新流程（简化）：
1. **在 JSON 中添加元数据**
   ```json
   {"id": "R5.1", "name": "新规则", "module": "layout", ...}
   ```

2. **写规则类（自动注册）**
   ```python
   @register_rule
   class MyNewRule(Rule):
       rule_id = "R5.1"
       ...
   ```

3. **写测试（使用 fixtures）**
   ```python
   def test_my_rule(make_ctx):
       ...
   ```

## 验证步骤

在 VS Code 终端执行：

```powershell
# 1. 设置环境变量
$env:PYTHONPATH = "C:\Users\afan\Desktop\Aesthetic-test"

# 2. 运行规则自校验
python scripts/validate_rules.py

# 3. 运行测试验证重构正确性
pytest tests/ -v

# 4. 测试新的 profile 功能
python -m card_scorer.cli.main --image test.png --query "深圳天气怎么样" --profile default --output reports/

# 5. 测试 quick profile（只检查关键问题）
python -m card_scorer.cli.main --image test.png --query "深圳天气怎么样" --profile quick --output reports/quick/
```

## 优势总结

| 方面 | 改进前 | 改进后 |
|-----|--------|--------|
| **添加规则** | 5 个步骤，需修改多个文件 | 2-3 个步骤，自动注册 |
| **规则元数据** | 硬编码在类属性中 | 集中在 JSON，易于管理 |
| **测试代码** | 每个文件重复定义工厂函数 | 统一 fixtures，零重复 |
| **规则启用控制** | 修改代码 | 通过 profile 动态控制 |
| **一致性检查** | 手工检查 | 自动化脚本验证 |
| **耦合度** | 高（6 个维度紧耦合） | 低（独立模块+自动注册） |

## 下一步建议

1. 将其他测试文件更新为使用新的 fixtures（参考 `test_rules_color_new.py`）
2. 根据需要创建更多 profile（如 `production.yaml`, `debug.yaml`）
3. 在 CI 中添加 `python scripts/validate_rules.py` 检查
4. 考虑将 threshold 配置也 JSON 化

## 文件清单

**新增文件：**
- `configs/rules/*.json` (6 个)
- `configs/profiles/*.yaml` (3 个)
- `card_scorer/rules/registry.py`
- `tests/conftest.py`
- `scripts/validate_rules.py`
- `tests/test_rules_color_new.py` (示例)

**修改文件：**
- `card_scorer/rules/*.py` (6 个规则模块)
- `card_scorer/rules/__init__.py`
- `card_scorer/engine/scorer.py`
- `card_scorer/cli/main.py`

**备份文件：**
- `card_scorer/engine/scorer.py.bak`
