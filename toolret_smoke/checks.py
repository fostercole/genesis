"""Pass/fail checks for the T4 scorer smoke. No model code."""

from __future__ import annotations


def scores_match(first: list[float], second: list[float], tol: float = 1e-4) -> bool:
    if not first or len(first) != len(second):
        return False
    return all(abs(a - b) <= tol for a, b in zip(first, second))


def max_abs_diff(first: list[float], second: list[float]) -> float:
    if len(first) != len(second) or not first:
        return float("inf")
    return max(abs(a - b) for a, b in zip(first, second))


def higher_score_sorts_earlier(scores: list[float]) -> bool:
    """A higher scalar must land at an earlier rank. Ties keep input order."""
    if len(scores) < 2:
        return False
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    for rank, index in enumerate(order):
        for later in order[rank + 1 :]:
            if scores[index] < scores[later]:
                return False
    ranked = [scores[i] for i in order]
    return all(ranked[i] >= ranked[i + 1] for i in range(len(ranked) - 1))


def has_score_spread(scores: list[float], tol: float = 1e-6) -> bool:
    if len(scores) < 2:
        return False
    return max(scores) - min(scores) > tol
