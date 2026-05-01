# AI Maturity Assessment Interviewer — Claude Code Instructions

## Project Purpose
A stateful CLI agent that conducts structured stakeholder interviews based on the
**Gartner AI Maturity Model**, scores responses across 6 dimensions, and produces
a Markdown narrative report. Phase 2 will add a web UI (FastAPI + React).

---

## Architecture Principles
- Keep `agent/`, `models/`, and `output/` strictly separated — the web layer in
  Phase 2 should be able to swap `cli.py` without touching any agent logic.
- All state flows through `AssessmentSession` (Pydantic). Never carry state in
  global variables or class-level mutables.
- Scoring must always be grounded in evidence extracted from the conversation.
  Never infer a score from silence or assumption.

---

## Gartner AI Maturity Model — Reference

### 5 Maturity Levels
| Level | Label | Characteristics |
|---|---|---|
| 1 | **Aware** | Ad hoc AI curiosity, no strategy, isolated experiments |
| 2 | **Active** | Pilots underway, exec interest but no governance, siloed |
| 3 | **Operational** | Repeatable processes, MLOps emerging, some ROI evidence |
| 4 | **Systematic** | Enterprise-wide AI strategy, governance in place, scaled use cases |
| 5 | **Transformational** | AI embedded in business model, continuous learning culture |

### 6 Assessment Dimensions
Each dimension is scored 1–5 independently, then averaged for an overall level.

| # | Dimension | Key Evidence to Probe |
|---|---|---|
| 1 | **Strategy & Vision** | AI roadmap existence, exec sponsorship, budget allocation, alignment to business goals |
| 2 | **Data & Infrastructure** | Data quality practices, lakehouse/warehouse maturity, feature store, data governance maturity |
| 3 | **Talent & Culture** | AI literacy across org, data science headcount, upskilling programs, change management readiness |
| 4 | **Governance & Risk** | AI ethics policy, model risk management, regulatory compliance framework, bias/explainability practices |
| 5 | **Use Case Portfolio** | Number of live use cases, stage distribution (POC/pilot/prod), value realised vs promised |
| 6 | **Technology & Tooling** | MLOps platform maturity, vendor landscape, CI/CD for models, monitoring in production |

---

## Interviewer Persona & Behaviour Rules

### Persona
You are a senior AI strategy consultant conducting a maturity assessment. Your
style is consultative, non-leading, and evidence-seeking. You are warm but
professionally rigorous.

### Hard Rules — Never Violate
1. **Never skip a dimension.** Complete all 6 before scoring.
2. **Never accept vague answers without probing.** Push for concrete examples,
   timelines, team sizes, or outcomes.
3. **Never score without evidence.** Every score must cite at least one specific
   thing the interviewee said.
4. **Never lead the witness.** Do not suggest answers or frame questions with
   desirable outcomes (e.g., "Do you have a *mature* data governance process?").
5. **Never hallucinate organisational context.** Only use what the interviewee
   has stated in the session.
6. **Graceful handling of "I don't know".** Score conservatively (level 1–2) and
   note the gap explicitly in the report.

### Adaptive Questioning
- Start each dimension with a **broad open question**.
- Follow up with **2–3 targeted probes** based on the answer.
- If an answer suggests higher maturity than expected, probe for evidence of
  sustainability and scale (not just one-off wins).
- If an answer suggests lower maturity, probe for intent and roadmap awareness.

---

## State Schema (see `src/models/assessment.py`)
The `AssessmentSession` model must always be the single source of truth:
- Org context (name, industry, interviewee role)
- Per-dimension: raw transcript, extracted evidence, score (1–5), rationale
- Overall maturity level (derived, not set directly)
- Session metadata (start time, completion status)

---

## Output Contract — Markdown Report
The report (`assessments/<org>_<date>.md`) must follow this structure exactly:

```
# AI Maturity Assessment Report
## Organisation: <name>
## Date: <date>
## Conducted by: AI Maturity Assessment Agent

---

## Executive Summary
[2–3 paragraph narrative. Overall level, top strengths, top gaps.]

## Overall Maturity Level: <1–5> — <Label>

---

## Dimension Scores

### 1. Strategy & Vision — Score: X/5
**Evidence:** [direct quotes or paraphrased statements from interview]
**Assessment:** [1–2 sentence narrative]
**Gaps:** [specific gaps identified]

[... repeat for all 6 dimensions ...]

---

## Key Recommendations
[3–5 prioritised, actionable recommendations with rationale]

## Next Steps
[Suggested 30/60/90-day actions]
```

---

## Development Conventions
- Python 3.11+
- Use `anthropic` SDK (not raw HTTP)
- Pydantic v2 for all models
- `rich` library for CLI formatting
- Tests go in `tests/` — at minimum test scoring logic and report generation
- Run with: `python src/cli.py`
- Generated reports: `assessments/` directory

---

## Known Risks & Mitigations
| Risk | Mitigation |
|---|---|
| Context drift on long interviews | Compress dimension transcripts after each dimension closes |
| Score inflation from self-reporting | Always probe for concrete evidence; note unsubstantiated claims |
| Interviewee fatigue | Cap at ~30 min; allow `save & resume` in Phase 2 |
| Scope creep | Radar charts, PDF, multi-stakeholder — all Phase 2 |
