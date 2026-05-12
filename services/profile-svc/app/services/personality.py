"""
profile-svc — Personality quiz scoring.

Scoring per plan §5.2:
  For each archetype A, score = Σ option_weight_for_A across answers.
  Archetype with highest score wins; ties broken by question order (work_pace first, collab_role second).
"""

from __future__ import annotations

from typing import Any

# Archetype keys per plan §5.3
ARCHETYPES = (
    "architect",
    "craftsperson",
    "mystic",
    "maverick",
    "connector",
    "storyteller",
    "producer",
    "showrunner",
)

# Tie-break: lower index wins
TIE_BREAK_QUESTIONS = ("work_pace", "collab_role")


def score_quiz(
    answers: list[dict[str, str]],
    questions: list[dict[str, Any]],
) -> tuple[str, dict[str, float]]:
    """
    Score quiz answers against question weights.

    Args:
        answers: list of {question_key, answer_key}
        questions: list of question dicts from DB ({question_key, options: [{answer_key, weights}]})

    Returns:
        (archetype_key, score_vector)
    """
    # Build lookup: question_key → {answer_key → {archetype → weight}}
    q_map: dict[str, dict[str, dict[str, float]]] = {}
    for q in questions:
        q_map[q["question_key"]] = {
            opt["answer_key"]: opt.get("weights", {})
            for opt in q.get("options", [])
        }

    scores: dict[str, float] = {a: 0.0 for a in ARCHETYPES}
    tie_break_scores: dict[str, dict[str, float]] = {}

    for ans in answers:
        qkey = ans["question_key"]
        akey = ans["answer_key"]
        weights = q_map.get(qkey, {}).get(akey, {})
        for archetype, w in weights.items():
            if archetype in scores:
                scores[archetype] = scores.get(archetype, 0.0) + w
        # Store per-tiebreak-question archetype scores
        if qkey in TIE_BREAK_QUESTIONS:
            tie_break_scores[qkey] = weights

    # Find winner with tie-breaking
    max_score = max(scores.values())
    candidates = [a for a, s in scores.items() if s == max_score]

    if len(candidates) == 1:
        winner = candidates[0]
    else:
        # Tie-break by work_pace weights
        winner = None
        for tb_q in TIE_BREAK_QUESTIONS:
            tb_weights = tie_break_scores.get(tb_q, {})
            best = max(
                (a for a in candidates if a in tb_weights),
                key=lambda a: tb_weights.get(a, 0.0),
                default=None,
            )
            if best:
                winner = best
                break
        if winner is None:
            winner = candidates[0]  # final fallback: alphabetical/first

    return winner, scores
