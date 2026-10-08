"""Score 32 dev rows twice with the released Open-Jev-2B head. No optimizer."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from toolret_smoke.checks import (
    has_score_spread,
    higher_score_sorts_earlier,
    max_abs_diff,
    scores_match,
)
from toolret_smoke.tools import render_tool


def candidate_content(query: str, instruction: str, tool_text: str) -> str:
    """Match jev.api.candidate_prompts for a string state, question, and option."""
    return (
        f"Context:\n{query}\n\nQuestion: {instruction}\n"
        f"Proposed answer: {tool_text}\nIs this proposed answer correct? Answer Yes or No."
    )


def _encoded_len(tokenizer, content: str) -> int:
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": content}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    return len(tokenizer(rendered, truncation=False)["input_ids"])


def _fits(tokenizer, query: str, instruction: str, tool_text: str, max_length: int) -> bool:
    return _encoded_len(tokenizer, candidate_content(query, instruction, tool_text)) <= max_length


def fit_tool_text(tokenizer, query: str, instruction: str, tool: dict, max_length: int) -> str:
    """Shrink description, then parameter names, and keep the tool."""
    description = tool.get("description") or ""
    params = list(tool.get("parameters") or [])

    def as_text(desc: str, names: list[str]) -> str:
        return render_tool({"name": tool.get("name") or "", "description": desc, "parameters": names})

    full = as_text(description, params)
    if _fits(tokenizer, query, instruction, full, max_length):
        return full
    lo, hi = 0, len(description)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = as_text(description[:mid], params)
        if _fits(tokenizer, query, instruction, candidate, max_length):
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    if best:
        return best
    names = list(params)
    while names:
        names = names[:-1]
        candidate = as_text("", names)
        if _fits(tokenizer, query, instruction, candidate, max_length):
            return candidate
    candidate = as_text("", [])
    if _fits(tokenizer, query, instruction, candidate, max_length):
        return candidate
    raise ValueError(f"tool {tool.get('name')!r} does not fit in max_length={max_length}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _forward(model, record: dict) -> list[float]:
    import torch

    with torch.inference_mode():
        values = model([record])[0]
    scores = [float(x) for x in values.detach().float().cpu().tolist()]
    if len(scores) != len(record["options"]):
        raise RuntimeError(
            f"expected {len(record['options'])} scalars, got {len(scores)} for {record['id']}"
        )
    return scores


def score_rows(model, rows: list[dict]) -> list[dict[str, Any]]:
    tokenizer = model.tokenizer
    max_length = int(model.max_length)
    reports = []
    for row in rows:
        query = row["query"]
        instruction = row["instruction"] or ""
        labeled = [("positive", tool) for tool in row["positives"]] + [
            ("negative", tool) for tool in row["negatives"]
        ]
        if len(labeled) < 2:
            raise RuntimeError(f"{row['id']} has fewer than 2 tools")
        options = [
            fit_tool_text(tokenizer, query, instruction, tool, max_length) for _, tool in labeled
        ]
        record = {
            "id": row["id"],
            "state": query,
            "kind": "choice",
            "question": instruction,
            "options": options,
        }
        first = _forward(model, record)
        second = _forward(model, record)
        diff = max_abs_diff(first, second)
        reports.append(
            {
                "id": row["id"],
                "n_tools": len(options),
                "n_positive": sum(1 for label, _ in labeled if label == "positive"),
                "n_negative": sum(1 for label, _ in labeled if label == "negative"),
                "labels": [label for label, _ in labeled],
                "scores": first,
                "second_scores": second,
                "max_abs_diff": diff,
                "matched": scores_match(first, second),
                "higher_sorts_earlier": higher_score_sorts_earlier(first),
                "spread": max(first) - min(first),
                "has_spread": has_score_spread(first),
            }
        )
    return reports


def summarize(reports: list[dict], checkpoint: Path, dtype: str, gpu_name: str, elapsed: float) -> dict:
    matched = all(row["matched"] for row in reports)
    ordered = all(row["higher_sorts_earlier"] for row in reports)
    spread = any(row["has_spread"] for row in reports)
    trainable = 0
    return {
        "status": "pass" if matched and ordered and spread else "fail",
        "job": "t4-scorer-smoke",
        "trained": False,
        "optimizer_steps": 0,
        "rows": len(reports),
        "tools_scored": sum(row["n_tools"] for row in reports),
        "two_runs_match": matched,
        "higher_score_sorts_earlier": ordered,
        "at_least_one_row_has_score_spread": spread,
        "max_abs_diff": max(row["max_abs_diff"] for row in reports),
        "dtype": dtype,
        "gpu": gpu_name,
        "elapsed_seconds": elapsed,
        "trainable_parameters_left_unfrozen": trainable,
        "checkpoint_sha256": {
            "model.json": file_sha256(checkpoint / "model.json"),
            "head.pt": file_sha256(checkpoint / "head.pt"),
            "adapter_config.json": file_sha256(checkpoint / "adapter" / "adapter_config.json"),
            "adapter_model.safetensors": file_sha256(
                checkpoint / "adapter" / "adapter_model.safetensors"
            ),
        },
        "per_row": reports,
    }
