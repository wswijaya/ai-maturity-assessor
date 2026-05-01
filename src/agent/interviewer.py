"""
Conversational interview loop for the AI Maturity Assessor.

Drives a single AssessmentSession through all 6 dimensions:
 - Opens each dimension with a scripted question (no API call needed).
 - Probes adaptively via the LLM until MIN_SCORING_TURNS interviewee responses.
 - Switches to scoring mode, parses the JSON score block, and closes the dimension.
 - Advances through all 6 dimensions, then marks the session complete.

I/O is fully injected (get_input / show_output) — this module has no CLI logic.
"""

from __future__ import annotations

from typing import Callable

from src.agent.prompts import (
    CLOSING_MESSAGE,
    DIMENSION_TRANSITION,
    OPENING_QUESTIONS,
    build_system_prompt,
)
from src.agent.scorer import score_dimension
from src.llm.base import LLMClient
from src.llm.factory import create_llm_client
from src.models.assessment import AssessmentSession

MIN_SCORING_TURNS = 4   # minimum interviewee turns before scoring is eligible
MAX_TURNS = 6           # hard cap — force scoring even if MIN hasn't been reached


class Interviewer:
    def __init__(
        self,
        session: AssessmentSession,
        client: LLMClient | None = None,
    ) -> None:
        self.session = session
        self.client = client or create_llm_client()
        # Cumulative messages list sent to the API on every turn.
        # Maintained across all dimensions so the LLM retains full context;
        # the system prompt compresses closed dimensions to keep it lean.
        self._messages: list[dict] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(
        self,
        get_input: Callable[[], str],
        show_output: Callable[[str], None],
    ) -> None:
        """Drive the full interview from first dimension to session completion."""
        session = self.session
        session.advance_dimension()

        while session.current_dimension is not None:
            self._run_dimension(get_input, show_output)
            next_dim = session.advance_dimension()
            if next_dim is not None:
                transition = DIMENSION_TRANSITION.format(
                    next_dimension=session.dimensions[next_dim].label
                )
                show_output(transition)

        session.close_session()
        show_output(CLOSING_MESSAGE)

    # ------------------------------------------------------------------
    # Private: per-dimension loop
    # ------------------------------------------------------------------

    def _run_dimension(
        self,
        get_input: Callable[[], str],
        show_output: Callable[[str], None],
    ) -> None:
        """Interview loop for one dimension until scoring completes."""
        session = self.session
        dim_id = session.current_dimension
        dim = session.dimensions[dim_id]

        # Use the scripted opening question — no API call, no latency hit.
        # A priming user message ensures the messages list opens with role=user.
        opening = OPENING_QUESTIONS[dim_id]
        session.add_to_transcript("agent", opening)
        self._messages.append(
            {"role": "user", "content": f"Please begin the {dim.label} section."}
        )
        self._messages.append({"role": "assistant", "content": opening})
        show_output(opening)

        while True:
            user_input = get_input().strip()
            if not user_input:
                continue

            session.add_to_transcript("interviewee", user_input)
            self._messages.append({"role": "user", "content": user_input})

            interviewee_turns = sum(
                1 for t in dim.transcript if t.role == "interviewee"
            )

            if interviewee_turns >= MIN_SCORING_TURNS or interviewee_turns >= MAX_TURNS:
                self._close_dimension()
                return

            probe = self._complete(mode="interview")
            session.add_to_transcript("agent", probe)
            self._messages.append({"role": "assistant", "content": probe})
            show_output(probe)

    # ------------------------------------------------------------------
    # Private: scoring
    # ------------------------------------------------------------------

    def _close_dimension(self) -> None:
        """Request a JSON score, parse it, and close the dimension."""
        dim = self.session.dimensions[self.session.current_dimension]
        system = build_system_prompt(self.session, mode="scoring")
        score_dimension(dim, self._messages, self.client, system)

    # ------------------------------------------------------------------
    # Private: LLM call
    # ------------------------------------------------------------------

    def _complete(self, mode: str = "interview") -> str:
        system = build_system_prompt(self.session, mode=mode)
        return self.client.complete(self._messages, system)
