# Card Scorer 扣分规则与计算公式完整文档

> **版本：** v1.0  
> **更新时间：** 2026-06-25  
> **适用系统：** Card Aesthetic Scoring System

---

## 📋 目录

- [系统概述](#系统概述)
- [评分模型](#评分模型)
- [维度 1: 信息完整性 (25分)](#维度-1-信息完整性-25分)
- [维度 2: 布局与留白 (20分)](#维度-2-布局与留白-20分)
- [维度 3: 色彩和谐 (15分)](#维度-3-色彩和谐-15分)
- [维度 4: 视觉层级 (10分)](#维度-4-视觉层级-10分)
- [维度 5: 视觉一致性 (20分)](#维度-5-视觉一致性-20分)
- [维度 6: 结构规范 (10分)](#维度-6-结构规范-10分)
- [附录: 中间值计算](#附录-中间值计算)

---

## 系统概述

### 评分原理

Card Scorer 采用**纯扣分模型**（Pure Deduction Model）：

```
最终分数 = 100 - Σ(所有规则的扣分)
```

- **起始分数：** 100 分
- **扣分规则：** 27 条启发式规则（6 个维度）
- **最低分数：** 0 分（理论上，实际很少低于 30 分）

### 严重级别

| 级别 | 英文 | 扣分范围 | 影响 |
|------|------|----------|------|
| 致命 | FATAL | 8-10 分 | 触发任意一条 → 总分上限锁定为 60 分，测试结论强制 FAIL |
| 严重 | MAJOR | 5-7 分 | 显著影响用户体验，建议修复 |
| 轻微 | MINOR | 2-4 分 | 可选优化项 |

### 阈值配置

所有判断阈值统一存储在 `configs/thresholds.yaml`，支持动态调整：

```yaml
information:
  truncation_confidence_threshold: 0.6
  redundancy_similarity_threshold: 0.85
  
layout:
  edge_margin_min_px: 16
  overlap_iou_threshold: 0.05
  
# ... 更多配置
```

---

## 维度 1: 信息完整性 (25分)

### R1.1 - 信息完整性 (Intent Entity Missing)

**判断条件:**
```
IF 意图分类后，缺少必需实体 (missing_required_entities)
OR OCR 识别到的文本块数量过少 (GENERAL 意图下 < 3 个文本块)
```

**计算公式:**
```python
# 1. 意图分类
result = IntentClassifier.analyze(query, ocr_texts)

# 2. 实体匹配
for pattern in entity_patterns:
    matches = pattern.regex.findall(ocr_text)
    if pattern.is_required and not matches:
        missing_count += 1
```

**阈值参数:**
- `keyword_missing_max_deduction`: 10 分
- `keyword_missing_per_item`: 5 分

**扣分逻辑:**

| 情况 | 条件 | 扣分 |
|------|------|------|
| 完美 | `has_required_entities == True` | 0 分 ✅ |
| 完全缺失 | 无实体且无文本 | 10 分 ❌ |
| 缺 1 个实体 | `missing_count == 1` | 5 分 ⚠️ |
| 缺 ≥2 个实体 | `missing_count >= 2` | 10 分 ❌ |
| GENERAL 内容不足 | `len(ocr_texts) < 3` | 5 分 ⚠️ |

**代码示例:**
```python
# Case 1: 完美情况
if result.has_required_entities:
    return PASS  # 0 分

# Case 2: 完全缺失
if not result.matched_entities and not result.all_text_has_content:
    return FAIL(deduction=10.0)

# Case 3: 部分缺失
if result.missing_required_entities:
    num_missing = len(result.missing_required_entities)
    deduction = 10.0 if num_missing >= 2 else 5.0
    return FAIL(deduction)

# Case 4: GENERAL 意图
if result.intent_name == "GENERAL":
    if len(ocr_texts) >= 3:
        return PASS
    else:
        return FAIL(deduction=5.0)
```

**举例说明:**

**场景 1：天气卡片**
- Query: "今天北京天气怎么样?"
- 意图: WEATHER
- 必需实体: ['temperature', 'weather_condition|location']
- OCR 结果: ['北京', '晴天'] (❌ 缺少温度)
- **扣分: 5 分**

**场景 2：耳机卡片（修复后）**
- Query: "Free Clip 2 耳机，左耳 47%，右耳 95%"
- 意图: AUDIO_DEVICE
- 必需实体: ['device_name', 'battery_level']
- OCR 结果: ['p2', '95%'] (❌ 设备名不足 5 字符)
- **扣分: 5 分**

---

### R1.2 - 文本截断 (Text Truncation)

**判断条件:**
```
IF OCR 元素的置信度 < 0.6
OR 文本以省略号结尾 ("...", "..")
```

**计算公式:**
```python
for elem in text_elements:
    is_truncated = (elem.confidence < 0.6) or 
                   elem.text.rstrip().endswith(("...", ".."))
```

**阈值参数:**
- `truncation_confidence_threshold`: 0.6
- `truncation_deduction`: 8 分

**扣分逻辑:**
- 检测到任何截断 → **扣 8 分** (固定)
- 否则 → 通过 (0 分)

**举例:**
- OCR 结果: "今天天气很好..." → 截断 (省略号)
- OCR 结果: "温度15°C" (置信度 0.45) → 截断 (低置信度)
- **扣分: 8 分**

---

### R1.3 - 信息冗余 (Information Redundancy)

**判断条件:**
```
IF 任意两个文本块的相似度 >= 0.85
```

**计算公式:**
```python
from difflib import SequenceMatcher

for i in range(len(texts)):
    for j in range(i + 1, len(texts)):
        similarity = SequenceMatcher(None, texts[i], texts[j]).ratio()
        # similarity ∈ [0, 1], 1 表示完全相同
```

**阈值参数:**
- `redundancy_similarity_threshold`: 0.85
- `redundancy_deduction`: 5 分

**扣分逻辑:**
- 存在相似度 ≥ 0.85 的文本对 → **扣 5 分**
- 否则 → 通过 (0 分)

**举例:**
- 文本 A: "北京今天晴天"
- 文本 B: "北京今天是晴天"
- 相似度: 0.92 > 0.85
- **扣分: 5 分**

---

### R1.4 - 关键实体缺失 (Entity Missing)

**判断条件:**
```
IF 卡片中没有任何文本元素 AND 没有任何组件元素
OR 卡片中没有任何文本元素（但有组件）
```

**计算公式:**
```python
text_count = len(ctx.text_elements)
component_count = len(ctx.component_elements)
```

**阈值参数:**
- `entity_missing_deduction`: 7 分

**扣分逻辑:**
- 完全空白 (text=0, component=0) → **扣 7 分**
- 仅缺文本 (text=0, component>0) → **扣 7 分**
- 有文本 (text>0) → 通过 (0 分)

**举例:**
- 场景: 卡片渲染失败，只有背景色
- OCR 结果: 无文本
- 组件检测: 无组件
- **扣分: 7 分**

---

## 维度 2: 布局与留白 (20分)

### R2.1 - 贴边检测 (Edge Proximity)

**判断条件:**
```
IF 元素到卡片边缘的最小距离 < 16px
```

**计算公式:**
```python
# 计算元素到四个边缘的距离
left = bbox.x1
top = bbox.y1
right = image_width - bbox.x2
bottom = image_height - bbox.y2

min_distance = min(left, top, right, bottom)
```

**阈值参数:**
- `edge_margin_min_px`: 16 像素
- `edge_deduction`: 5 分

**扣分逻辑:**
- 任何元素 `min_distance < 16px` → **扣 5 分**
- 否则 → 通过 (0 分)

**举例:**
- 元素 bbox: (10, 20, 100, 50)
- 卡片尺寸: 300 × 200
- 边距: left=10, top=20, right=200, bottom=150
- min_distance = 10 < 16
- **扣分: 5 分**

---

### R2.2 - 元素重叠 (Element Overlap)

**判断条件:**
```
IF 两个元素的 IoU (Intersection over Union) > 0.05
```

**计算公式:**
```python
# 计算交集面积
x_overlap = max(0, min(x2_a, x2_b) - max(x1_a, x1_b))
y_overlap = max(0, min(y2_a, y2_b) - max(y1_a, y1_b))
intersection = x_overlap * y_overlap

# 计算并集面积
union = area_a + area_b - intersection

# IoU
iou = intersection / union if union > 0 else 0
```

**阈值参数:**
- `overlap_iou_threshold`: 0.05 (5%)
- `overlap_deduction`: 8 分

**扣分逻辑:**
- 检测到任何 IoU > 0.05 → **扣 8 分** (致命)
- 否则 → 通过 (0 分)

**举例:**
- 元素 A: (50, 50, 100, 100) 面积 2500
- 元素 B: (80, 80, 130, 130) 面积 2500
- 交集: 20×20 = 400
- 并集: 2500 + 2500 - 400 = 4600
- IoU = 400/4600 = 0.087 > 0.05
- **扣分: 8 分**

---

### R2.3 - 留白比例 (Whitespace Ratio)

**判断条件:**
```
IF whitespace_ratio < 0.20 (过于拥挤)
OR whitespace_ratio > 0.70 (过于稀疏)
```

**计算公式:**
```python
# 创建掩码图像
mask = np.zeros((height, width), dtype=np.uint8)

# 标记所有元素占用区域
for elem in elements:
    mask[y1:y2, x1:x2] = 1

# 计算占用面积
occupied_pixels = np.sum(mask)
total_pixels = height * width

# 留白比例
whitespace_ratio = 1.0 - (occupied_pixels / total_pixels)
```

**阈值参数:**
- `whitespace_ratio_min`: 0.20 (20%)
- `whitespace_ratio_max`: 0.70 (70%)
- `whitespace_deduction`: 5 分

**扣分逻辑:**
- `ratio ∈ [0.20, 0.70]` → 通过 (0 分) ✅
- `ratio < 0.20` → **扣 5 分** (过于拥挤)
- `ratio > 0.70` → **扣 5 分** (过于稀疏)

**举例:**
- 卡片尺寸: 300 × 200 = 60000 像素
- 元素占用: 50000 像素
- 留白比例: 1 - 50000/60000 = 0.167 < 0.20
- **扣分: 5 分** (过于拥挤)

---

### R2.4 - 元素溢出 (Element Overflow)

**判断条件:**
```
IF 元素 bbox 超出卡片边界
```

**计算公式:**
```python
overflow = {}
if bbox.x1 < 0:
    overflow["left"] = abs(bbox.x1)
if bbox.y1 < 0:
    overflow["top"] = abs(bbox.y1)
if bbox.x2 > image_width:
    overflow["right"] = bbox.x2 - image_width
if bbox.y2 > image_height:
    overflow["bottom"] = bbox.y2 - image_height
```

**阈值参数:**
- `element_overflow_deduction`: 8 分

**扣分逻辑:**
- 检测到任何溢出 → **扣 8 分**
- 否则 → 通过 (0 分)

**举例:**
- 卡片尺寸: 300 × 200
- 元素 bbox: (280, 150, 320, 180)
- 溢出: right = 320 - 300 = 20px
- **扣分: 8 分**

---

## 维度 3: 色彩和谐 (15分)

### R3.1 - 颜色过多 (Too Many Colors)

**判断条件:**
```
IF 显著主色数量 (proportion > 5%) > 5
```

**计算公式:**
```python
# 使用 KMeans 提取主色
from sklearn.cluster import KMeans
kmeans = KMeans(n_clusters=5, random_state=42)
labels = kmeans.fit_predict(pixels)

# 计算每个颜色的占比
for i in range(5):
    count = np.sum(labels == i)
    proportion = count / len(labels)
    if proportion > 0.05:  # 占比 > 5%
        significant_colors.append(color)
```

**阈值参数:**
- `max_dominant_colors`: 5
- `too_many_colors_deduction`: 5 分

**扣分逻辑:**
- `count <= 5` → 通过 (0 分)
- `count > 5` → **扣 5 分**

**举例:**
- 主色: 红(12%), 蓝(10%), 绿(8%), 黄(7%), 紫(6%), 橙(5.5%)
- 显著主色: 6 种 > 5
- **扣分: 5 分**

---

### R3.2 - 对比度不足 (Contrast Ratio)

**判断条件:**
```
IF 任意两个主色的对比度 < 4.5:1 (WCAG AA 标准)
```

**计算公式:**
```python
# WCAG 2.0 对比度公式
def relative_luminance(r, g, b):
    # 1. 归一化到 [0, 1]
    rgb = [c / 255.0 for c in (r, g, b)]
    
    # 2. 线性化 sRGB
    linear = []
    for s in rgb:
        if s <= 0.03928:
            linear.append(s / 12.92)
        else:
            linear.append(((s + 0.055) / 1.055) ** 2.4)
    
    # 3. 计算相对亮度
    L = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    return L

# 4. 计算对比度
L1 = relative_luminance(r1, g1, b1)
L2 = relative_luminance(r2, g2, b2)
lighter = max(L1, L2)
darker = min(L1, L2)
contrast_ratio = (lighter + 0.05) / (darker + 0.05)
```

**阈值参数:**
- `contrast_ratio_min`: 4.5 (WCAG AA 标准)
- `contrast_deduction`: 5 分

**扣分逻辑:**
- `min_contrast >= 4.5` → 通过 (0 分)
- `min_contrast < 4.5` → **扣 5 分**

**举例:**
- 颜色 A: RGB(200, 200, 200) 浅灰
- 颜色 B: RGB(220, 220, 220) 极浅灰
- L1 = 0.715, L2 = 0.789
- 对比度 = (0.789 + 0.05) / (0.715 + 0.05) = 1.1:1 < 4.5
- **扣分: 5 分**

---

### R3.3 - 高饱和度 (High Saturation)

**判断条件:**
```
IF 任意主色的 HSV 饱和度 > 0.9
```

**计算公式:**
```python
import colorsys

# RGB → HSV
h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
# s ∈ [0, 1]
```

**阈值参数:**
- `saturation_max`: 0.9
- `high_saturation_deduction`: 3 分

**扣分逻辑:**
- 存在 s > 0.9 的颜色 → **扣 3 分**
- 否则 → 通过 (0 分)

**举例:**
- 颜色: RGB(255, 0, 0) 纯红
- HSV: (0°, 1.0, 1.0)
- 饱和度: 1.0 > 0.9
- **扣分: 3 分**

---

### R3.4 - 配色冲突 (Color Conflict)

**判断条件:**
```
IF 两个主色的色相距离接近 180° (互补色)
AND 两个颜色的饱和度都 > 0.3
AND |hue_distance - 180| < 30°
```

**计算公式:**
```python
# 1. 获取色相 (Hue)
h1 = color_a.hsv[0] * 360  # [0, 360°]
h2 = color_b.hsv[0] * 360

# 2. 计算色相距离（取短弧）
hue_dist = abs(h1 - h2)
if hue_dist > 180:
    hue_dist = 360 - hue_dist

# 3. 判断是否为互补色冲突
is_conflict = (
    abs(hue_dist - 180) < 30 and  # 接近 180°
    color_a.hsv[1] > 0.3 and      # 饱和度足够高
    color_b.hsv[1] > 0.3
)
```

**阈值参数:**
- `hue_conflict_threshold`: 30° (度数)
- `color_conflict_deduction`: 5 分

**扣分逻辑:**
- 检测到互补色冲突 → **扣 5 分**
- 否则 → 通过 (0 分)

**举例:**
- 颜色 A: RGB(255, 0, 0) → 色相 0° (红), 饱和度 1.0
- 颜色 B: RGB(0, 255, 100) → 色相 165° (青绿), 饱和度 0.8
- 色相距离: 165° (短弧)
- |165 - 180| = 15° < 30° → 互补色冲突
- **扣分: 5 分**

---

## 维度 4: 视觉层级 (10分)

### R4.1 - 视觉重心偏移 (Visual Center Offset)

**判断条件:**
```
IF 视觉重心与几何重心的欧氏距离 > 0.15
```

**计算公式:**
```python
import cv2

# 1. 计算图像矩
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
inverted = 255 - gray  # 反转使前景有权重
moments = cv2.moments(inverted)

# 2. 计算视觉重心（归一化到 [0, 1]）
cx = moments["m10"] / moments["m00"] / width
cy = moments["m01"] / moments["m00"] / height

# 3. 计算偏移量
offset_x = cx - 0.5  # 几何重心在 (0.5, 0.5)
offset_y = cy - 0.5
offset_norm = sqrt(offset_x**2 + offset_y**2)
```

**阈值参数:**
- `visual_center_offset_max`: 0.15 (归一化单位)
- `visual_center_deduction`: 4 分

**扣分逻辑:**
- `offset_norm <= 0.15` → 通过 (0 分)
- `offset_norm > 0.15` → **扣 4 分**

**举例:**
- 视觉重心: (0.7, 0.6)
- 几何重心: (0.5, 0.5)
- offset_norm = sqrt(0.2² + 0.1²) = 0.224 > 0.15
- **扣分: 4 分**

---

### R4.2 - 密度均衡 (Density Balance)

**判断条件:**
```
IF 四象限密度的最大值/最小值 > 3.0
```

**计算公式:**
```python
# 1. 划分四象限
mid_x = image_width / 2
mid_y = image_height / 2

density = {
    "top_left": 0,
    "top_right": 0,
    "bottom_left": 0,
    "bottom_right": 0
}

# 2. 累加每个元素的面积到对应象限
for elem in elements:
    cx, cy = elem.bbox.center
    area = elem.bbox.area
    
    if cx <= mid_x and cy <= mid_y:
        density["top_left"] += area
    elif cx > mid_x and cy <= mid_y:
        density["top_right"] += area
    elif cx <= mid_x and cy > mid_y:
        density["bottom_left"] += area
    else:
        density["bottom_right"] += area

# 3. 计算密度比
max_density = max(density.values())
min_density = min(density.values())
ratio = max_density / min_density if min_density > 0 else float('inf')
```

**阈值参数:**
- `quadrant_density_ratio_max`: 3.0
- `density_balance_deduction`: 3 分

**扣分逻辑:**
- `ratio <= 3.0` → 通过 (0 分)
- `ratio > 3.0` → **扣 3 分**

**举例:**
- 象限密度: {左上: 6000, 右上: 500, 左下: 1000, 右下: 1500}
- max_density = 6000, min_density = 500
- ratio = 12.0 > 3.0
- **扣分: 3 分**

---

### R4.3 - 尺寸层级 (Size Hierarchy)

**判断条件:**
```
IF 标题/正文字号比 < 1.2 (层级不明显)
OR 标题/正文字号比 > 2.5 (差距过大)
```

**计算公式:**
```python
# 1. 收集所有文本元素的字号
sizes = [elem.font_size_est or elem.bbox.height 
         for elem in text_elements]

# 2. 估算标题和正文字号
max_size = max(sizes)        # 最大字号 → 标题
median_size = median(sizes)  # 中位数 → 正文

# 3. 计算比例
ratio = max_size / median_size
```

**阈值参数:**
- `heading_body_ratio_min`: 1.2
- `heading_body_ratio_max`: 2.5
- `size_hierarchy_deduction`: 3 分

**扣分逻辑:**
- `文本元素 < 2` → 通过 (0 分, 元素太少)
- `ratio ∈ [1.2, 2.5]` → 通过 (0 分)
- `ratio < 1.2` → **扣 3 分** (层级不明显)
- `ratio > 2.5` → **扣 3 分** (差距过大)

**举例:**
- 文本字号: [16, 16, 15, 14, 14]
- max_size = 16, median_size = 15
- ratio = 16/15 = 1.07 < 1.2
- **扣分: 3 分** (层级不明显)

---

## 维度 5: 视觉一致性 (20分)

### VC-1 - 对齐一致性 (Alignment Consistency)

**判断条件:**
```
IF 离群率 (outlier_ratio) > 0.4
OR 左对齐轴线数量 (num_left_clusters) > 5
```

**计算公式:**
```python
# 1. 收集所有元素的左边缘坐标
left_edges = [elem.bbox.x1 for elem in elements]

# 2. 1D 聚类（eps=5px）
def cluster_1d(values, eps=5.0):
    sorted_vals = sorted(values)
    clusters = [[sorted_vals[0]]]
    
    for v in sorted_vals[1:]:
        if v - clusters[-1][-1] <= eps:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    
    return clusters

left_clusters = cluster_1d(left_edges, eps=5.0)
num_left_clusters = len(left_clusters)

# 3. 计算离群率
largest_cluster_size = max(len(c) for c in left_clusters)
outlier_ratio = 1.0 - largest_cluster_size / len(left_edges)
```

**阈值参数:**
- `alignment_cluster_eps`: 5 像素
- `alignment_deduction`: 6 分

**扣分逻辑:**
- `outlier_ratio <= 0.4 AND num_clusters <= 5` → 通过 (0 分)
- `outlier_ratio > 0.4 OR num_clusters > 5` → **扣 6 分**

**举例:**
- 左边缘: [10, 12, 50, 52, 90, 150, 152]
- 聚类: [[10, 12], [50, 52], [90], [150, 152]]
- num_clusters = 4
- largest_cluster = 2
- outlier_ratio = 1 - 2/7 = 0.71 > 0.4
- **扣分: 6 分**

---

### VC-2 - 间距一致性 (Spacing Consistency)

**判断条件:**
```
IF 元素间垂直间距的变异系数 (CV) > 0.3
```

**计算公式:**
```python
# 1. 按 Y 坐标排序元素
sorted_elems = sorted(elements, key=lambda e: e.bbox.y1)

# 2. 计算相邻元素间距
gaps = []
for i in range(1, len(sorted_elems)):
    gap = sorted_elems[i].bbox.y1 - sorted_elems[i-1].bbox.y2
    gaps.append(gap)

# 3. 计算变异系数 (Coefficient of Variation)
mean_gap = mean(gaps)
std_gap = std(gaps)
cv = std_gap / mean_gap if mean_gap > 0 else 0
```

**阈值参数:**
- `spacing_variance_threshold`: 0.3
- `spacing_deduction`: 5 分

**扣分逻辑:**
- `cv <= 0.3` → 通过 (0 分)
- `cv > 0.3` → **扣 5 分**

**举例:**
- 垂直间距: [10, 12, 25, 8, 30]
- mean_gap = 17, std_gap = 9.6
- cv = 9.6 / 17 = 0.565 > 0.3
- **扣分: 5 分**

---

### VC-3 - 字号节奏 (Font Rhythm)

**判断条件:**
```
IF 字号层级数量 > 4
```

**计算公式:**
```python
# 1. 收集所有字号
sizes = [elem.font_size_est or elem.bbox.height 
         for elem in text_elements]

# 2. 量化到 2px（避免噪声）
bucketed = [round(s / 2) * 2 for s in sizes]

# 3. 去重统计层级数
size_levels = len(set(bucketed))
```

**阈值参数:**
- `font_size_levels_max`: 4
- `font_rhythm_deduction`: 4 分

**扣分逻辑:**
- `size_levels <= 4` → 通过 (0 分)
- `size_levels > 4` → **扣 4 分**

**举例:**
- 字号: [12, 14, 16, 18, 20, 24]
- 量化后: [12, 14, 16, 18, 20, 24]
- 层级数: 6 > 4
- **扣分: 4 分**

---

### VC-4 - 组件节奏 (Component Rhythm)

**判断条件:**
```
IF 组件间垂直间距的变异系数 (CV) > 0.3
AND 组件数量 >= 3
```

**计算公式:**
```python
# 计算方式与 VC-2 相同，但仅针对 component_elements
sorted_comps = sorted(components, key=lambda c: c.bbox.y1)
gaps = [sorted_comps[i].bbox.y1 - sorted_comps[i-1].bbox.y2 
        for i in range(1, len(sorted_comps))]
cv = std(gaps) / mean(gaps)
```

**阈值参数:**
- `spacing_variance_threshold`: 0.3
- `component_rhythm_deduction`: 4 分

**扣分逻辑:**
- `cv <= 0.3 OR components < 3` → 通过 (0 分)
- `cv > 0.3 AND components >= 3` → **扣 4 分**

**举例:**
- 组件间距: [15, 30, 12, 40]
- mean = 24.25, std = 12.3
- cv = 12.3 / 24.25 = 0.507 > 0.3
- **扣分: 4 分**

---

### VC-5 - 图标比例 (Icon Proportion)

**判断条件:**
```
IF 图标总面积 / 卡片面积 < 0.02 (过小)
OR 图标总面积 / 卡片面积 > 0.15 (过大)
```

**计算公式:**
```python
total_icon_area = sum(c.area for c in components)
image_area = image_width * image_height
ratio = total_icon_area / image_area
```

**阈值参数:**
- `icon_ratio_min`: 0.02 (2%)
- `icon_ratio_max`: 0.15 (15%)
- `icon_proportion_deduction`: 3 分

**扣分逻辑:**
- 无组件 → 通过 (0 分)
- `ratio ∈ [0.02, 0.15]` → 通过 (0 分)
- `ratio < 0.02` → **扣 3 分** (过小)
- `ratio > 0.15` → **扣 3 分** (过大)

**举例:**
- 卡片面积: 300 × 200 = 60000
- 图标总面积: 800
- ratio = 800 / 60000 = 0.0133 < 0.02
- **扣分: 3 分** (图标过小)

---

### VC-6 - 图文比例 (Text-Image Ratio)

**判断条件:**
```
IF 文本面积 / 总面积 < 0.3 (文本过少)
OR 文本面积 / 总面积 > 0.8 (文本过多)
```

**计算公式:**
```python
text_area = sum(e.bbox.area for e in text_elements)
comp_area = sum(c.area for c in components)
total = text_area + comp_area
ratio = text_area / total if total > 0 else 0
```

**阈值参数:**
- `text_image_ratio_min`: 0.3
- `text_image_ratio_max`: 0.8
- `text_image_ratio_deduction`: 3 分

**扣分逻辑:**
- 无组件（纯文本） → 通过 (0 分)
- `ratio ∈ [0.3, 0.8]` → 通过 (0 分)
- `ratio < 0.3 OR ratio > 0.8` → **扣 3 分**

**举例:**
- 文本面积: 2000
- 组件面积: 8000
- 总面积: 10000
- ratio = 2000 / 10000 = 0.2 < 0.3
- **扣分: 3 分** (文本占比过低)

---

### VC-7 - 边距一致性 (Margin Consistency)

**判断条件:**
```
IF 左边距变异系数 (left_cv) > 0.25
OR 右边距变异系数 (right_cv) > 0.25
```

**计算公式:**
```python
left_margins = [elem.bbox.x1 for elem in elements]
right_margins = [image_width - elem.bbox.x2 for elem in elements]

left_cv = std(left_margins) / mean(left_margins)
right_cv = std(right_margins) / mean(right_margins)
```

**阈值参数:**
- `margin_consistency_threshold`: 0.25
- `margin_consistency_deduction`: 3 分

**扣分逻辑:**
- `left_cv <= 0.25 AND right_cv <= 0.25` → 通过 (0 分)
- `left_cv > 0.25 OR right_cv > 0.25` → **扣 3 分**

**举例:**
- 左边距: [10, 15, 30, 12]
- mean = 16.75, std = 8.8
- left_cv = 8.8 / 16.75 = 0.525 > 0.25
- **扣分: 3 分**

---

### VC-8 - 网格对齐 (Grid Alignment)

**判断条件:**
```
IF X 方向对齐率 (x_snap_ratio) < 0.5
OR Y 方向对齐率 (y_snap_ratio) < 0.5
```

**计算公式:**
```python
def snap_ratio(values, eps=5.0):
    """计算有多少元素与其他元素对齐（距离 <= eps）"""
    snapped = 0
    sorted_v = sorted(values)
    
    for i, v in enumerate(sorted_v):
        for j in range(i + 1, len(sorted_v)):
            if sorted_v[j] - v > eps:
                break
            if abs(sorted_v[j] - v) <= eps:
                snapped += 1
                break
    
    return snapped / len(values)

left_edges = [elem.bbox.x1 for elem in elements]
top_edges = [elem.bbox.y1 for elem in elements]

x_snap_ratio = snap_ratio(left_edges, eps=5.0)
y_snap_ratio = snap_ratio(top_edges, eps=5.0)
```

**阈值参数:**
- `alignment_cluster_eps`: 5 像素 (隐含)
- `grid_alignment_deduction`: 3 分

**扣分逻辑:**
- `x_snap >= 0.5 AND y_snap >= 0.5` → 通过 (0 分)
- `x_snap < 0.5 OR y_snap < 0.5` → **扣 3 分**

**举例:**
- X 坐标: [10, 50, 90, 130]
- 对齐检测: 没有元素彼此对齐 (距离都 > 5px)
- x_snap_ratio = 0 / 4 = 0.0 < 0.5
- **扣分: 3 分**

---

## 维度 6: 结构规范 (10分)

### R5.1 - 嵌套深度 (Nesting Depth)

**判断条件:**
```
IF DSL 树的最大嵌套深度 > 5
```

**计算公式:**
```python
def get_max_nesting_depth(node, depth=0):
    if not isinstance(node, dict):
        return depth
    
    children = node.get("children", [])
    if not children:
        return depth
    
    return max(
        get_max_nesting_depth(child, depth + 1) 
        for child in children
    )

actual_depth = get_max_nesting_depth(dsl_tree)
```

**阈值参数:**
- `max_nesting_depth`: 5
- `nesting_deduction`: 3 分

**扣分逻辑:**
- 无 DSL 输入 → 跳过 (0 分)
- `depth <= 5` → 通过 (0 分)
- `depth > 5` → **扣 3 分**

**举例:**
- DSL: Card > Container > VStack > HStack > Text > Bold
- 嵌套深度: 6 > 5
- **扣分: 3 分**

---

### R5.2 - 空容器 (Empty Container)

**判断条件:**
```
IF DSL 树中存在 children 为空数组的容器节点
```

**计算公式:**
```python
def find_empty_containers(node):
    empty = []
    
    def visitor(n, depth):
        if isinstance(n, dict):
            node_type = n.get("type", "")
            # 检查是否为容器类型
            if any(kw in node_type.lower() 
                   for kw in ("container", "stack", "box")):
                if n.get("children") == []:
                    empty.append(node_type)
    
    walk_dsl(node, visitor)
    return empty
```

**阈值参数:**
- `empty_container_deduction`: 3 分

**扣分逻辑:**
- 无 DSL 输入 → 跳过 (0 分)
- 无空容器 → 通过 (0 分)
- 检测到空容器 → **扣 3 分**

**举例:**
- DSL 节点: `{"type": "VStack", "children": []}`
- 检测到: 1 个空容器
- **扣分: 3 分**

---

### R5.3 - 圆角一致性 (Border Radius Consistency)

**判断条件:**
```
IF DSL 树中不同的 borderRadius 值数量 > 3
```

**计算公式:**
```python
radii = set()

def visitor(node, depth):
    if isinstance(node, dict):
        for key in ("borderRadius", "border_radius", "radius"):
            if key in node:
                radii.add(float(node[key]))

walk_dsl(dsl_tree, visitor)
radius_levels = len(radii)
```

**阈值参数:**
- `border_radius_levels_max`: 3
- `border_radius_deduction`: 2 分

**扣分逻辑:**
- 无 DSL 输入 → 跳过 (0 分)
- `levels <= 3` → 通过 (0 分)
- `levels > 3` → **扣 2 分**

**举例:**
- DSL 圆角值: [4, 8, 12, 16, 20]
- 层级数: 5 > 3
- **扣分: 2 分**

---

### R5.4 - 装饰过多 (Excessive Decoration)

**判断条件:**
```
IF DSL 树中装饰元素数量 > 3
```

**计算公式:**
```python
deco_count = 0

def visitor(node, depth):
    if isinstance(node, dict):
        node_type = str(node.get("type", "")).lower()
        if any(kw in node_type for kw in 
               ("decoration", "divider", "separator", "ornament")):
            deco_count += 1

walk_dsl(dsl_tree, visitor)
```

**阈值参数:**
- `decoration_count_max`: 3
- `decoration_deduction`: 2 分

**扣分逻辑:**
- 无 DSL 输入 → 跳过 (0 分)
- `count <= 3` → 通过 (0 分)
- `count > 3` → **扣 2 分**

**举例:**
- DSL 装饰: 5 个 Divider 节点
- deco_count = 5 > 3
- **扣分: 2 分**

---

## 附录: 中间值计算

### Geometry Analyzer (几何分析器)

提供基础几何计算：

| 输出 | 计算方法 | 使用规则 |
|------|----------|----------|
| `edge_distances` | 元素到四边距离 | R2.1 |
| `overlaps` | IoU 重叠检测 | R2.2 |
| `whitespace_ratio` | 留白比例 | R2.3 |
| `overflows` | 边界溢出检测 | R2.4 |
| `visual_center` | OpenCV 图像矩 | R4.1 |
| `quadrant_density` | 四象限面积统计 | R4.2 |

### Consistency Analyzer (一致性分析器)

提供一致性计算：

| 输出 | 计算方法 | 使用规则 |
|------|----------|----------|
| `alignment` | 1D 聚类分析 | VC-1 |
| `spacing` | 变异系数 (CV) | VC-2 |
| `font_rhythm` | 字号去重统计 | VC-3 |
| `component_rhythm` | 组件间距 CV | VC-4 |
| `icon_proportion` | 面积占比 | VC-5 |
| `text_image_ratio` | 文本/组件比 | VC-6 |
| `margin_consistency` | 边距 CV | VC-7 |
| `grid_alignment` | 对齐率统计 | VC-8 |

### Hierarchy Analyzer (层级分析器)

提供层级计算：

| 输出 | 计算方法 | 使用规则 |
|------|----------|----------|
| `visual_center_offset` | 欧氏距离 | R4.1 |
| `density_balance` | 象限密度比 | R4.2 |
| `size_hierarchy` | 字号比例 | R4.3 |

### Aesthetics Analyzer (美学分析器)

提供色彩计算：

| 输出 | 计算方法 | 使用规则 |
|------|----------|----------|
| `color_count` | KMeans 聚类 | R3.1 |
| `min_contrast` | WCAG 对比度 | R3.2 |
| `high_saturation` | HSV 饱和度 | R3.3 |
| `color_conflicts` | 色相距离 | R3.4 |

---

## 总结

### 规则统计

| 维度 | 规则数 | 总分 | 平均扣分 | 固定扣分规则 | 渐进扣分规则 |
|------|--------|------|----------|--------------|--------------|
| Information | 4 | 25 | 6.25 | 3 | 1 (R1.1) |
| Layout | 4 | 20 | 5.0 | 4 | 0 |
| Color | 4 | 15 | 3.75 | 4 | 0 |
| Hierarchy | 3 | 10 | 3.33 | 3 | 0 |
| Consistency | 8 | 20 | 2.5 | 8 | 0 |
| Structure | 4 | 10 | 2.5 | 4 | 0 |
| **总计** | **27** | **100** | **3.70** | **26** | **1** |

### 关键特性

1. **固定扣分主导：** 96% 的规则采用固定扣分（IF 违规 THEN 扣 X 分）
2. **唯一渐进式：** 仅 R1.1 采用分级扣分（缺 1 个扣 5 分，缺 ≥2 个扣 10 分）
3. **阈值可配置：** 所有阈值存储在 `thresholds.yaml`，支持动态调整
4. **分析器分层：** geometry → consistency/hierarchy/aesthetics 形成依赖链
5. **DSL 可选：** Structure 维度的 4 条规则仅在提供 DSL 时生效

---

**文档版本：** v1.0  
**最后更新：** 2026-06-25  
**维护者：** Card Scorer Team  
**反馈渠道：** [GitHub Issues](https://github.com/your-repo/card-scorer/issues)
