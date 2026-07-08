# 批量测试目录

将待测试的卡片图片放入此目录，然后运行批量评分脚本。

## 文件命名规则

```
batch_test/
├── card1.png                 # 卡片图片（必需）
├── card1_query.txt          # 查询文本（可选，如果没有则为空查询）
├── card1_dsl.json           # DSL 结构（可选，如果没有则跳过结构规则）
├── card2.png
├── card2_query.txt
└── ...
```

## 使用方法

### 1. 添加图片

将你的卡片截图复制到这个目录：

```bash
# 方式 1：直接复制
cp 你的图片路径/*.png batch_test/

# 方式 2：手动拖拽图片到此文件夹
```

### 2. （可选）添加查询文本

如果你的卡片需要根据特定查询进行评分（比如"天气"、"新闻"），创建对应的 `_query.txt` 文件：

```bash
echo "上海天气" > batch_test/card1_query.txt
echo "北京新闻" > batch_test/card2_query.txt
```

### 3. 运行批量评分

```bash
# 在项目根目录运行
python scripts/batch_score.py
```

### 4. 查看结果

评分完成后，结果会保存到 `reports/batch/` 目录：

- **summary.csv** - 所有卡片的汇总表格（Excel 可打开）
  - 包含：卡片名称、分数、状态、问题数量、主要问题等
  
- **每张卡片的详细报告** - `reports/batch/<卡片名>/report.json`
  - 包含：所有规则的评分详情、扣分原因、修复建议

## 示例

假设你有以下图片：

```
batch_test/
├── weather_card.png
├── weather_card_query.txt    (内容: "天气预报")
├── news_card.png
└── news_card_query.txt        (内容: "今日新闻")
```

运行：

```bash
python scripts/batch_score.py
```

输出：

```
Found 2 card(s) in batch_test

[1/2] weather_card ... 75.0 (PASS)
[2/2] news_card ... 52.0 (PASS)

Done. 2 PASS, 0 FAIL, 0 ERROR
Summary: reports/batch/summary.csv
Reports: reports/batch
```

## 自定义输入输出目录

```bash
# 从其他目录读取图片
python scripts/batch_score.py --input 你的图片目录 --output 自定义输出目录
```

## 注意事项

- ✅ 仅支持 `.png` 和 `.jpg` 格式
- ✅ 图片名称不能包含 `_query` 或 `_dsl`（这些是保留后缀）
- ✅ 查询文本文件必须使用 UTF-8 编码
- ⚠️ 大批量测试（>100 张）可能需要几分钟时间
