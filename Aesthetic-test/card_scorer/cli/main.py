"""CLI entry point using Typer.

Usage:
    card-scorer --image screenshot.png --query "涓婃捣澶╂皵" [--dsl card.json] [--output report/]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="card-scorer",
    help="Card Aesthetic Scoring System - Automatically filter ugly cards.",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def score(
    image: str = typer.Option(..., "--image", "-i", help="Path to card screenshot"),
    query: str = typer.Option("", "--query", "-q", help="Query text or path to query.txt"),
    dsl: str = typer.Option("", "--dsl", "-d", help="Path to DSL JSON file (optional)"),
    output: str = typer.Option("report", "--output", "-o", help="Output directory"),
    profile: str = typer.Option("default", "--profile", "-p", help="Validation profile (default, strict, quick)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Score a card screenshot for aesthetic quality."""
    _setup_logging(verbose)

    # Validate image
    if not Path(image).exists():
        console.print(f"[red]Error:[/red] Image not found: {image}")
        raise typer.Exit(1)

    # Read query from file if it looks like a file path
    query_text = query
    if query and Path(query).exists() and Path(query).suffix in (".txt", ".text"):
        query_text = Path(query).read_text(encoding="utf-8").strip()

    # Run pipeline
    from card_scorer.engine.context import build_context
    from card_scorer.engine.scorer import score as run_score
    from card_scorer.reports.json_report import save as save_json
    from card_scorer.reports.html_report import save as save_html

    console.print("[bold]Running card aesthetic scoring...[/bold]")

    ctx, _ = build_context(
        image_path=image,
        query=query_text,
        dsl_path=dsl,
    )

    report = run_score(ctx, profile=profile)

    # Output
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = save_json(report, str(output_dir / "report.json"))
    html_path = save_html(report, str(output_dir / "report.html"), image_path=image)

    # Console output
    status_style = "green" if report.status == "PASS" else "red"
    console.print()
    console.print(f"[bold]Card Score: [{status_style}]{report.total_score}[/{status_style}][/bold]")
    console.print(f"[bold]Status: [{status_style}]{report.status}[/{status_style}][/bold]")
    console.print()

    if report.deduction_details:
        table = Table(title="Top Issues")
        table.add_column("Rule", style="cyan")
        table.add_column("Severity")
        table.add_column("Deduction", justify="right")
        table.add_column("Explanation")

        # Sort by deduction amount
        sorted_issues = sorted(report.deduction_details, key=lambda r: r.score_delta)
        for r in sorted_issues:
            sev_style = {
                "fatal": "red bold",
                "major": "yellow",
                "minor": "blue",
                "info": "dim",
            }.get(r.severity.value, "")
            table.add_row(
                f"{r.rule_id} {r.rule_name}",
                f"[{sev_style}]{r.severity.value}[/{sev_style}]",
                str(r.score_delta),
                r.explanation,
            )
        console.print(table)
    else:
        console.print("[green]No issues detected. All rules passed.[/green]")

    console.print()
    console.print(f"JSON report: {json_path}")
    console.print(f"HTML report: {html_path}")

    # Exit code for CI
    if report.status == "FAIL":
        raise typer.Exit(1)


def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()

