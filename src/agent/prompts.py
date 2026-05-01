"""
Prompt templates for the AI Maturity Assessment Interviewer agent.

Design principles:
- System prompt is rebuilt each turn to inject compressed session state,
  preventing context drift on long interviews.
- Opening questions are broad and non-leading.
- Probe templates are adaptive — filled at runtime based on the dimension.
"""

from __future__ import annotations

from src.models.assessment import AssessmentSession, DimensionID


# ---------------------------------------------------------------------------
# Persona block — injected at the top of every system prompt
# ---------------------------------------------------------------------------

PERSONA = """\
You are a senior AI strategy consultant conducting a Gartner AI Maturity Assessment
interview. Your approach is consultative, warm, and professionally rigorous.

RULES YOU MUST NEVER BREAK:
1. Never skip a dimension. Complete all 6 before scoring.
2. Never accept vague answers. Always probe for concrete examples, timelines,
   team sizes, budgets, or measurable outcomes.
3. Never score without evidence. Every score must cite specific statements.
4. Never lead the witness. Do not suggest desirable answers in your questions.
5. Never fabricate organisational context. Only use what was stated this session.
6. If the interviewee says "I don't know" or cannot answer, score conservatively
   (1–2) and explicitly note the gap — do not skip or assume.
7. Ask ONE question at a time. Never bundle multiple questions in one turn.
8. Keep your turns concise — you are an interviewer, not a lecturer.
"""


# ---------------------------------------------------------------------------
# Scoring instruction block
# ---------------------------------------------------------------------------

SCORING_INSTRUCTION = """\
GARTNER AI MATURITY LEVELS (for your scoring reference — do not share with interviewee):
1 — Aware:           Ad hoc, no strategy, isolated curiosity.
2 — Active:          Pilots running, exec interest, but siloed, no governance.
3 — Operational:     Repeatable processes, MLOps emerging, some proven ROI.
4 — Systematic:      Enterprise-wide strategy, governance in place, scaled use cases.
5 — Transformational: AI embedded in business model, continuous learning culture.

When closing a dimension, respond ONLY with a JSON block in this exact format:
{
  "score": <int 1-5>,
  "rationale": "<one sentence citing specific evidence>",
  "evidence": ["<evidence item 1>", "<evidence item 2>"],
  "gaps": ["<gap 1>", "<gap 2>"]
}
Do not add any text outside the JSON block when scoring.
"""


# ---------------------------------------------------------------------------
# Opening questions per dimension (broad, non-leading)
# ---------------------------------------------------------------------------

OPENING_QUESTIONS: dict[DimensionID, str] = {
    DimensionID.STRATEGY: (
        "Let's start with strategy. Can you describe how your organisation "
        "currently thinks about AI — is there a defined direction or roadmap, "
        "and who owns it?"
    ),
    DimensionID.DATA: (
        "Moving to data and infrastructure — how would you describe the state "
        "of your data assets today? Things like accessibility, quality, and "
        "readiness for AI workloads."
    ),
    DimensionID.TALENT: (
        "Let's talk about people. What does your current AI and data capability "
        "look like in terms of skills and team structure?"
    ),
    DimensionID.GOVERNANCE: (
        "On the topic of governance — how does your organisation manage risk "
        "and accountability around AI systems, including things like ethics, "
        "compliance, and model oversight?"
    ),
    DimensionID.USE_CASES: (
        "I'd like to understand your AI use case portfolio. Can you walk me "
        "through the AI initiatives you have in flight — from early experiments "
        "through to production?"
    ),
    DimensionID.TECHNOLOGY: (
        "Finally, let's cover tooling and technology. What platforms or "
        "infrastructure does your team use to build, deploy, and monitor "
        "AI/ML models?"
    ),
}


# ---------------------------------------------------------------------------
# Probe question banks per dimension
# (Agent selects adaptively based on the conversation — not asked verbatim)
# ---------------------------------------------------------------------------

PROBE_BANKS: dict[DimensionID, list[str]] = {
    DimensionID.STRATEGY: [
        "Who sponsors AI at the executive level, and how actively are they involved?",
        "Is AI investment tracked as a separate budget line, or embedded in other programs?",
        "How does your AI roadmap connect to specific business outcomes?",
        "Has the strategy been communicated to teams beyond data and technology?",
        "How often is the AI strategy reviewed or updated?",
    ],
    DimensionID.DATA: [
        "How do teams currently access data for AI projects — self-serve, or through requests?",
        "What does your data quality management process look like in practice?",
        "Do you have a centralised feature store or shared ML data layer?",
        "How mature is your data governance — cataloguing, lineage, ownership?",
        "What's the biggest data bottleneck when starting a new AI project?",
    ],
    DimensionID.TALENT: [
        "How many people work in data science or ML engineering roles currently?",
        "Is AI literacy a formal goal for non-technical staff?",
        "How do you attract and retain AI talent given market competition?",
        "Do you have internal upskilling or reskilling programs for AI?",
        "Who makes the call on AI project prioritisation — technical leads or the business?",
    ],
    DimensionID.GOVERNANCE: [
        "Do you have a published AI ethics or responsible AI policy?",
        "How are model decisions explained to regulators or affected users?",
        "What happens when a model behaves unexpectedly in production?",
        "Is there a formal model risk management process, similar to financial risk?",
        "How do you handle regulatory requirements like GDPR or sector-specific AI rules?",
    ],
    DimensionID.USE_CASES: [
        "Of the AI initiatives you mentioned, how many are in production vs still in POC?",
        "Can you share a specific example where AI delivered measurable business value?",
        "What does your typical journey from AI idea to production look like — time and steps?",
        "Are there use cases that failed or were discontinued? What happened?",
        "How do business units initiate AI projects — do they come to you, or is it top-down?",
    ],
    DimensionID.TECHNOLOGY: [
        "Do you use a managed ML platform (e.g. SageMaker, Vertex, Databricks ML) or custom infrastructure?",
        "How are models deployed and versioned — is there a standard process?",
        "What monitoring is in place for models in production — drift, performance, fairness?",
        "How close is your ML pipeline to a proper CI/CD workflow?",
        "Are your AI tools integrated with your data platform, or are they separate stacks?",
    ],
}


# ---------------------------------------------------------------------------
# Transition messages
# ---------------------------------------------------------------------------

DIMENSION_TRANSITION = (
    "Thank you — that's helpful context. Let's move on to {next_dimension}."
)

CLOSING_MESSAGE = """\
That covers all six dimensions. Thank you for your time and candour — \
this gives us a solid foundation for the assessment.

I'll now compile your results into a maturity report. You can expect it \
in your assessments folder shortly.
"""


# ---------------------------------------------------------------------------
# System prompt builder — called fresh every turn
# ---------------------------------------------------------------------------

def build_system_prompt(session: AssessmentSession, mode: str = "interview") -> str:
    """
    Builds the full system prompt for the current turn.

    mode:
      "interview"  — normal conversational interviewing
      "scoring"    — instruct Claude to output a JSON score block
      "report"     — instruct Claude to write the full Markdown report
    """
    parts = [PERSONA, "---", f"SESSION STATE:\n{session.context_summary()}"]

    if session.current_dimension:
        dim = session.dimensions[session.current_dimension]
        probes = "\n".join(f"- {p}" for p in PROBE_BANKS[session.current_dimension])
        parts.append(
            f"\nCURRENT DIMENSION: {dim.label}\n"
            f"Turns in this dimension: {len(dim.transcript)}\n"
            f"Available probes (pick adaptively, do not ask all):\n{probes}"
        )

    if mode == "scoring":
        parts.append("---\n" + SCORING_INSTRUCTION)
    elif mode == "report":
        parts.append(
            "---\nYou are now generating the final Markdown report. "
            "Follow the report structure defined in CLAUDE.md exactly. "
            "Use only evidence from the session. Do not add recommendations "
            "that are not grounded in the interview content."
        )

    return "\n\n".join(parts)
