"""`fp-audit` Typer CLI.

Three commands per `tools/fp-audit/README.md`:
- `run` — execute the audit against one rule or all rules
- `add-fixture` — append a new fixture entry to known-good or known-bad
- `report` — render the audit report against the schema

Until the engine is wired in, the CLI surface returns
`deferred_engine_unavailable` decisions for every rule with exit code 0.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.table import Table

from saferskills_fp_audit.runner import AuditDecision, run_audit

app = typer.Typer(
    name="fp-audit",
    help="SaferSkills false-positive audit harness.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()


def _project_root() -> Path:
    """Resolve the SaferSkills repo root from this file's location."""
    return Path(__file__).resolve().parents[3]


@app.command()
def run(
    rule: Annotated[
        str | None,
        typer.Option(help="Single rule_id to audit (e.g. SS-SKILL-INJECT-IGNORE-01)."),
    ] = None,
    all_rules: Annotated[bool, typer.Option("--all", help="Audit every rule in rubric/.")] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Print fixture + rule discovery without running the engine."
        ),
    ] = False,
) -> None:
    """Run the FP audit."""
    if not rule and not all_rules and not dry_run:
        console.print("[red]Specify --rule <id>, --all, or --dry-run.[/red]")
        raise typer.Exit(code=2)

    root = _project_root()
    report = run_audit(
        repo_root=root,
        rule_id=rule,
        run_all=all_rules,
        dry_run=dry_run,
    )

    table = Table(title=f"FP Audit (rubric={report.rubric_version[:7]})")
    table.add_column("Rule ID", style="cyan")
    table.add_column("Fixtures", justify="right")
    table.add_column("TP", justify="right")
    table.add_column("FP", justify="right")
    table.add_column("FP Rate", justify="right")
    table.add_column("Decision", style="green")

    for entry in report.per_rule:
        decision_style = {
            AuditDecision.PROMOTE_TO_ACTIVE: "[green]promote_to_active[/green]",
            AuditDecision.ACTIVE_CONFIRMED: "[green]active_confirmed[/green]",
            AuditDecision.SHADOW_EXTENDED: "[yellow]shadow_extended[/yellow]",
            AuditDecision.DEMOTE_TO_SHADOW: "[red]demote_to_shadow[/red]",
            AuditDecision.DEFERRED_ENGINE_UNAVAILABLE: "[dim]deferred_engine_unavailable[/dim]",
        }[entry.decision]
        table.add_row(
            entry.rule_id,
            str(entry.fixtures_evaluated),
            str(entry.true_positives),
            str(entry.false_positives),
            f"{entry.fp_rate:.2%}",
            decision_style,
        )

    console.print(table)


@app.command("add-fixture")
def add_fixture(
    source_url: Annotated[str, typer.Argument(help="GitHub URL of the upstream fixture source.")],
    label: Annotated[str, typer.Option(help="Fixture label: good or bad.")] = "good",
    notes: Annotated[str, typer.Option(help="Per-fixture context — cite the source.")] = "",
) -> None:
    """Append a new fixture entry to the appropriate manifest."""
    if label not in {"good", "bad"}:
        console.print(f"[red]Label must be 'good' or 'bad' (got {label}).[/red]")
        raise typer.Exit(code=2)

    root = _project_root()
    manifest_path = root / "tools" / "fp-audit" / "fixtures" / f"known-{label}" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]]
    if manifest_path.exists():
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or []
    else:
        manifest = []

    slug = source_url.rstrip("/").split("/")[-2:]
    new_entry: dict[str, object] = {
        "path": "--".join(slug),
        "source_url": source_url,
        "hash_at_capture": None,
        "notes": notes,
    }
    if label == "good":
        new_entry["expected_score_range"] = [80, 100]
    manifest.append(new_entry)
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    console.print(f"[green]Appended fixture[/green] {new_entry['path']} → {manifest_path}")


@app.command()
def report(
    output: Annotated[Path, typer.Option(help="Output path for the JSON report.")] = Path(
        "fp_audit_report.json"
    ),
) -> None:
    """Render the FP-audit report (validated against schemas/fp-audit-report.schema.json)."""
    root = _project_root()
    report_obj = run_audit(repo_root=root, run_all=True, dry_run=False)
    output.write_text(json.dumps(report_obj.to_dict(), indent=2), encoding="utf-8")
    console.print(f"[green]Wrote report[/green] → {output}")


if __name__ == "__main__":
    app()
