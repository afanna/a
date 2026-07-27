"""纯规则美学评分的批次汇总产物。

读取 output/reports/{qid}/result.json，聚合写出：
- output/reports/model_scores.jsonl：每行一个样本的机器可读分数
- output/reports/model_report.html：单文件画廊汇总报告（缩略图 base64 内嵌，
  JS 数据驱动，支持搜索/等级/问题类型筛选与排序，点击卡片经相对路径跳转
  {qid}/report.html 单样本详情）

画廊样式对齐 Aesthetic_Rule_Check 源项目的 calibration/build_rule_only_summary.py：
status 四态（pass / pass_with_warnings / needs_review / fail）、分数分布直方图、
等级彩色徽章、场景切片、置顶筛选栏。
"""

from __future__ import annotations

import base64
import html
import json
import re
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
# validator 语义：置信度低于该值的样本计入 needs_review 信号
LOW_CONFIDENCE_THRESHOLD = 0.8
GRADE_ORDER = ["S", "A", "B+", "B", "C", "D"]
# 分数分布直方图分桶（下界含、上界不含，最后一桶为 <60）
HISTO_BINS = [(90, 101, "90+"), (80, 90, "80"), (75, 80, "75"), (70, 75, "70"), (60, 70, "60"), (0, 60, "<60")]


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
        "calibrated_overall": data.get("calibrated_overall"),
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


def _scene_of(qid: str) -> str:
    """从 qid 提取场景标签，如 taskspec_gpt55__Case-29-elderly-care-008 -> elderly-care。"""
    match = re.search(r"Case-\d+-(.+?)-\d+$", qid or "")
    return match.group(1) if match else "unknown"


def _short_id(qid: str) -> str:
    """去掉冗长的批次前缀，卡片上展示短 id。"""
    return qid.replace("taskspec_gpt55_long__", "").replace("taskspec_gpt55__", "")


def _status_of(entries: list[tuple[str, dict]]) -> str:
    """validator 语义四态：存在 high 级问题即 fail；medium 或低置信度降级。"""
    severity_counts = Counter()
    needs_review = 0
    for _, data in entries:
        for deduction in data.get("deductions", []):
            severity_counts[str(deduction.get("severity", ""))] += 1
        if float(data.get("confidence") or 0.0) < LOW_CONFIDENCE_THRESHOLD:
            needs_review += 1
    if severity_counts.get("high", 0) > 0:
        return "fail"
    if severity_counts.get("medium", 0) > 0 or needs_review:
        return "needs_review" if needs_review else "pass_with_warnings"
    return "pass"


def _histogram_html(overalls: list[float]) -> str:
    """分数分布直方图（90+ / 80-90 / 75-80 / 70-75 / 60-70 / <60）。"""
    counts = []
    for low, high, _label in HISTO_BINS:
        counts.append(sum(1 for score in overalls if low <= score < high))
    peak = max(counts, default=0)
    bars = "".join(
        f'<div class="bar" style="height:{max(2, round(42 * count / peak)) if peak else 2}px" title="{count} 个"></div>'
        for count in counts
    )
    labels = "".join(f"<span>{label}</span>" for _low, _high, label in HISTO_BINS)
    return f'<div class="histo">{bars}</div><div class="histo-labels">{labels}</div>'


GALLERY_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · 汇总画廊</title>
<style>
  :root { color-scheme: light; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #f6f7f9; color: #1f2328; }
  main { max-width: 1280px; margin: 0 auto; padding: 24px 28px 40px; }
  h1 { margin: 0; font-size: 22px; }
  .sub { margin: 6px 0 0; color: #57606a; font-size: 13px; }
  .status { display: inline-block; margin-left: 10px; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; vertical-align: 3px; }
  .status-fail { background: #fde8e8; color: #c81e1e; }
  .status-pass_with_warnings { background: #fdf3e1; color: #b45309; }
  .status-needs_review { background: #e0ecff; color: #1d4ed8; }
  .status-pass { background: #e6f4ea; color: #057647; }
  .stats { display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0 6px; }
  .stat { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px 18px; min-width: 110px; }
  .stat strong { display: block; font-size: 24px; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .stat span { color: #57606a; font-size: 12px; }
  .histo { display: flex; align-items: flex-end; gap: 4px; height: 46px; padding: 8px 12px 4px; }
  .histo .bar { flex: 1; background: #93c5fd; border-radius: 3px 3px 0 0; min-height: 2px; }
  .histo-labels { display: flex; gap: 4px; padding: 0 12px 8px; }
  .histo-labels span { flex: 1; text-align: center; font-size: 10px; color: #8b949e; }
  .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 14px 0 18px; padding: 12px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; position: sticky; top: 0; z-index: 5; }
  .controls input[type="search"] { padding: 7px 10px; border: 1px solid #d0d7de; border-radius: 8px; font-size: 13px; width: 210px; }
  .controls select { padding: 7px 8px; border: 1px solid #d0d7de; border-radius: 8px; font-size: 13px; background: #fff; }
  .grade-btns { display: inline-flex; gap: 4px; }
  .grade-btns button { border: 1px solid #d0d7de; background: #fff; border-radius: 7px; padding: 6px 10px; font-size: 12.5px; cursor: pointer; color: #374151; }
  .grade-btns button.on { background: #1f2328; color: #fff; border-color: #1f2328; }
  .count-note { margin-left: auto; color: #57606a; font-size: 12.5px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(196px, 1fr)); gap: 14px; }
  .card { display: block; background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit; transition: box-shadow .12s, transform .12s; }
  .card:hover { box-shadow: 0 4px 16px rgba(31,35,40,.12); transform: translateY(-1px); }
  .thumb { position: relative; height: 168px; background: #fff; display: flex; align-items: center; justify-content: center; border-bottom: 1px solid #edf0f2; }
  .thumb img { max-width: 100%; max-height: 168px; object-fit: contain; }
  .cap-flag { position: absolute; top: 8px; right: 8px; background: #b45309; color: #fff; font-size: 10px; padding: 2px 7px; border-radius: 999px; }
  .body { padding: 10px 12px 12px; }
  .sid { font-family: ui-monospace, Consolas, monospace; font-size: 11px; color: #57606a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .score-row { display: flex; align-items: baseline; gap: 8px; margin-top: 4px; }
  .score { font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .grade { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 6px; }
  .g-S, .g-A { background: #e6f4ea; color: #057647; }
  .g-Bp { background: #e0ecff; color: #1d4ed8; }
  .g-B { background: #eef1f4; color: #57606a; }
  .g-C { background: #fdf3e1; color: #b45309; }
  .g-D { background: #fde8e8; color: #c81e1e; }
  .scene { margin-left: auto; font-size: 10px; color: #8b949e; }
  .issues { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; min-height: 20px; }
  .issue { font-size: 10px; padding: 2px 7px; border-radius: 999px; background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; }
  .issue.err { background: #fde8e8; color: #c81e1e; border-color: #f6d5d5; }
  .detail { display: inline-block; margin-top: 8px; font-size: 12px; color: #2563eb; }
  .empty { padding: 60px 0; text-align: center; color: #8b949e; display: none; }
  footer { margin-top: 26px; color: #8b949e; font-size: 12px; line-height: 1.7; }
</style>
</head>
<body>
<main>
  <h1>__TITLE__ · 汇总画廊<span class="status status-__STATUS__">__STATUS__</span></h1>
  <p class="sub">__SUB__</p>
  <div class="stats">
    <div class="stat"><strong>__COUNT__</strong><span>样本</span></div>
    <div class="stat"><strong>__MEAN__</strong><span>均分</span></div>
    <div class="stat"><strong>__MEDIAN__</strong><span>中位分</span></div>
    <div class="stat"><strong>__CAPPED__</strong><span>触发封顶</span></div>
    <div class="stat"><strong>__LOWCONF__</strong><span>低置信度 &lt;0.8</span></div>
    <div class="stat" style="min-width:230px">
      <span>分数分布（90+ / 80-90 / 75-80 / 70-75 / 60-70 / &lt;60）</span>
      __HISTO__
    </div>
  </div>
  <div class="controls">
    <input type="search" id="q" placeholder="搜索样本 ID / 场景…">
    <span class="grade-btns" id="gradeBtns"></span>
    <select id="issueSel"><option value="">全部问题类型</option></select>
    <select id="sortSel">
      <option value="asc">分数 ↑（最差在前）</option>
      <option value="desc">分数 ↓</option>
      <option value="conf">置信度 ↑</option>
      <option value="scene">按场景</option>
    </select>
    <span class="count-note" id="countNote"></span>
  </div>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty">没有匹配的样本</div>
  <footer>
    数据：<code>model_scores.jsonl</code> 与各样本 <code>{qid}/result.json</code> ·
    引擎：内置 <code>Aesthetic_Rule_Check</code> 纯规则评分，不调用外部模型。<br>
    status 语义：<code>fail</code> = 存在 ERROR（high）级问题；<code>needs_review</code> = 无 high 但存在低置信度（&lt;0.8）样本；
    <code>pass_with_warnings</code> = 无 high 但存在 medium 级问题。<br>
    规则未命中 ≠ 视觉验收通过；未命中只表示当前规则没有发现可证明的问题。
  </footer>
</main>
<script>
const SAMPLES = __SAMPLES__;
const GRADES = __GRADE_LIST__;
const grid = document.getElementById('grid');
const emptyEl = document.getElementById('empty');
const countNote = document.getElementById('countNote');
const state = { q: '', grade: '', issue: '', sort: 'asc' };

function esc(s) { return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function gradeCls(g) { return g === 'B+' ? 'g-Bp' : 'g-' + g[0]; }

function cardHtml(s) {
  const issues = s.issues.slice(0, 2).map(([label, sev]) =>
    `<span class="issue${sev === 'high' ? ' err' : ''}">${esc(label)}</span>`).join('')
    + (s.issues.length > 2 ? `<span class="issue">+${s.issues.length - 2}</span>` : '');
  return `<a class="card" href="${esc(s.report)}" title="${esc(s.sid)}">
    <div class="thumb"><img loading="lazy" src="${esc(s.img)}" alt="${esc(s.id)}">${s.caps ? `<span class="cap-flag">封顶×${s.caps}</span>` : ''}</div>
    <div class="body">
      <div class="sid">${esc(s.id)}</div>
      <div class="score-row"><span class="score">${s.score.toFixed(1)}</span><span class="grade ${gradeCls(s.grade)}">${esc(s.grade)}</span><span class="scene">${esc(s.scene)}</span></div>
      <div class="issues">${issues}</div>
      <span class="detail">查看详情 →</span>
    </div></a>`;
}

function apply() {
  let list = SAMPLES.filter(s =>
    (!state.q || s.sid.toLowerCase().includes(state.q) || s.scene.includes(state.q)) &&
    (!state.grade || s.grade === state.grade) &&
    (!state.issue || s.issues.some(([, , code]) => code === state.issue)));
  const key = {
    asc: (a, b) => a.score - b.score,
    desc: (a, b) => b.score - a.score,
    conf: (a, b) => a.conf - b.conf,
    scene: (a, b) => a.scene.localeCompare(b.scene) || a.score - b.score,
  }[state.sort];
  list = list.sort(key);
  grid.innerHTML = list.map(cardHtml).join('');
  emptyEl.style.display = list.length ? 'none' : 'block';
  countNote.textContent = `${list.length} / ${SAMPLES.length} 张`;
}

const gradeSet = ['', ...GRADES];
const btns = document.getElementById('gradeBtns');
gradeSet.forEach(g => {
  const b = document.createElement('button');
  b.textContent = g === '' ? '全部' : g;
  if (g === '') b.classList.add('on');
  b.onclick = () => { state.grade = g; btns.querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on'); apply(); };
  btns.appendChild(b);
});

const issueSel = document.getElementById('issueSel');
const issueCounts = {};
SAMPLES.forEach(s => s.issues.forEach(([label, , code]) => { issueCounts[code] = [label, (issueCounts[code]?.[1] || 0) + 1]; }));
Object.entries(issueCounts).sort((a, b) => b[1][1] - a[1][1]).forEach(([code, [label, n]]) => {
  const o = document.createElement('option');
  o.value = code; o.textContent = `${label}（${n}）`;
  issueSel.appendChild(o);
});

document.getElementById('q').oninput = e => { state.q = e.target.value.trim().toLowerCase(); apply(); };
issueSel.onchange = e => { state.issue = e.target.value; apply(); };
document.getElementById('sortSel').onchange = e => { state.sort = e.target.value; apply(); };
apply();
</script>
</body>
</html>
"""


def _render_gallery_html(config: AutomationConfig, entries: list[tuple[str, dict]]) -> str:
    """渲染 JS 数据驱动的单文件画廊：SAMPLES 数组注入，前端负责筛选/排序。"""
    samples: list[dict] = []
    for qid, data in entries:
        image_path = config.card_output_dir / f"{qid}.png"
        if not image_path.exists():
            image_path = Path(data.get("image_path", ""))
        img_url = _embed_image_data_url(image_path) if image_path.exists() else ""

        deductions = sorted(
            data.get("deductions", []),
            key=lambda d: (SEVERITY_RANK.get(d.get("severity", ""), 3), d.get("score_delta", 0.0)),
        )
        issues = [
            [DEDUCTION_LABELS.get(str(d.get("code")), str(d.get("code"))), str(d.get("severity", "")), str(d.get("code"))]
            for d in deductions
            if d.get("code")
        ]
        samples.append({
            "id": _short_id(qid),
            "sid": qid,
            # 展示分与 grade 口径一致：优先 calibrated_overall（P0-3 标定后最终分），回退 overall
            "score": float(data.get("calibrated_overall") or data.get("overall") or 0.0),
            "grade": str(data.get("grade", "-")),
            "scene": _scene_of(qid),
            "caps": len(data.get("hard_caps", [])),
            "conf": float(data.get("confidence") or 0.0),
            "img": img_url,
            "report": f"{qid}/report.html",
            "issues": issues,
        })

    overalls = sorted(s["score"] for s in samples)
    capped = sum(1 for s in samples if s["caps"])
    low_conf = sum(1 for s in samples if s["conf"] < LOW_CONFIDENCE_THRESHOLD)
    status = _status_of(entries)

    grade_set = {s["grade"] for s in samples}
    grade_list = [g for g in GRADE_ORDER if g in grade_set] + sorted(grade_set - set(GRADE_ORDER))

    # 维度权重摘要，如 "geometry 35 / visual 35 / information 15 / layout 10 / consistency 5"
    weights = ""
    for _, data in entries:
        dims = [d for d in data.get("dimensions", []) if d.get("name")]
        if dims:
            weights = " / ".join(f"{d['name']} {float(d.get('weight', 0.0)):.0f}" for d in dims)
            break

    sub = (
        f"{len(samples)} 张样本 · 本地规则评分（{weights or 'geometry / visual / information / layout / consistency'}，含封顶机制）· "
        f"生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 点击卡片进入单样本详情报告"
    )

    samples_json = json.dumps(samples, ensure_ascii=False).replace("</", "<\\/")

    return (
        GALLERY_HTML.replace("__TITLE__", "纯规则美学评分")
        .replace("__STATUS__", status)
        .replace("__SUB__", html.escape(sub))
        .replace("__COUNT__", str(len(samples)))
        .replace("__MEAN__", f"{statistics.mean(overalls):.2f}")
        .replace("__MEDIAN__", f"{statistics.median(overalls):.2f}")
        .replace("__CAPPED__", f"{capped}/{len(samples)}")
        .replace("__LOWCONF__", str(low_conf))
        .replace("__HISTO__", _histogram_html(overalls))
        .replace("__SAMPLES__", samples_json)
        .replace("__GRADE_LIST__", json.dumps(grade_list, ensure_ascii=False))
    )
