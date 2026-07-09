from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from .models import EvaluationResult, MetricResult


def write_outputs(result: EvaluationResult, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "result.json"
    html_path = output_dir / "report.html"
    json_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(result), encoding="utf-8")
    return json_path, html_path


def write_batch_index(results: list[EvaluationResult], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    index_path = output_dir / "index.html"
    summary_path.write_text(
        json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    index_path.write_text(render_batch_html(results), encoding="utf-8")
    return summary_path, index_path


def render_html(result: EvaluationResult) -> str:
    image_data = image_data_url(result.image_path)
    dimensions = "\n".join(render_dimension(result_dimension) for result_dimension in result.dimensions)
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in result.warnings) or "<li>无</li>"
    required = "".join(f"<li>{html.escape(item.text)}</li>" for item in result.required_texts) or "<li>无</li>"
    missing = "".join(f"<li>{html.escape(item)}</li>" for item in result.missing_texts) or "<li>无</li>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Aesthetic Rule Check Report</title>
  <style>
    :root {{ color-scheme: light; font-family: Arial, "Microsoft YaHei", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #1f2328; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 16px; font-size: 24px; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .summary {{ display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }}
    .score {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 18px; }}
    .score strong {{ display: block; font-size: 44px; line-height: 1; }}
    .image {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }}
    .image img {{ max-width: 100%; height: auto; display: block; margin: 0 auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }}
    section {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #edf0f2; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ color: #57606a; font-weight: 600; }}
    .bar {{ height: 8px; background: #edf0f2; border-radius: 999px; overflow: hidden; }}
    .fill {{ height: 100%; background: #2563eb; }}
    ul {{ margin: 0; padding-left: 18px; }}
    code {{ background: #f0f2f4; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>纯规则美学检测报告</h1>
  <div class="summary">
    <section class="score">
      <h2>总分</h2>
      <strong>{result.overall:.2f}</strong>
      <p>等级：{html.escape(result.grade)}</p>
      <p>可信度：{result.confidence:.2%}</p>
    </section>
    <section class="image">
      <img src="{image_data}" alt="card screenshot">
    </section>
  </div>
  <div class="grid">
    {dimensions}
    <section>
      <h2>必要显示信息</h2>
      <ul>{required}</ul>
    </section>
    <section>
      <h2>缺失信息</h2>
      <ul>{missing}</ul>
    </section>
    <section>
      <h2>警告</h2>
      <ul>{warnings}</ul>
    </section>
  </div>
</main>
</body>
</html>
"""


def render_batch_html(results: list[EvaluationResult]) -> str:
    rows = "\n".join(render_batch_row(result) for result in results)
    average = sum(result.overall for result in results) / len(results) if results else 0.0
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Aesthetic Rule Check Batch Report</title>
  <style>
    :root {{ color-scheme: light; font-family: Arial, "Microsoft YaHei", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #1f2328; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 16px; font-size: 24px; }}
    .summary {{ display: flex; gap: 16px; margin-bottom: 16px; }}
    .stat {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px 18px; }}
    .stat strong {{ display: block; font-size: 28px; line-height: 1; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid #edf0f2; padding: 10px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: #57606a; font-weight: 600; }}
    a {{ color: #2563eb; text-decoration: none; }}
  </style>
</head>
<body>
<main>
  <h1>纯规则美学批量检测报告</h1>
  <div class="summary">
    <div class="stat"><strong>{len(results)}</strong><span>图片数量</span></div>
    <div class="stat"><strong>{average:.2f}</strong><span>平均分</span></div>
  </div>
  <table>
    <thead><tr><th>图片</th><th>总分</th><th>等级</th><th>可信度</th><th>维度分</th><th>报告</th><th>警告</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</main>
</body>
</html>
"""


def render_batch_row(result: EvaluationResult) -> str:
    dimension_text = " / ".join(f"{item.label}:{item.score:.1f}" for item in result.dimensions)
    report_dir = result.image_path.stem
    warnings = "; ".join(result.warnings[:3])
    if len(result.warnings) > 3:
        warnings += f"; +{len(result.warnings) - 3}"
    return (
        "<tr>"
        f"<td>{html.escape(result.image_path.name)}</td>"
        f"<td>{result.overall:.2f}</td>"
        f"<td>{html.escape(result.grade)}</td>"
        f"<td>{result.confidence:.2%}</td>"
        f"<td>{html.escape(dimension_text)}</td>"
        f"<td><a href=\"{html.escape(report_dir)}/report.html\">report.html</a></td>"
        f"<td>{html.escape(warnings or '无')}</td>"
        "</tr>"
    )


def render_dimension(dimension) -> str:
    rows = "\n".join(render_metric(metric) for metric in dimension.metrics)
    return f"""<section>
  <h2>{html.escape(dimension.label)}：{dimension.score:.2f}</h2>
  <div class="bar"><div class="fill" style="width:{max(0, min(100, dimension.score)):.2f}%"></div></div>
  <table>
    <thead><tr><th>Metric</th><th>Score</th><th>Value</th><th>Formula</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>"""


def render_metric(metric: MetricResult) -> str:
    score = "" if metric.score is None else f"{metric.score:.2f}"
    value = html.escape(json.dumps(metric.value, ensure_ascii=False)) if isinstance(metric.value, (dict, list)) else html.escape(str(metric.value))
    return (
        "<tr>"
        f"<td><code>{html.escape(metric.name)}</code></td>"
        f"<td>{score}</td>"
        f"<td>{value}</td>"
        f"<td>{html.escape(metric.formula)}</td>"
        "</tr>"
    )


def image_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"
