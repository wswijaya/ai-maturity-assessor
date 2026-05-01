"""
Assessment state models — single source of truth for the entire session.
All agent logic reads from and writes to AssessmentSession exclusively.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MaturityLevel(int, Enum):
    AWARE = 1
    ACTIVE = 2
    OPERATIONAL = 3
    SYSTEMATIC = 4
    TRANSFORMATIONAL = 5

    def label(self) -> str:
        return {
            1: "Aware",
            2: "Active",
            3: "Operational",
            4: "Systematic",
            5: "Transformational",
        }[self.value]

    def description(self) -> str:
        return {
            1: "Ad hoc AI curiosity, no strategy, isolated experiments.",
            2: "Pilots underway, exec interest but no governance, siloed.",
            3: "Repeatable processes, MLOps emerging, some ROI evidence.",
            4: "Enterprise-wide AI strategy, governance in place, scaled use cases.",
            5: "AI embedded in business model, continuous learning culture.",
        }[self.value]


class DimensionID(str, Enum):
    STRATEGY = "strategy_vision"
    DATA = "data_infrastructure"
    TALENT = "talent_culture"
    GOVERNANCE = "governance_risk"
    USE_CASES = "use_case_portfolio"
    TECHNOLOGY = "technology_tooling"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class ConversationTurn(BaseModel):
    role: str                      # "agent" | "interviewee"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DimensionAssessment(BaseModel):
    dimension_id: DimensionID
    label: str
    transcript: list[ConversationTurn] = Field(default_factory=list)
    evidence: list[str] = Field(
        default_factory=list,
        description="Concrete evidence extracted from interviewee statements.",
    )
    score: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Score 1–5. Must not be set until dimension is complete.",
    )
    score_rationale: Optional[str] = Field(
        default=None,
        description="Why this score was assigned. Must cite evidence.",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="Specific gaps or weaknesses identified.",
    )
    is_complete: bool = False

    def add_turn(self, role: str, content: str) -> None:
        self.transcript.append(ConversationTurn(role=role, content=content))

    def close(self, score: int, rationale: str, gaps: list[str], evidence: list[str]) -> None:
        """Finalise a dimension. Validates score is evidence-backed."""
        if not evidence:
            raise ValueError(
                f"Cannot close dimension '{self.label}' without at least one evidence item."
            )
        self.score = score
        self.score_rationale = rationale
        self.gaps = gaps
        self.evidence = evidence
        self.is_complete = True


class OrgContext(BaseModel):
    org_name: str
    industry: str
    interviewee_name: str
    interviewee_role: str
    employee_count: Optional[str] = None   # e.g. "500–1000"
    additional_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Root session model
# ---------------------------------------------------------------------------

DIMENSION_METADATA: dict[DimensionID, str] = {
    DimensionID.STRATEGY:   "Strategy & Vision",
    DimensionID.DATA:       "Data & Infrastructure",
    DimensionID.TALENT:     "Talent & Culture",
    DimensionID.GOVERNANCE: "Governance & Risk",
    DimensionID.USE_CASES:  "Use Case Portfolio",
    DimensionID.TECHNOLOGY: "Technology & Tooling",
}


class AssessmentSession(BaseModel):
    session_id: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    is_complete: bool = False

    org_context: Optional[OrgContext] = None

    dimensions: dict[DimensionID, DimensionAssessment] = Field(
        default_factory=lambda: {
            dim_id: DimensionAssessment(
                dimension_id=dim_id,
                label=label,
            )
            for dim_id, label in DIMENSION_METADATA.items()
        }
    )

    current_dimension: Optional[DimensionID] = None

    # Flat conversation log for the full session (context sent to Claude)
    full_transcript: list[ConversationTurn] = Field(default_factory=list)

    # ---------------------------------------------------------------------------
    # Computed properties
    # ---------------------------------------------------------------------------

    @computed_field
    @property
    def completed_dimensions(self) -> list[DimensionID]:
        return [d for d, v in self.dimensions.items() if v.is_complete]

    @computed_field
    @property
    def remaining_dimensions(self) -> list[DimensionID]:
        return [d for d, v in self.dimensions.items() if not v.is_complete]

    @computed_field
    @property
    def overall_score(self) -> Optional[float]:
        scores = [v.score for v in self.dimensions.values() if v.score is not None]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 1)

    @computed_field
    @property
    def overall_level(self) -> Optional[MaturityLevel]:
        score = self.overall_score
        if score is None:
            return None
        return MaturityLevel(min(5, max(1, round(score))))

    @computed_field
    @property
    def dimension_order(self) -> list[DimensionID]:
        """Fixed interview order."""
        return list(DIMENSION_METADATA.keys())

    # ---------------------------------------------------------------------------
    # Mutation helpers
    # ---------------------------------------------------------------------------

    def add_to_transcript(self, role: str, content: str) -> None:
        turn = ConversationTurn(role=role, content=content)
        self.full_transcript.append(turn)
        if self.current_dimension:
            self.dimensions[self.current_dimension].transcript.append(turn)

    def advance_dimension(self) -> Optional[DimensionID]:
        """Move to the next incomplete dimension. Returns None if all done."""
        for dim_id in self.dimension_order:
            if not self.dimensions[dim_id].is_complete:
                self.current_dimension = dim_id
                return dim_id
        self.current_dimension = None
        return None

    def close_session(self) -> None:
        self.is_complete = True
        self.completed_at = datetime.utcnow()

    def context_summary(self) -> str:
        """
        Compressed context string injected into Claude's system prompt to
        reduce token usage on long sessions.
        """
        lines = []
        if self.org_context:
            ctx = self.org_context
            lines.append(
                f"Org: {ctx.org_name} | Industry: {ctx.industry} | "
                f"Interviewee: {ctx.interviewee_name} ({ctx.interviewee_role})"
            )
        for dim_id, dim in self.dimensions.items():
            if dim.is_complete:
                lines.append(
                    f"[CLOSED] {dim.label}: Score={dim.score}/5 | "
                    f"Evidence={'; '.join(dim.evidence[:2])}"
                )
            elif dim_id == self.current_dimension:
                lines.append(f"[ACTIVE] {dim.label}")
        return "\n".join(lines)
