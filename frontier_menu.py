"""Menus, tool-call parsing, and transcripts for the frontier loop. No GPU."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from frontier_budget import ARM_ORDER, CORE_ARMS

K = 10
ARM_LABELS = {
    "full": "full menu",
    "bm25": "keyword search",
    "original": "original Open-Jev-2B top 10",
    "tuned": "tuned 2B top 10",
    "hosted": "hosted Jev top 10",
}
MENU_SIZE = 50
MAX_MODEL_LEN = 8192
PROMPT_TOKEN_BUDGET = 5200
SYSTEM_PROMPT = (
    "You are a tool-calling assistant. "
    "Call exactly one tool from the menu. "
    "Do not answer in prose."
)
_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")
_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_NAME_FIELD_RE = re.compile(r'"name"\s*:\s*"([^"\\]+)"')


def load_dev_ids(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def select_rows(rows: list[dict], dev_ids: set[str], n: int, seed: int = 0) -> list[dict]:
    """Dev rows only. The official ToolRet test split is not in this file."""
    pool = []
    for row in rows:
        if row.get("id") not in dev_ids:
            continue
        if int(row.get("n_positive") or 0) < 1:
            continue
        if len(row.get("candidates") or []) != MENU_SIZE:
            continue
        if len(row.get("query") or "") < 15:
            continue
        pool.append(row)
    order = list(range(len(pool)))
    random.Random(seed).shuffle(order)
    chosen = [pool[index] for index in order[: int(n)]]
    if len(chosen) < int(n):
        raise RuntimeError(f"only {len(chosen)} dev rows passed the menu checks; wanted {n}")
    return chosen


def bm25_top(candidates: list[dict], k: int = K) -> list[dict]:
    ranked = sorted(
        enumerate(candidates),
        key=lambda pair: (
            pair[1].get("bm25_rank") is None,
            pair[1]["bm25_rank"] if pair[1].get("bm25_rank") is not None else 10**9,
            pair[0],
        ),
    )
    return [candidates[index] for index, _tool in ranked[:k]]


def rank_by_score(candidates: list[dict], scores: list[float], k: int = K) -> list[dict]:
    if len(scores) != len(candidates):
        raise ValueError("scores and candidates differ in length")
    order = sorted(range(len(candidates)), key=lambda index: (-float(scores[index]), index))
    return [candidates[index] for index in order[:k]]


def sanitize_tool_name(name: str, index: int, used: set[str]) -> str:
    base = _NAME_RE.sub("_", name or "").strip("_")
    if not base or not base[0].isalpha():
        base = f"tool_{index}"
    base = base[:48]
    candidate = base
    n = 2
    while candidate in used:
        suffix = f"_{n}"
        candidate = (base[: 64 - len(suffix)] + suffix)[:64]
        n += 1
    used.add(candidate)
    return candidate


def assign_call_names(candidates: list[dict]) -> list[dict]:
    used: set[str] = set()
    named = []
    for index, tool in enumerate(candidates):
        item = dict(tool)
        item["call_name"] = sanitize_tool_name(str(tool.get("name") or ""), index, used)
        item["menu_index"] = index
        named.append(item)
    return named


def _parameter_properties(parameters: list) -> dict[str, dict]:
    properties = {}
    for raw in parameters or []:
        name = str(raw).strip()
        if not name or name in properties:
            continue
        properties[name] = {"type": "string"}
    return properties


def openai_tool(tool: dict, description_chars: int) -> dict:
    description = (tool.get("description") or "").strip()
    if description_chars >= 0:
        description = description[:description_chars]
    if not description:
        description = "No description."
    return {
        "type": "function",
        "function": {
            "name": tool["call_name"],
            "description": description,
            "parameters": {
                "type": "object",
                "properties": _parameter_properties(tool.get("parameters") or []),
            },
        },
    }


def render_prompt(tokenizer, query: str, tools: list[dict]) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Call exactly one tool that best fulfills this request.\n\n" + query,
        },
    ]
    return tokenizer.apply_chat_template(
        messages,
        tools=tools,
        add_generation_prompt=True,
        tokenize=False,
    )


def _token_len(tokenizer, text: str) -> int:
    return len(tokenizer(text, add_special_tokens=False)["input_ids"])


def fit_tools(tokenizer, query: str, menu: list[dict], token_budget: int = PROMPT_TOKEN_BUDGET) -> tuple[list[dict], str, int]:
    """Shrink descriptions until the chat prompt fits the token budget."""
    lo, hi = 0, 800
    best_tools = [openai_tool(tool, 0) for tool in menu]
    best_prompt = render_prompt(tokenizer, query, best_tools)
    best_len = _token_len(tokenizer, best_prompt)
    if best_len <= token_budget:
        # Grow is unnecessary; 800 is the cap we are willing to show.
        capped = [openai_tool(tool, 800) for tool in menu]
        prompt = render_prompt(tokenizer, query, capped)
        length = _token_len(tokenizer, prompt)
        if length <= token_budget:
            return capped, prompt, length
    while lo <= hi:
        mid = (lo + hi) // 2
        tools = [openai_tool(tool, mid) for tool in menu]
        prompt = render_prompt(tokenizer, query, tools)
        length = _token_len(tokenizer, prompt)
        if length <= token_budget:
            best_tools, best_prompt, best_len = tools, prompt, length
            lo = mid + 1
        else:
            hi = mid - 1
    if best_len > token_budget:
        raise RuntimeError(f"prompt is {best_len} tokens with empty descriptions; budget is {token_budget}")
    return best_tools, best_prompt, best_len


def arm_menus(
    named: list[dict],
    original_scores: list[float],
    tuned_scores: list[float],
    hosted: list[dict] | None = None,
) -> dict[str, list[dict]]:
    menus = {
        "full": list(named),
        "bm25": bm25_top(named, K),
        "original": rank_by_score(named, original_scores, K),
        "tuned": rank_by_score(named, tuned_scores, K),
    }
    if hosted:
        menus["hosted"] = list(hosted)
    return menus


def core_done(query: dict) -> bool:
    arms = query.get("arms") or {}
    return all(isinstance(arms.get(arm), dict) and "called" in arms[arm] for arm in CORE_ARMS)


def has_arm(query: dict, arm: str) -> bool:
    item = (query.get("arms") or {}).get(arm)
    return isinstance(item, dict) and "called" in item


def merge_queries(previous: list[dict], extra: list[dict]) -> list[dict]:
    """Keep finished arms. Extra results fill gaps and append new ids."""
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for query in previous:
        by_id[query["id"]] = {"id": query["id"], "query": query.get("query") or "", "arms": dict(query.get("arms") or {})}
        order.append(query["id"])
    for query in extra:
        if query["id"] not in by_id:
            by_id[query["id"]] = {"id": query["id"], "query": query.get("query") or "", "arms": {}}
            order.append(query["id"])
        dest = by_id[query["id"]]
        if query.get("query") and not dest.get("query"):
            dest["query"] = query["query"]
        for arm, item in (query.get("arms") or {}).items():
            if arm not in dest["arms"] and isinstance(item, dict) and "called" in item:
                dest["arms"][arm] = item
    return [by_id[row_id] for row_id in order]


def build_prompts(
    tokenizer,
    rows: list[dict],
    scores_by_id: dict[str, dict[str, list[float]]],
    hosted_menus: dict[str, list[dict]] | None = None,
    arms_for: dict[str, tuple[str, ...]] | None = None,
) -> list[dict]:
    prompts = []
    hosted_menus = hosted_menus or {}
    for row in rows:
        named = assign_call_names(row["candidates"])
        wanted = arms_for[row["id"]] if arms_for and row["id"] in arms_for else ARM_ORDER
        scored = scores_by_id.get(row["id"]) or {}
        if any(arm in wanted for arm in ("original", "tuned")):
            menus = arm_menus(named, scored["original"], scored["tuned"], hosted_menus.get(row["id"]))
        else:
            menus = {
                "full": list(named),
                "bm25": bm25_top(named, K),
                "hosted": list(hosted_menus.get(row["id"]) or []),
            }
        for arm in wanted:
            if arm not in menus:
                continue
            menu = menus[arm]
            tools, prompt, length = fit_tools(tokenizer, row["query"], menu)
            prompts.append(
                {
                    "id": row["id"],
                    "arm": arm,
                    "query": row["query"],
                    "prompt": prompt,
                    "prompt_tokens": length,
                    "valid_names": [tool["call_name"] for tool in menu],
                    "shown": [
                        {"call_name": tool["call_name"], "name": tool.get("name") or "", "corpus_id": tool.get("corpus_id")}
                        for tool in menu
                    ],
                }
            )
    return prompts


def extract_called_tools(text: str) -> list[str]:
    """Pull tool names from Qwen-style tool-call markup or a bare JSON object."""
    found: list[str] = []
    blobs = _TOOL_CALL_RE.findall(text or "")
    if not blobs:
        stripped = (text or "").strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            blobs = [stripped]
    for blob in blobs:
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and obj.get("name"):
            found.append(str(obj["name"]))
            continue
        match = _NAME_FIELD_RE.search(blob)
        if match:
            found.append(match.group(1))
    return found


def first_tool(calls: list[str]) -> str | None:
    return calls[0] if calls else None


def calls_match(truth: list[str], predicted: list[str]) -> bool:
    return first_tool(truth) == first_tool(predicted)


def arm_accuracy(queries: list[dict], arm: str) -> float:
    rows = [query for query in queries if arm in (query.get("arms") or {}) and "full" in query["arms"]]
    if not rows:
        return 0.0
    hits = 0
    for query in rows:
        truth = query["arms"]["full"]["called"]
        hits += int(calls_match(truth, query["arms"][arm]["called"]))
    return hits / len(rows)


def transcript_arms(queries: list[dict]) -> list[str]:
    ordered = (*ARM_ORDER, "hosted")
    return [arm for arm in ordered if any(arm in (query.get("arms") or {}) for query in queries)]


def render_transcripts(queries: list[dict], model_id: str, revision: str) -> str:
    lines = [
        "# Frontier tool-call transcripts",
        "",
        f"Model `{model_id}` at `{revision}`.",
        "Ground truth is the tool called on the full menu. Each filtered arm sees the same query and a 10-tool slice of that menu.",
        "",
    ]
    for query in queries:
        lines.append(f"## {query['id']}")
        lines.append("")
        lines.append(query.get("query") or "")
        lines.append("")
        lines.append("| Arm | Tools shown | Called | Matched full menu | Seconds |")
        lines.append("| --- | ---: | --- | --- | ---: |")
        truth = query["arms"]["full"]["called"]
        for arm in ARM_ORDER:
            if arm not in query["arms"]:
                continue
            item = query["arms"][arm]
            called = ", ".join(item["called"]) if item["called"] else "(none)"
            matched = "yes" if calls_match(truth, item["called"]) else "no"
            lines.append(
                f"| {ARM_LABELS.get(arm, arm)} | {item.get('n_shown', '')} | {called} | {matched} | {item.get('seconds', 0):.2f} |"
            )
        lines.append("")
        for arm in ARM_ORDER:
            if arm not in query["arms"]:
                continue
            item = query["arms"][arm]
            names = ", ".join(tool["call_name"] for tool in item.get("shown") or [])
            lines.append(f"### {ARM_LABELS.get(arm, arm)}")
            lines.append("")
            lines.append(f"Menu: {names}")
            lines.append("")
            lines.append("```")
            lines.append((item.get("output") or "").rstrip())
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
