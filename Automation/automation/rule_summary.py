"""纯规则美学评分的批次汇总产物。

读取 output/reports/{qid}/result.json，聚合写出：
- output/reports/model_scores.jsonl：每行一个样本的机器可读分数
- output/reports/model_report.html：单文件画廊汇总报告（缩略图 base64 内嵌，
  点击卡片经相对路径跳转 {qid}/report.html 单样本详情）

画廊样式参考 Aesthetic_Rule_Check 源项目的 calibration/build_rule_only_summary.py。
"""

from __future__ import annotations

import base64
import html
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from .config import AutomationConfig

# 扣分代码 -> 中文标签（与规则包 localization 中的命名保持一致）
DEDUCTION_LABELS = {
    "visual.low_contrast": "文本对比度不足",
    "visual.palette_fragmented": "配色碎片化",
    "visual.focus_unclear": "视觉焦点不清晰",
    "visual.balance_off_center": "视觉重心偏移",
    "visual.text_image_balance": "图文比例失衡",
    "visual.reading_flow_weak": "阅读路径混乱",
    "information.text_missing": "核心文本缺失",
    "information.number_mismatch": "关键数字不匹配",
    "information.unit_weak_match": "单位符号弱匹配",
    "geometry.edge_too_close": "组件贴边",
    "geometry.overlap": "DSL 组件重叠",
    "geometry.density_too_high": "DSL 信息密度过高",
    "geometry.density_too_low": "DSL 信息密度过低",
    "geometry.alignment_weak": "DSL 对齐不足",
    "geometry.grid_weak": "DSL 隐式网格弱",
    "geometry.rhythm_weak": "DSL 间距节奏弱",
    "geometry.hierarchy_weak": "字号层级不足",
    "geometry.typography_too_fragmented": "字号层级碎片化",
    "layout.overlap": "截图元素重叠",
    "layout.overflow": "截图元素溢出",
    "layout.margin_weak": "边距一致性差",
    "layout.rhythm_weak": "截图间距节奏弱",
}

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
TOP_DEDUCTION_LIMIT = 5


def _top_deduction_codes(deductions: list[dict], limit: int = TOP_DEDUCTION_LIMIT) -> list[str]:
    """按严重度与扣分额排序，取前几个扣分 code。"""
    ordered = sorted(
        deductions,
        key=lambda d: (SEVERITY_RANK.get(d.get("severity", ""), 3), d.get("score_delta", 0.0)),
    )
    return [str(d.get("code")) for d in ordered[:limit]]


def _score_row(qid: str, data: dict) -> dict:
    """单样本的机器可读分数行；report/image 使用相对于 reports/ 目录的相对路径。"""
    dimensions = {
        dim["name"]: dim.get("score")
        for dim in data.get("dimensions", [])
        if dim.get("name")
    }
    return {
        "qid": qid,
        "overall": data.get("overall"),
        "raw_overall": data.get("raw_overall"),
        "grade": data.get("grade"),
        "dimensions": dimensions,
        "top_deductions": _top_deduction_codes(data.get("deductions", [])),
        "report": f"{qid}/report.html",
        "image": f"../{qid}.png",
    }


def _embed_image_data_url(path: Path, max_edge: int = 480) -> str:
    """读取图片，缩放到长边 max_edge 后以 PNG base64 data URL 返回（单文件自包含）。

    与规则包保持同一套依赖，使用 opencv 编解码。
    """
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        return ""
    height, width = image.shape[:2]
    if max(width, height) > max_edge:
        scale = max_edge / max(width, height)
        image = cv2.resize(
            image,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")


def build_rule_summary(
    config: AutomationConfig,
    qids: list[str],
) -> tuple[Path, Path] | None:
    """聚合本轮规则评分结果，写出 model_scores.jsonl 与 model_report.html。

    qids 为本轮成功产出单样本报告的样本 id；缺少 result.json 的样本会被跳过。
    没有任何有效结果时返回 None，不写文件。
    """
    report_root = config.rule_report_dir
    entries: list[tuple[str, dict]] = []
    for qid in qids:
        result_path = config.rule_report_dir_for(qid) / "result.json"
        if not result_path.exists():
            continue
        data = json.loads(result_path.read_text(encoding="utf-8"))
        entries.append((qid, data))
    if not entries:
        return None

    report_root.mkdir(parents=True, exist_ok=True)

    # ---- 机器可读分数 jsonl ----
    rows = [_score_row(qid, data) for qid, data in entries]
    scores_text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    config.scores_jsonl_path.write_text(scores_text, encoding="utf-8")

    # ---- 画廊汇总 html ----
    gallery_html = _render_gallery_html(config, entries)
    config.report_html_path.write_text(gallery_html, encoding="utf-8")
    return config.scores_jsonl_path, config.report_html_path


GALLERY_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>纯规则美学评分 · 汇总画廊</title>
<style>
  :root { color-scheme: light; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #f6f7f9; color: #1f2328; }
  main { max-width: 1280px; margin: 0 auto; padding: 24px 28px 40px; }
  h1 { margin: 0; font-size: 22px; }
  .sub { margin: 6px 0 0; color: #57606a; font-size: 13px; }
  .stats { display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0 6px; }
  .stat { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px 18px; min-width: 110px; }
  .stat strong { display: block; font-size: 24px; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .stat span { color: #57606a; font-size: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; margin-top: 18px; }
  .card { display: block; background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit; transition: box-shadow .12s, transform .12s; }
  .card:hover { box-shadow: 0 4px 16px rgba(31,35,40,.12); transform: translateY(-1px); }
  .thumb { position: relative; height: 180px; background: #fff; display: flex; align-items: center; justify-content: center; border-bottom: 1px solid #edf0f2; }
  .thumb img { max-width: 100%; max-height: 180px; object-fit: contain; }
  .cap-flag { position: absolute; top: 8px; right: 8px; background: #b45309; color: #fff; font-size: 10px; padding: 2px 7px; border-radius: 999px; }
  .body { padding: 10px 12px 12px; }
  .sid { font-family: ui-monospace, Consolas, monospace; font-size: 11px; color: #57606a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .score-row { display: flex; align-items: baseline; gap: 8px; margin-top: 4px; }
  .score { font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .grade { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 6px; background: #eef1f4; color: #57606a; }
  .dims { margin-top: 6px; font-size: 11px; color: #57606a; line-height: 1.6; }
  .issues { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; min-height: 20px; }
  .issue { font-size: 10px; padding: 2px 7px; border-radius: 999px; background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; }
  .issue.err { background: #fde8e8; color: #c81e1e; border-color: #f6d5d5; }
  .detail { display: inline-block; margin-top: 8px; font-size: 12px; color: #2563eb; }
  footer { margin-top: 26px; color: #8b949e; font-size: 12px; line-height: 1.7; }
</style>
</head>
<body>
<main>
  <h1>纯规则美学评分 · 汇总画廊</h1>
  <p class="sub">__COUNT__ 张样本 · 本地规则评分（geometry / visual / information / layout / consistency，含封顶机制）· 生成于 __NOW__ · 点击卡片进入单样本详情报告</p>
  <div class="stats">
    <div class="stat"><strong>__COUNT__</strong><span>样本</span></div>
    <div class="stat"><strong>__MEAN__</strong><span>均分</span></div>
    <div class="stat"><strong>__MEDIAN__</strong><span>中位分</span></div>
    <div class="stat"><strong>__MINMAX__</strong><span>最低 / 最高</span></div>
    <div class="stat"><strong>__CAPPED__</strong><span>触发封顶</span></div>
    <div class="stat"><strong>__GRADES__</strong><span>等级分布</span></div>
  </div>
  <div class="grid">
__CARDS__
  </div>
  <footer>
    数据：<code>model_scores.jsonl</code> 与各样本 <code>{qid}/result.json</code> ·
    引擎：内置 <code>Aesthetic_Rule_Check</code> 纯规则评分，不调用外部模型。<br>
    规则未命中 ≠ 视觉验收通过；未命中只表示当前规则没有发现可证明的问题。
  </footer>
</main>
</body>
</html>
"""

CARD_HTML = """    <a class="card" href="__HREF__" title="__QID__">
      <div class="thumb"><img loading="lazy" src="__IMG__" alt="__QID__">__CAPFLAG__</div>
      <div class="body">
        <div class="sid">__QID__</div>
        <div class="score-row"><span class="score">__SCORE__</span><span class="grade">__GRADE__</span></div>
        <div class="dims">__DIMS__</div>
        <div class="issues">__ISSUES__</div>
        <span class="detail">查看详情 →</span>
      </div>
    </a>"""


def _render_gallery_html(config: AutomationConfig, entries: list[tuple[str, dict]]) -> str:
    """渲染单文件画廊：每个样本一张卡片，缩略图内嵌，链接用相对路径。"""
    cards: list[str] = []
    for qid, data in sorted(entries, key=lambda item: item[1].get("overall", 0.0)):
        image_path = config.card_output_dir / f"{qid}.png"
        if not image_path.exists():
            image_path = Path(data.get("image_path", ""))
        img_url = _embed_image_data_url(image_path) if image_path.exists() else ""

        caps = data.get("hard_caps", [])
        cap_flag = f'<span class="cap-flag">封顶×{len(caps)}</span>' if caps else ""

        dims = " · ".join(
            f"{html.escape(dim.get('label') or dim['name'])} {dim.get('score', 0):.0f}"
            for dim in data.get("dimensions", [])
            if dim.get("name")
        )

        deductions = sorted(
            data.get("deductions", []),
            key=lambda d: (SEVERITY_RANK.get(d.get("severity", ""), 3), d.get("score_delta", 0.0)),
        )
        issue_tags = "".join(
            f'<span class="issue{" err" if d.get("severity") == "high" else ""}">'
            f'{html.escape(DEDUCTION_LABELS.get(d.get("code"), str(d.get("code"))))}</span>'
            for d in deductions[:3]
        )
        if len(deductions) > 3:
            issue_tags += f'<span class="issue">+{len(deductions) - 3}</span>'

        card = (
            CARD_HTML.replace("__HREF__", html.escape(f"{qid}/report.html"))
            .replace("__QID__", html.escape(qid))
            .replace("__IMG__", img_url)
            .replace("__CAPFLAG__", cap_flag)
            .replace("__SCORE__", f"{data.get('overall', 0.0):.1f}")
            .replace("__GRADE__", html.escape(str(data.get("grade", "-"))))
            .replace("__DIMS__", dims)
            .replace("__ISSUES__", issue_tags or '<span class="issue">无扣分项</span>')
        )
        cards.append(card)

    overalls = [data.get("overall", 0.0) for _, data in entries]
    grades = Counter(str(data.get("grade", "-")) for _, data in entries)
    grade_text = " / ".join(f"{g}×{n}" for g, n in sorted(grades.items()))
    capped = sum(1 for _, data in entries if data.get("hard_caps"))

    return (
        GALLERY_HTML.replace("__COUNT__", str(len(entries)))
        .replace("__NOW__", datetime.now().strftime("%Y-%m-%d %H:%M"))
        .replace("__MEAN__", f"{statistics.mean(overalls):.2f}")
        .replace("__MEDIAN__", f"{statistics.median(overalls):.2f}")
        .replace("__MINMAX__", f"{min(overalls):.1f} / {max(overalls):.1f}")
        .replace("__CAPPED__", f"{capped}/{len(entries)}")
        .replace("__GRADES__", html.escape(grade_text))
        .replace("__CARDS__", "\n".join(cards))
    )
