"""
Scoring module for the AI Maturity Assessment.

Public surface:
  parse_score_json(raw)      — strip fences, parse JSON, validate schema, return dict.
  score_dimension(dim, ...)  — call the Anthropic SDK in scoring mode, with one retry
                               on malformed JSON, then close the dimension.
"""

from __future__ import annotations

import json
import re

import anthropic

from src.models.assessment import DimensionAssessment

DEFAULT_MODEL = "claude-opus-4-7"


def parse_score_json(raw: str) -> dict:
    """
    Strip markdown fences, parse JSON, and validate the scoring schema.

    Raises:
      json.JSONDecodeError  — raw text is not parseable JSON (caller may retry).
      ValueError            — JSON is valid but fails schema/range/content checks
                              (retrying with the same prompt will not help).

    Score coercion: accepts int, float (3.0), or numeric string ("3").
    Returns a validated dict: score (int 1–5), rationale (str),
    evidence (list[str]), gaps (list[str]).
    """
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    # Let json.JSONDecodeError propagate — caller decides whether to retry.
    data = json.loads(clean)

    if not isinstance(data, dict):
        raise ValueError("Parsed JSON is not an object.")

    for key in ("score", "rationale", "evidence"):
        if key not in data:
            raise ValueError(f"Missing required key: '{key}'")

    # Score: coerce from float or numeric string, then range-check.
    raw_score = data["score"]
    try:
        score = int(float(raw_score))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Score is not a number: {raw_score!r}") from exc

    if not (1 <= score <= 5):
        raise ValueError(f"Score {score} is out of range 1–5.")
    data["score"] = score

    # Rationale: must be a non-empty, non-whitespace string.
    rationale = data.get("rationale", "")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("Rationale must be a non-empty string.")

    # Evidence: must contain at least one non-whitespace string.
    evidence = data["evidence"]
    if not isinstance(evidence, list):
        raise ValueError("Evidence must be a list.")
    meaningful = [e for e in evidence if isinstance(e, str) and e.strip()]
    if not meaningful:
        raise ValueError(
            "Evidence list must contain at least one non-empty string."
        )
    data["evidence"] = meaningful

    if "gaps" not in data:
        data["gaps"] = []

    return data


def score_dimension(
    dim: DimensionAssessment,
    messages: list[dict],
    client: anthropic.Anthropic,
    model: str,
    system: str | list[dict],
) -> None:
    """
    Drive the scoring exchange for a single dimension.

    Sends the scoring cue, calls the Anthropic SDK with the accumulated
    conversation, and parses the JSON score block.

    Retry policy:
      - json.JSONDecodeError (malformed response)  → retry once.
      - ValueError (valid JSON but invalid content) → raise immediately.
      A second JSONDecodeError after retry is re-raised as ValueError.

    On success, calls dim.close() with validated values.
    Mutates messages in place.
    """
    scoring_cue = (
        f"Thank you — that covers the {dim.label} dimension. "
        "Please now output your scoring JSON as instructed."
    )
    messages.append({"role": "user", "content": scoring_cue})

    raw = _call_api(client, model, system, messages)
    messages.append({"role": "assistant", "content": raw})

    try:
        score_data = parse_score_json(raw)
    except json.JSONDecodeError:
        retry_cue = (
            "Your response was not valid JSON. "
            "Respond with ONLY the JSON score block — no other text."
        )
        messages.append({"role": "user", "content": retry_cue})
        raw = _call_api(client, model, system, messages)
        messages.append({"role": "assistant", "content": raw})
        try:
            score_data = parse_score_json(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Score JSON still malformed after retry for '{dim.label}'."
            ) from exc

    dim.close(
        score=score_data["score"],
        rationale=score_data["rationale"],
        gaps=score_data.get("gaps", []),
        evidence=score_data["evidence"],
    )


def _call_api(
    client: anthropic.Anthropic,
    model: str,
    system: str | list[dict],
    messages: list[dict],
) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    return response.content[0].text
