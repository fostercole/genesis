"""Score a fixed candidate list with one Open-Jev forward pass per chunk.

Candidates are independent, so splitting a row into chunks does not change a score.
The smoke's two-run check is not repeated here.
"""

from __future__ import annotations

from typing import Any

from toolret_smoke.dev_eval import aggregate_metrics, positive_ranks
from toolret_smoke.score_rows import _encoded_len, _forward, candidate_content, fit_tool_text

SCORE_TOKEN_BUDGET = 8192
SCORE_MAX_ITEMS = 16


def pack_chunks(lengths: list[int], budget: int = SCORE_TOKEN_BUDGET, max_items: int = SCORE_MAX_ITEMS) -> list[list[int]]:
    """Group candidate indexes so the padded token count stays near the budget."""
    chunks: list[list[int]] = []
    current: list[int] = []
    for index, length in enumerate(lengths):
        if not current:
            current = [index]
            continue
        proposed = max(lengths[i] for i in current + [index]) * (len(current) + 1)
        if proposed > budget or len(current) >= max_items:
            chunks.append(current)
            current = [index]
        else:
            current.append(index)
    if current:
        chunks.append(current)
    return chunks


def fit_row(tokenizer, row: dict, max_length: int) -> tuple[list[str], list[int]]:
    query = row["query"]
    instruction = row["instruction"] or ""
    options = []
    lengths = []
    for tool in row["candidates"]:
        text = fit_tool_text(tokenizer, query, instruction, tool, max_length)
        options.append(text)
        lengths.append(_encoded_len(tokenizer, candidate_content(query, instruction, text)))
    return options, lengths


def score_fitted(model, row: dict, options: list[str], lengths: list[int]) -> list[float]:
    if len(options) != len(row["candidates"]):
        raise RuntimeError(f"{row['id']} fitted {len(options)} tools for {len(row['candidates'])} candidates")
    scores = [0.0] * len(options)
    for indexes in pack_chunks(lengths):
        record = {
            "id": row["id"],
            "state": row["query"],
            "kind": "choice",
            "question": row["instruction"] or "",
            "options": [options[index] for index in indexes],
        }
        part = _forward(model, record)
        for index, score in zip(indexes, part):
            scores[index] = score
    return scores


def ranks_for_row(row: dict, scores: list[float]) -> dict[str, Any]:
    relevant = [bool(tool["relevant"]) for tool in row["candidates"]]
    if sum(relevant) + int(row["n_positive_outside"]) != int(row["n_positive"]):
        raise RuntimeError(
            f"{row['id']} relevant flags {sum(relevant)} plus outside {row['n_positive_outside']} "
            f"do not equal {row['n_positive']} positives"
        )
    return {
        "id": row["id"],
        "n_positive": int(row["n_positive"]),
        "ranks": positive_ranks(scores, relevant, int(row["n_positive"])),
    }


def summarize_model(per_row: list[dict]) -> dict[str, Any]:
    return {
        "rows": len(per_row),
        "metrics": aggregate_metrics(per_row),
        "per_row": [{"id": row["id"], "n_positive": row["n_positive"], "ranks": row["ranks"]} for row in per_row],
    }
