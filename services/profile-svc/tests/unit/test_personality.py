"""
Tests: Personality quiz scoring → archetype assignment.
Run: pytest tests/unit/test_personality.py -q
"""

import pytest

from app.services.personality import ARCHETYPES, score_quiz


# Minimal question set for testing (same structure as seed data)
_QUESTIONS = [
    {
        "question_key": "work_pace",
        "options": [
            {"answer_key": "a", "weights": {"architect": 0.7, "connector": 0.3}},
            {"answer_key": "b", "weights": {"mystic": 0.6, "maverick": 0.4}},
            {"answer_key": "c", "weights": {"craftsperson": 0.7, "storyteller": 0.3}},
            {"answer_key": "d", "weights": {"connector": 0.8, "producer": 0.2}},
        ],
    },
    {
        "question_key": "feedback_style",
        "options": [
            {"answer_key": "a", "weights": {"architect": 0.5, "craftsperson": 0.5}},
            {"answer_key": "b", "weights": {"mystic": 0.6, "connector": 0.4}},
            {"answer_key": "c", "weights": {"maverick": 0.7, "producer": 0.3}},
            {"answer_key": "d", "weights": {"showrunner": 0.6, "producer": 0.4}},
        ],
    },
    {
        "question_key": "risk_appetite",
        "options": [
            {"answer_key": "a", "weights": {"craftsperson": 0.7, "architect": 0.3}},
            {"answer_key": "b", "weights": {"maverick": 0.8, "mystic": 0.2}},
            {"answer_key": "c", "weights": {"connector": 0.6, "storyteller": 0.4}},
            {"answer_key": "d", "weights": {"producer": 0.7, "showrunner": 0.3}},
        ],
    },
    {
        "question_key": "collab_role",
        "options": [
            {"answer_key": "a", "weights": {"architect": 0.5, "showrunner": 0.5}},
            {"answer_key": "b", "weights": {"connector": 0.8, "producer": 0.2}},
            {"answer_key": "c", "weights": {"maverick": 0.6, "mystic": 0.4}},
            {"answer_key": "d", "weights": {"craftsperson": 0.8, "storyteller": 0.2}},
        ],
    },
    {
        "question_key": "success_metric",
        "options": [
            {"answer_key": "a", "weights": {"craftsperson": 0.8, "architect": 0.2}},
            {"answer_key": "b", "weights": {"storyteller": 0.7, "mystic": 0.3}},
            {"answer_key": "c", "weights": {"producer": 0.6, "showrunner": 0.4}},
            {"answer_key": "d", "weights": {"maverick": 0.6, "mystic": 0.4}},
        ],
    },
    {
        "question_key": "energy_source",
        "options": [
            {"answer_key": "a", "weights": {"mystic": 0.7, "craftsperson": 0.3}},
            {"answer_key": "b", "weights": {"connector": 0.6, "showrunner": 0.4}},
            {"answer_key": "c", "weights": {"architect": 0.7, "producer": 0.3}},
            {"answer_key": "d", "weights": {"maverick": 0.6, "storyteller": 0.4}},
        ],
    },
]


class TestScoreQuiz:
    def test_all_architect_answers_yields_architect(self):
        answers = [
            {"question_key": "work_pace", "answer_key": "a"},      # architect 0.7
            {"question_key": "feedback_style", "answer_key": "a"},  # architect 0.5
            {"question_key": "risk_appetite", "answer_key": "a"},   # architect 0.3
            {"question_key": "collab_role", "answer_key": "a"},     # architect 0.5
            {"question_key": "success_metric", "answer_key": "a"},  # architect 0.2
            {"question_key": "energy_source", "answer_key": "c"},   # architect 0.7
        ]
        archetype, scores = score_quiz(answers, _QUESTIONS)
        assert archetype == "architect"
        assert scores["architect"] > scores["craftsperson"]

    def test_all_connector_yields_connector(self):
        answers = [
            {"question_key": "work_pace", "answer_key": "d"},      # connector 0.8
            {"question_key": "feedback_style", "answer_key": "b"},  # connector 0.4
            {"question_key": "risk_appetite", "answer_key": "c"},   # connector 0.6
            {"question_key": "collab_role", "answer_key": "b"},     # connector 0.8
            {"question_key": "success_metric", "answer_key": "c"},  # connector — not in this Q
            {"question_key": "energy_source", "answer_key": "b"},   # connector 0.6
        ]
        archetype, scores = score_quiz(answers, _QUESTIONS)
        assert archetype == "connector"

    def test_score_vector_has_all_archetypes(self):
        answers = [{"question_key": q["question_key"], "answer_key": "a"} for q in _QUESTIONS]
        archetype, scores = score_quiz(answers, _QUESTIONS)
        for a in ARCHETYPES:
            assert a in scores

    def test_winner_is_max_score(self):
        answers = [{"question_key": q["question_key"], "answer_key": "a"} for q in _QUESTIONS]
        archetype, scores = score_quiz(answers, _QUESTIONS)
        max_score = max(scores.values())
        assert scores[archetype] == max_score

    def test_unknown_answer_key_ignored(self):
        """Unknown answer key → no weights → score 0 for that question."""
        answers = [
            {"question_key": "work_pace", "answer_key": "z"},  # unknown
            *[{"question_key": q["question_key"], "answer_key": "a"} for q in _QUESTIONS[1:]],
        ]
        archetype, scores = score_quiz(answers, _QUESTIONS)
        assert archetype in ARCHETYPES  # still produces a result

    def test_empty_answers_produces_zero_scores(self):
        archetype, scores = score_quiz([], _QUESTIONS)
        assert all(v == 0.0 for v in scores.values())
        # With all zeros, winner is the tie-break first candidate
        assert archetype in ARCHETYPES
