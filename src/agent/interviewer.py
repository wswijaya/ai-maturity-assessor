"""
Conversational interview loop for the AI Maturity Assessor.

Drives a single AssessmentSession through all 6 dimensions:
 - Opens each dimension with a scripted question (no API call needed).
 - Probes adaptively via Claude until MIN_SCORING_TURNS interviewee responses.
 - Switches to scoring mode, parses the JSON score block, and closes the dimension.
 - Advances through all 6 dimensions, then marks the session complete.

I/O is fully injected (get_input / show_output) — this module has no CLI logic.
"""

from __future__ import annotations

from typing import Callable

import anthropic

from src.agent.prompts import (
    CLOSING_MESSAGE,
    DIMENSION_TRANSITION,
    OPENING_QUESTIONS,
    build_system_prompt,
)
from src.agent.scorer import score_dimension
from src.models.assessment import AssessmentSession

MIN_SCORING_TURNS = 4   # minimum interviewee turns before scoring is eligible
MAX_TURNS = 6           # hard cap — force scoring even if MIN hasn't been reached
DEFAULT_MODEL = "claude-opus-4-7"


class Interviewer:
    def __init__(
        self,
        session: AssessmentSession,
        client: anthropic.Anthropic | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.session = session
        self.client = client or anthropic.Anthropic()
        self.model = model
        # Cumulative messages list sent to the API on every turn.
        # Maintained across all dimensions so Claude retains full context;
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

            probe = self._call_claude(mode="interview")
            session.add_to_transcript("agent", probe)
            self._messages.append({"role": "assistant", "content": probe})
            show_output(probe)

    # ------------------------------------------------------------------
    # Private: scoring
    # ------------------------------------------------------------------

    def _close_dimension(self) -> None:
        """Request a JSON score from Claude, parse it, and close the dimension."""
        dim = self.session.dimensions[self.session.current_dimension]
        system = build_system_prompt(self.session, mode="scoring")
        score_dimension(dim, self._messages, self.client, self.model, system)

    # ------------------------------------------------------------------
    # Private: API call
    # ------------------------------------------------------------------

    def _call_claude(self, mode: str = "interview") -> str:
        """Call Claude with the current session state. Caches the static PERSONA block."""
        system_text = build_system_prompt(self.session, mode=mode)

        # Split the prompt at the first "---" separator so the static PERSONA
        # block is cached across all turns while the session-state block is not.
        separator = "\n\n---\n\n"
        split_idx = system_text.find(separator)
        if split_idx > 0:
            system: list[dict] | str = [
                {
                    "type": "text",
                    "text": system_text[:split_idx],
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": system_text[split_idx + len(separator):],
                },
            ]
        else:
            system = system_text

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=self._messages,
        )
        return response.content[0].text


