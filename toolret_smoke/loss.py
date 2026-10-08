"""ToolRet per-target NLL. Other targets are left out of each softmax."""

from __future__ import annotations

import math


def toolret_nll(scores: list[float], n_positive: int) -> float:
    """Average NLL of each target against the negatives only."""
    if n_positive < 1:
        raise ValueError("a row needs at least one target")
    if n_positive > len(scores):
        raise ValueError("n_positive exceeds the candidate list")
    negatives = scores[n_positive:]
    if not negatives:
        return 0.0
    total = 0.0
    for target in scores[:n_positive]:
        logits = [target, *negatives]
        peak = max(logits)
        log_z = math.log(sum(math.exp(value - peak) for value in logits))
        total += -(target - peak - log_z)
    return total / n_positive


def toolret_nll_torch(scores, n_positive: int):
    """Same objective, differentiable. Positives occupy the leading positions."""
    import torch

    if n_positive < 1 or n_positive > scores.shape[0]:
        raise ValueError("n_positive is outside the candidate list")
    negatives = scores[n_positive:]
    if negatives.numel() == 0:
        return scores.sum() * 0.0
    positives = scores[:n_positive]
    logits = torch.cat(
        [positives.unsqueeze(1), negatives.unsqueeze(0).expand(n_positive, -1)],
        dim=1,
    )
    return -torch.log_softmax(logits, dim=1)[:, 0].mean()
