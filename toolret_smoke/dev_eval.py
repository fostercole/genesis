"""Dev-split candidate lists and the metrics that lock k. No GPU and no training."""

from __future__ import annotations

import math
from typing import Any

# Plan rates, Oct 8 2026: L4 GPU $0.80/hr, CPU $0.0000131/core/s, memory $0.00000222/GiB/s.
# A loaded L4 in the plan is 8 cores and 32 GiB, about $1.43 per hour.
L4_GPU_USD_PER_HOUR = 0.80
L4_CORES = 8
L4_MEMORY_GIB = 32
CPU_USD_PER_CORE_SECOND = 0.0000131
MEMORY_USD_PER_GIB_SECOND = 0.00000222
LOADED_L4_USD_PER_SEC = (
    (L4_GPU_USD_PER_HOUR / 3600)
    + (L4_CORES * CPU_USD_PER_CORE_SECOND)
    + (L4_MEMORY_GIB * MEMORY_USD_PER_GIB_SECOND)
)
DEV_ROWS = 2000
CANDIDATES = 50
CUTOFFS = (3, 5, 10)
# "Within a point" is one percentage point on a 0–100 completeness score.
WITHIN_ONE_POINT = 0.01
DEV_SCORE_CAP_USD = 10.0


def tool_identity(tool: dict[str, Any]) -> tuple:
    """Identity after truncation to name, description, and parameter names.

    A blank tool does not share an identity with other blank tools.
    """
    name = tool.get("name") or ""
    description = tool.get("description") or ""
    parameters = tuple(tool.get("parameters") or [])
    if name or description or parameters:
        return ("fields", name, description, parameters)
    raw = tool.get("raw") or tool.get("corpus_id") or ""
    return ("blank", raw)


def assemble_candidates(
    positives: list[dict[str, Any]],
    bm25_ranked: list[dict[str, Any]],
    k: int = CANDIDATES,
) -> dict[str, Any]:
    """Keep every positive, then fill from BM25 up to k.

    The plan says to take the BM25 top 50 and does not say whether a missed
    positive stays in the list. This is the silent-plan choice: every positive
    is kept, and the remaining slots are the BM25 hits that are not already
    positives. When that would pass k, the lowest BM25 non-positives are
    dropped. Positives that still do not fit are left outside the scored list
    and count as misses.
    """
    if k < 1:
        raise ValueError("k must be positive")
    golds: list[dict[str, Any]] = []
    gold_ids: list[tuple] = []
    seen_gold = set()
    for tool in positives:
        identity = tool_identity(tool)
        if identity in seen_gold:
            continue
        seen_gold.add(identity)
        golds.append(tool)
        gold_ids.append(identity)

    selected: list[dict[str, Any]] = []
    seen = set()
    taken_from_bm25 = set()
    for rank, tool in enumerate(bm25_ranked):
        if len(selected) >= k:
            break
        identity = tool_identity(tool)
        if identity in seen:
            continue
        seen.add(identity)
        taken_from_bm25.add(identity)
        selected.append(_candidate(tool, relevant=identity in seen_gold, bm25_rank=rank, injected=False))

    for tool, identity in zip(golds, gold_ids):
        if identity in seen:
            continue
        selected.append(_candidate(tool, relevant=True, bm25_rank=None, injected=True))
        seen.add(identity)

    while len(selected) > k:
        drop_at = next(
            (index for index in range(len(selected) - 1, -1, -1) if not selected[index]["relevant"]),
            None,
        )
        if drop_at is None:
            selected = selected[:k]
            break
        selected.pop(drop_at)

    present = {tool_identity(tool) for tool in selected if tool["relevant"]}
    return {
        "candidates": selected,
        "n_positive": len(golds),
        "n_positive_in_bm25": sum(1 for identity in gold_ids if identity in taken_from_bm25),
        "n_injected": sum(1 for tool in selected if tool["injected"]),
        "n_positive_outside": sum(1 for identity in gold_ids if identity not in present),
    }


def _candidate(tool: dict[str, Any], relevant: bool, bm25_rank: int | None, injected: bool) -> dict[str, Any]:
    return {
        "corpus_id": tool.get("corpus_id"),
        "name": tool.get("name") or "",
        "description": tool.get("description") or "",
        "parameters": list(tool.get("parameters") or []),
        "relevant": relevant,
        "bm25_rank": bm25_rank,
        "injected": injected,
    }


def positive_ranks(scores: list[float], relevant: list[bool], n_positive: int) -> list[int | None]:
    """1-based ranks of the gold tools. None means the gold is outside the list.

    Ties keep the candidate input order, the same rule as the scorer smoke.
    Each relevant flag is one gold that is in the list. Golds outside the list
    are the difference between n_positive and the number of relevant flags.
    """
    if len(scores) != len(relevant):
        raise ValueError("scores and relevant flags differ in length")
    if sum(relevant) > n_positive:
        raise ValueError("more relevant candidates than positives")
    order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
    ranks = [rank for rank, index in enumerate(order, start=1) if relevant[index]]
    ranks.extend([None] * (n_positive - len(ranks)))
    return ranks


def _dcg_at(ranks: list[int | None], k: int) -> float:
    total = 0.0
    for rank in ranks:
        if rank is not None and rank <= k:
            total += 1.0 / math.log2(rank + 1)
    return total


def _idcg(n_positive: int, k: int) -> float:
    return sum(1.0 / math.log2(rank + 1) for rank in range(1, min(k, n_positive) + 1))


def row_metrics(ranks: list[int | None], n_positive: int, ks: tuple[int, ...] = CUTOFFS) -> dict[str, float]:
    """nDCG@10, recall@k, and completeness@k. Macro inputs are one row.

    Recall@k is the fraction of that row's positives placed in the top k.
    Completeness@k is 1 when every positive is in the top k, else 0.
    nDCG@10 uses binary relevance. A positive with no rank is a miss.
    """
    if n_positive <= 0:
        raise ValueError("a dev row needs at least one positive")
    if len(ranks) != n_positive:
        raise ValueError("ranks must cover every positive")
    metrics = {
        "ndcg@10": _dcg_at(ranks, 10) / _idcg(n_positive, 10),
    }
    for k in ks:
        found = sum(1 for rank in ranks if rank is not None and rank <= k)
        metrics[f"recall@{k}"] = found / n_positive
        metrics[f"completeness@{k}"] = 1.0 if found == n_positive else 0.0
    return metrics


def aggregate_metrics(rows: list[dict[str, Any]], ks: tuple[int, ...] = CUTOFFS) -> dict[str, float]:
    """Unweighted mean over rows. One row, one vote, matching pytrec-style macro averages."""
    if not rows:
        raise ValueError("no rows to aggregate")
    keys = ["ndcg@10", *[f"recall@{k}" for k in ks], *[f"completeness@{k}" for k in ks]]
    totals = {key: 0.0 for key in keys}
    for row in rows:
        metrics = row_metrics(row["ranks"], row["n_positive"], ks)
        for key in keys:
            totals[key] += metrics[key]
    n = len(rows)
    return {key: totals[key] / n for key in keys}


def lock_k(completeness: dict[int, float], ks: tuple[int, ...] = CUTOFFS) -> dict[str, Any]:
    """Smallest k whose completeness is within one point of the best of ks."""
    best = max(completeness[k] for k in ks)
    locked = None
    for k in ks:
        if best - completeness[k] <= WITHIN_ONE_POINT + 1e-12:
            locked = k
            break
    if locked is None:
        raise RuntimeError("no cutoff was within a point of the best")
    return {
        "locked_k": locked,
        "best_completeness": best,
        "best_k": max(ks, key=lambda k: (completeness[k], -k)),
        "within_one_point": WITHIN_ONE_POINT,
        "compared": {str(k): completeness[k] for k in ks},
    }


def full_pass_estimate_usd(
    load_seconds: float,
    probe_score_seconds: float,
    probe_rows: int,
    full_rows: int = DEV_ROWS,
) -> float:
    """Dollars for loading both checkpoints once and scoring every dev row on a loaded L4."""
    if probe_rows <= 0 or full_rows <= 0:
        raise ValueError("row counts must be positive")
    if load_seconds < 0 or probe_score_seconds < 0:
        raise ValueError("timings must be non-negative")
    per_row = probe_score_seconds / probe_rows
    return (load_seconds + per_row * full_rows) * LOADED_L4_USD_PER_SEC
