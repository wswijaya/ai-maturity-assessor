"""
Report generator for the AI Maturity Assessment.

Architecture:
- Claude generates ONLY narrative prose (executive summary, per-dimension assessments,
  recommendations, next steps). It receives scores/evidence as read-only context.
- All factual data (scores, evidence, gaps) is assembled directly from AssessmentSession.
  Claude cannot write to those fields — hallucination is structurally impossible.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from src.models.assessment import AssessmentSession, DimensionID, MaturityLevel

DEFAULT_MODEL = "claude-opus-4-7"


# ---------------------------------------------------------------------------
# Pydantic schema for Claude's narrative output — prose ONLY, no scores
# ---------------------------------------------------------------------------

class _DimNarrative(BaseModel):
    dimension_id: str = Field(description="Must match a DimensionID value exactly.")
    assessment: str = Field(description="1–2 sentence narrative assessment grounded in the evidence provided.")


class _ReportNarratives(BaseModel):
    executive_summary: str = Field(
        description=(
            "2–3 paragraph narrative. Cover: overall maturity level and what it means, "
            "the organisation's top 2–3 strengths, and the top 2–3 gaps that most limit "
            "progress. Be specific — reference the organisation by name."
        )
    )
    dimension_assessments: list[_DimNarrative] = Field(
        description="One narrative entry per dimension. Must include all 6 dimensions."
    )
    recommendations: list[str] = Field(
        description=(
            "3–5 prioritised, actionable recommendations. Each should be a complete sentence "
            "explaining what to do and why, grounded in evidence from the assessment."
        )
    )
    next_steps_30_days: list[str] = Field(description="2–3 concrete actions achievable within 30 days.")
    next_steps_60_days: list[str] = Field(description="2–3 actions achievable within 60 days.")
    next_steps_90_days: list[str] = Field(description="2–3 actions achievable within 90 days.")


# ---------------------------------------------------------------------------
# System prompt for the report generation call
# ---------------------------------------------------------------------------

_NARRATIVE_SYSTEM = """\
You are a senior AI strategy consultant writing an executive assessment report.

You will be given a structured briefing containing:
- Organisation context (name, industry, interviewee)
- Per-dimension interview evidence, scores (already assigned), and gaps

YOUR JOB:
Write the narrative sections of the report. You are a narrator and analyst — not a scorer.

HARD CONSTRAINTS:
1. NEVER invent, modify, or dispute scores. Scores are already assigned and shown in the briefing.
2. NEVER invent evidence. Only reference what is explicitly stated in the briefing's evidence lists.
3. NEVER add evidence bullets, score numbers, or gap bullets to your output — those come from elsewhere.
4. Write narrative prose only. Your output is JSON containing strings and string arrays.
5. Be specific: name the organisation, reference actual evidence from the briefing.
6. Be actionable: recommendations must be grounded in identified gaps.
7. Calibrate tone to the overall score. A score of 1–2 warrants candour about urgency.

OUTPUT FORMAT:
Respond with a single JSON object matching the schema you will be given. No other text.
"""


# ---------------------------------------------------------------------------
# Briefing builder — the factual context given to Claude
# ---------------------------------------------------------------------------

def _build_briefing(session: AssessmentSession) -> str:
    ctx = session.org_context
    lines: list[str] = []

    if ctx:
        lines.append(
            f"ORGANISATION: {ctx.org_name}\n"
            f"INDUSTRY: {ctx.industry}\n"
            f"INTERVIEWEE: {ctx.interviewee_name} ({ctx.interviewee_role})"
        )
        if ctx.employee_count:
            lines[-1] += f"\nEMPLOYEE COUNT: {ctx.employee_count}"

    lines.append("")
    lines.append(f"OVERALL SCORE: {session.overall_score}/5 — {session.overall_level.label() if session.overall_level else 'N/A'}")
    lines.append("")

    lines.append("DIMENSION SCORES AND EVIDENCE:")
    for dim in session.dimensions.values():
        lines.append(f"\n[{dim.dimension_id.value}] {dim.label} — Score: {dim.score}/5")
        if dim.evidence:
            lines.append("  Evidence:")
            for ev in dim.evidence:
                lines.append(f"    - {ev}")
        if dim.gaps:
            lines.append("  Gaps:")
            for gap in dim.gaps:
                lines.append(f"    - {gap}")
        if dim.score_rationale:
            lines.append(f"  Rationale: {dim.score_rationale}")
        # Include a condensed transcript excerpt for narrative context
        interviewee_turns = [t for t in dim.transcript if t.role == "interviewee"]
        if interviewee_turns:
            lines.append("  Key interviewee statements (excerpts):")
            for turn in interviewee_turns[:3]:
                excerpt = turn.content[:600].replace("\n", " ")
                lines.append(f"    • {excerpt}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude call — structured output with fallback
# ---------------------------------------------------------------------------

def _generate_narratives(
    session: AssessmentSession,
    client: anthropic.Anthropic,
    model: str,
) -> _ReportNarratives:
    briefing = _build_briefing(session)
    user_message = (
        f"Please write the narrative report sections for this assessment.\n\n"
        f"=== ASSESSMENT BRIEFING ===\n{briefing}\n=== END BRIEFING ==="
    )

    # Primary path: structured output via messages.parse
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=4096,
            system=_NARRATIVE_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            output_format=_ReportNarratives,
        )
        return response.parsed
    except (AttributeError, Exception):
        pass

    # Fallback: plain create + manual JSON extraction
    schema_hint = json.dumps(_ReportNarratives.model_json_schema(), indent=2)
    fallback_message = (
        f"{user_message}\n\n"
        f"Respond with a single JSON object matching this schema:\n{schema_hint}"
    )
    raw = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_NARRATIVE_SYSTEM,
        messages=[{"role": "user", "content": fallback_message}],
    ).content[0].text

    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    data = json.loads(clean)
    return _ReportNarratives.model_validate(data)


# ---------------------------------------------------------------------------
# Markdown assembler — facts from session, prose from narratives
# ---------------------------------------------------------------------------

def _lookup_narrative(narratives: _ReportNarratives, dim_id: DimensionID) -> str:
    for entry in narratives.dimension_assessments:
        if entry.dimension_id == dim_id.value:
            return entry.assessment
    return ""


def _assemble_markdown(
    session: AssessmentSession,
    narratives: _ReportNarratives,
    date_str: str,
) -> str:
    ctx = session.org_context
    org_name = ctx.org_name if ctx else "Unknown"
    lines: list[str] = []
    w = lines.append

    # Header
    w("# AI Maturity Assessment Report")
    w(f"## Organisation: {org_name}")
    w(f"## Date: {date_str}")
    w("## Conducted by: AI Maturity Assessment Agent")
    w("")
    w("---")
    w("")

    # Executive summary — Claude-generated prose
    w("## Executive Summary")
    w("")
    w(narratives.executive_summary)
    w("")

    # Overall level — from session state
    if session.overall_level:
        level = session.overall_level
        w(
            f"## Overall Maturity Level: {session.overall_score}/5 — "
            f"Level {level.value} — {level.label()}"
        )
        w("")
        w(f"*{level.description()}*")
    else:
        w("## Overall Maturity Level: N/A")
    w("")
    w("---")
    w("")

    # Dimension scores — facts from session, narrative from Claude
    w("## Dimension Scores")
    w("")
    for i, (dim_id, dim) in enumerate(session.dimensions.items(), start=1):
        score_str = f"{dim.score}/5" if dim.score is not None else "Not scored"
        w(f"### {i}. {dim.label} — Score: {score_str}")
        w("")

        # Evidence — from session only
        if dim.evidence:
            w("**Evidence:**")
            for ev in dim.evidence:
                w(f"- {ev}")
            w("")

        # Assessment narrative — from Claude
        narrative = _lookup_narrative(narratives, dim_id)
        if narrative:
            w(f"**Assessment:** {narrative}")
            w("")

        # Gaps — from session only
        if dim.gaps:
            w("**Gaps:**")
            for gap in dim.gaps:
                w(f"- {gap}")
            w("")

    w("---")
    w("")

    # Recommendations — Claude-generated
    w("## Key Recommendations")
    w("")
    for i, rec in enumerate(narratives.recommendations, start=1):
        w(f"{i}. {rec}")
    w("")

    # Next steps — Claude-generated
    w("## Next Steps")
    w("")
    w("### 30-Day Actions")
    for action in narratives.next_steps_30_days:
        w(f"- {action}")
    w("")
    w("### 60-Day Actions")
    for action in narratives.next_steps_60_days:
        w(f"- {action}")
    w("")
    w("### 90-Day Actions")
    for action in narratives.next_steps_90_days:
        w(f"- {action}")
    w("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_report(
    session: AssessmentSession,
    client: Optional[anthropic.Anthropic] = None,
    model: str = DEFAULT_MODEL,
) -> Path:
    """
    Generate a full Markdown report for a completed AssessmentSession.

    Scores, evidence, and gaps are pulled directly from session state.
    Executive summary, dimension narratives, recommendations, and next steps
    are generated by a Claude API call.

    Returns the path to the saved Markdown file.
    """
    if not session.is_complete:
        raise ValueError("Cannot generate report for an incomplete session.")
    if not all(d.is_complete for d in session.dimensions.values()):
        incomplete = [d.label for d in session.dimensions.values() if not d.is_complete]
        raise ValueError(f"Dimensions not yet scored: {', '.join(incomplete)}")

    _client = client or anthropic.Anthropic()
    narratives = _generate_narratives(session, _client, model)

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    ctx = session.org_context
    org_slug = ctx.org_name.lower().replace(" ", "_") if ctx else "session"
    stem = f"{org_slug}_{session.session_id}"

    out_dir = Path("assessments")
    out_dir.mkdir(exist_ok=True)

    md_content = _assemble_markdown(session, narratives, date_str)
    md_path = out_dir / f"{stem}.md"
    md_path.write_text(md_content, encoding="utf-8")

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    return md_path
