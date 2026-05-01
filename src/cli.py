"""
Entry point for the AI Maturity Assessment tool.
Run with: python3 src/cli.py
Dry-run demo: python3 src/cli.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from src.agent.interviewer import Interviewer
from src.agent.prompts import DIMENSION_TRANSITION, OPENING_QUESTIONS
from src.llm.factory import create_llm_client
from src.models.assessment import (
    AssessmentSession,
    DimensionID,
    MaturityLevel,
    OrgContext,
)
from src.output.report_generator import generate_report

console = Console()

_SCORE_COLOUR: dict[int, str] = {
    1: "red",
    2: "orange3",
    3: "yellow",
    4: "green",
    5: "bold green",
}


# ---------------------------------------------------------------------------
# Greeting
# ---------------------------------------------------------------------------

def _greet(dry_run: bool = False) -> None:
    title = "[bold blue]Welcome — DEMO MODE[/bold blue]" if dry_run else "[bold blue]Welcome[/bold blue]"
    body = (
        "[bold]AI Maturity Assessment[/bold]  [dim](dry run)[/dim]\n\n"
        "This demo simulates [bold]2 of 6 dimensions[/bold] with scripted responses.\n"
        "No API calls are made. Use it to preview the interview flow."
        if dry_run else
        "[bold]AI Maturity Assessment[/bold]\n\n"
        "A structured interview that evaluates your organisation's AI maturity "
        "across [bold]6 dimensions[/bold] of the Gartner AI Maturity Model.\n\n"
        "The session takes approximately [bold]25–30 minutes[/bold].\n"
        "Candid answers produce the most accurate and useful assessment."
    )
    console.print()
    console.print(
        Panel(
            Text.from_markup(body, justify="center"),
            title=title,
            border_style="blue",
            padding=(1, 4),
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Org context collection
# ---------------------------------------------------------------------------

def _collect_org_context() -> OrgContext:
    console.print(Rule("[bold yellow]Organisation Context[/bold yellow]", style="yellow"))
    console.print(
        "  [dim]This context frames the assessment and calibrates scoring.[/dim]"
    )
    console.print()

    org_name         = Prompt.ask("  [bold]Organisation name[/bold]")
    industry         = Prompt.ask("  [bold]Industry[/bold]")
    interviewee_name = Prompt.ask("  [bold]Your name[/bold]")
    interviewee_role = Prompt.ask("  [bold]Your role / title[/bold]")
    headcount        = Prompt.ask(
        "  [bold]Approx. employee count[/bold] [dim](e.g. 200–500, optional)[/dim]",
        default="",
    )

    console.print()
    return OrgContext(
        org_name=org_name,
        industry=industry,
        interviewee_name=interviewee_name,
        interviewee_role=interviewee_role,
        employee_count=headcount.strip() or None,
    )


def _confirm_ready(ctx: OrgContext) -> bool:
    console.print(Rule(style="dim"))
    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_row("[dim]Organisation[/dim]", ctx.org_name)
    summary.add_row("[dim]Industry[/dim]",     ctx.industry)
    summary.add_row(
        "[dim]Interviewee[/dim]",
        f"{ctx.interviewee_name}  ·  {ctx.interviewee_role}",
    )
    if ctx.employee_count:
        summary.add_row("[dim]Employee count[/dim]", ctx.employee_count)
    console.print(summary)
    console.print()
    return Confirm.ask("  Ready to begin the interview?", default=True)


# ---------------------------------------------------------------------------
# Interviewer I/O callbacks
# ---------------------------------------------------------------------------

def _show_output(text: str) -> None:
    console.print()
    console.print(
        Panel(
            text,
            title="[dim blue]Consultant[/dim blue]",
            border_style="blue",
            padding=(0, 2),
        )
    )


def _show_user_echo(text: str) -> None:
    """Display a pre-scripted user reply (dry-run only)."""
    console.print()
    console.print(f"[bold green]  You (demo)[/bold green]  [dim]{text}[/dim]")


def _get_input() -> str:
    console.print()
    return Prompt.ask("[bold green]  You[/bold green]")


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _assessments_dir() -> Path:
    path = Path("assessments")
    path.mkdir(exist_ok=True)
    return path


def _save_partial(session: AssessmentSession) -> Path:
    path = _assessments_dir() / f"partial_{session.session_id}.json"
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Score summary table — printed after report generation
# ---------------------------------------------------------------------------

def _print_score_summary(session: AssessmentSession) -> None:
    console.print()
    console.print(Rule("[bold yellow]Assessment Summary[/bold yellow]", style="yellow"))
    console.print()

    tbl = Table(
        "Dimension",
        "Score",
        "Maturity Level",
        border_style="yellow",
        show_lines=True,
        title=(
            f"[bold]{session.org_context.org_name}[/bold]"
            if session.org_context
            else ""
        ),
    )

    for dim in session.dimensions.values():
        if dim.score is not None and 1 <= dim.score <= 5:
            colour = _SCORE_COLOUR[dim.score]
            score_cell = f"[{colour}]{dim.score}/5[/{colour}]"
            level_cell = f"[{colour}]{MaturityLevel(dim.score).label()}[/{colour}]"
        else:
            score_cell = "[dim]—[/dim]"
            level_cell = "[dim]—[/dim]"
        tbl.add_row(dim.label, score_cell, level_cell)

    if session.overall_level:
        c = _SCORE_COLOUR.get(session.overall_level.value, "dim")
        tbl.add_row(
            "[bold]Overall[/bold]",
            f"[{c}][bold]{session.overall_score}/5[/bold][/{c}]",
            f"[{c}][bold]Level {session.overall_level.value} — {session.overall_level.label()}[/bold][/{c}]",
        )

    console.print(tbl)
    console.print()


# ---------------------------------------------------------------------------
# Dry-run mock data
# ---------------------------------------------------------------------------

_DRY_RUN_ORG = OrgContext(
    org_name="Acme Corp",
    industry="Retail",
    interviewee_name="Alex Chen",
    interviewee_role="Head of Data & Analytics",
    employee_count="1,000–5,000",
)

# Each entry: dimension, scripted (probe, answer) pairs, and the resulting score.
_DRY_RUN_DIMS: list[dict] = [
    {
        "dim_id": DimensionID.STRATEGY,
        # Each tuple: (interviewee answer, consultant follow-up | None).
        # None on the last entry means scoring triggers immediately after that answer.
        "exchange": [
            (
                "Our CTO chairs an informal AI task force. It meets monthly but there's no formal mandate or charter yet.",
                "Is there a dedicated AI budget line, or is investment embedded in other programmes?",
            ),
            (
                "No dedicated line — we draw from the IT transformation budget. Maybe £200k this year in total.",
                "How does this AI activity connect to specific business outcomes?",
            ),
            (
                "We have two pilot targets: demand forecasting and a customer service chatbot. But no written roadmap beyond them.",
                None,
            ),
        ],
        "score": 2,
        "rationale": "AI activity is present with CTO sponsorship but entirely informal — no written roadmap, dedicated budget, or governance structure.",
        "evidence": [
            "CTO chairs monthly AI task force with no formal mandate",
            "AI funded from IT transformation budget (~£200k); no dedicated line item",
            "Two pilots identified but no documented roadmap beyond them",
        ],
        "gaps": [
            "No written AI strategy or roadmap",
            "No dedicated budget line",
            "AI strategy not communicated beyond the technology function",
        ],
    },
    {
        "dim_id": DimensionID.DATA,
        "exchange": [
            (
                "We have a Snowflake warehouse and a data catalog. Most teams can self-serve for structured data.",
                "What does your data quality management process look like in practice?",
            ),
            (
                "Data ownership is assigned per domain. We run quality checks on ingestion but there are no formal SLAs.",
                "What's the biggest data bottleneck when starting a new AI project?",
            ),
            (
                "Getting clean, labelled training data. Every ML project ends up doing a lot of manual curation work.",
                None,
            ),
        ],
        "score": 3,
        "rationale": "Data infrastructure is operationally sound with self-serve access, but ML-specific tooling and formal quality SLAs are absent.",
        "evidence": [
            "Snowflake warehouse with self-serve data catalog in production",
            "Domain-level data ownership with quality checks on ingestion",
            "No labelled training data pipeline — sourcing is ad hoc and manual",
        ],
        "gaps": [
            "No feature store or shared ML data layer",
            "No formal data quality SLAs",
            "Labelled training data sourcing is a bottleneck for every ML project",
        ],
    },
]


def _run_dry_run() -> None:
    """Run a 2-dimension scripted demo without making any API calls."""
    _greet(dry_run=True)

    session = AssessmentSession()
    session.org_context = _DRY_RUN_ORG

    # Show the pre-filled context as the user would normally enter it.
    ctx = _DRY_RUN_ORG
    ctx_tbl = Table(show_header=False, box=None, padding=(0, 2))
    ctx_tbl.add_row("[dim]Organisation[/dim]", ctx.org_name)
    ctx_tbl.add_row("[dim]Industry[/dim]",     ctx.industry)
    ctx_tbl.add_row("[dim]Interviewee[/dim]",  f"{ctx.interviewee_name}  ·  {ctx.interviewee_role}")
    ctx_tbl.add_row("[dim]Employee count[/dim]", ctx.employee_count or "")
    console.print(Rule("[bold yellow]Organisation Context  [dim](demo)[/dim][/bold yellow]", style="yellow"))
    console.print(ctx_tbl)
    console.print()

    console.print(Rule(
        "[bold blue]Interview  [dim](dry run — 2 of 6 dimensions)[/dim][/bold blue]",
        style="blue",
    ))

    for i, mock in enumerate(_DRY_RUN_DIMS):
        dim_id: DimensionID = mock["dim_id"]
        dim = session.dimensions[dim_id]
        session.current_dimension = dim_id

        _show_output(OPENING_QUESTIONS[dim_id])

        for answer, follow_up in mock["exchange"]:
            _show_user_echo(answer)
            if follow_up:
                _show_output(follow_up)

        dim.close(
            score=mock["score"],
            rationale=mock["rationale"],
            evidence=mock["evidence"],
            gaps=mock["gaps"],
        )

        if i < len(_DRY_RUN_DIMS) - 1:
            next_label = session.dimensions[_DRY_RUN_DIMS[i + 1]["dim_id"]].label
            _show_output(DIMENSION_TRANSITION.format(next_dimension=next_label))

    session.current_dimension = None

    console.print()
    console.print(Rule("[dim]Dry-run complete — 2 of 6 dimensions simulated[/dim]", style="dim"))

    _print_score_summary(session)

    console.print(
        Panel(
            "[dim]Report generation is skipped in dry-run mode.[/dim]\n\n"
            "Run [bold]python3 src/cli.py[/bold] (without [bold]--dry-run[/bold]) "
            "for a full 6-dimension assessment and narrative report.",
            border_style="dim",
            padding=(0, 2),
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Maturity Assessment — Gartner-model structured interview.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run a 2-dimension scripted demo without calling the API.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.dry_run:
        _run_dry_run()
        return

    session: AssessmentSession | None = None

    try:
        _greet()
        org_ctx = _collect_org_context()

        if not _confirm_ready(org_ctx):
            console.print()
            console.print("  [dim]Interview cancelled. Goodbye.[/dim]")
            return

        session = AssessmentSession()
        session.org_context = org_ctx

        console.print()
        console.print(Rule("[bold blue]Interview[/bold blue]", style="blue"))

        llm = create_llm_client()
        interviewer = Interviewer(session=session, client=llm)
        interviewer.run(get_input=_get_input, show_output=_show_output)

        console.print("  [dim]Generating narrative report…[/dim]")
        report_path = generate_report(session, client=llm)

        _print_score_summary(session)

        console.print(
            Panel(
                f"Report saved to [bold]{report_path}[/bold]",
                title="[bold green]Assessment Complete[/bold green]",
                border_style="green",
                padding=(0, 2),
            )
        )
        console.print()

    except KeyboardInterrupt:
        console.print()
        console.print()
        console.print("  [yellow]Interview interrupted.[/yellow]")

        if session is not None and not session.is_complete:
            if Confirm.ask("  Save partial session?", default=True):
                path = _save_partial(session)
                console.print(f"  [dim]Partial session saved → {path}[/dim]")

        console.print()
        console.print("  [dim]Goodbye.[/dim]")
        sys.exit(0)


if __name__ == "__main__":
    main()
