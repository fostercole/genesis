"""Frontier menu comparison on one query at a time.

The full menu is the dev pass's 50-candidate pool. Keyword search is BM25
order inside that pool. The graph label for that arm is "keyword search".
Hosted Jev stays in the design and is paused while its API key is empty.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pi_loop import parse_env_text

TARGET_EXAMPLES = 90
POOL = 50
K = 10
STARTER_CREDIT_USD = 30.0
CREDIT_BUFFER_USD = 1.0
MIN_LAUNCH_USD = 2.0
# Planning rate Cole already has: H100 plus 8 cores and 32 GiB.
PLANNING_ALL_IN_USD_PER_HOUR = 4.58

RUNNING_ARMS = (
    "full_menu",
    "keyword_search",
    "original_open_jev_2b",
    "tuned_2b",
)
ARM_LABELS = {
    "full_menu": "full menu",
    "keyword_search": "keyword search",
    "original_open_jev_2b": "original Open-Jev-2B",
    "tuned_2b": "tuned 2B",
    "hosted_jev": "hosted Jev",
}
SYSTEM_PROMPT = (
    "Call the one tool that best fulfills the user request. "
    "Return one tool call and no other text."
)


def remaining_credit_usd(credits_applied_usd: float, billed_cost_usd: float, starter_usd: float = STARTER_CREDIT_USD) -> float:
    """Unused Starter compute. A positive billed cost means the grant is already gone."""
    if billed_cost_usd > 0:
        return 0.0
    return starter_usd - abs(credits_applied_usd)


def may_launch(remaining_usd: float) -> bool:
    return remaining_usd >= MIN_LAUNCH_USD


def would_cross_wall(spent_usd: float, next_usd: float, remaining_usd: float, buffer_usd: float = CREDIT_BUFFER_USD) -> bool:
    """True when the next call would enter the last dollar of remaining credit."""
    return spent_usd + next_usd > remaining_usd - buffer_usd


def all_in_usd_per_hour(gpu_usd_per_hour: float, cores: float, memory_gib: float, cpu_usd_per_hour: float, memory_usd_per_gib_hour: float) -> float:
    return gpu_usd_per_hour + cores * cpu_usd_per_hour + memory_gib * memory_usd_per_gib_hour


def select_rows(rows: list[dict[str, Any]], n: int = TARGET_EXAMPLES) -> list[dict[str, Any]]:
    chosen = []
    for row in rows:
        if len(row.get("candidates") or []) != POOL:
            continue
        chosen.append(row)
        if len(chosen) == n:
            break
    return chosen


def keyword_top(candidates: list[dict[str, Any]], k: int = K) -> list[dict[str, Any]]:
    """BM25 order. Injected tools have no keyword rank and are left out."""
    ranked = [(index, tool) for index, tool in enumerate(candidates) if tool.get("bm25_rank") is not None]
    ranked.sort(key=lambda item: (item[1]["bm25_rank"], item[0]))
    return [tool for _, tool in ranked[:k]]


def score_top(candidates: list[dict[str, Any]], scores: list[float], k: int = K) -> list[dict[str, Any]]:
    if len(scores) != len(candidates):
        raise ValueError("scores and candidates differ in length")
    order = sorted(range(len(candidates)), key=lambda index: (-float(scores[index]), index))
    return [candidates[index] for index in order[:k]]


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]", "_", text or "")
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug or not slug[0].isalpha():
        slug = "t_" + slug
    return slug[:64]


def assign_function_names(candidates: list[dict[str, Any]]) -> dict[str, str]:
    """Stable function names for one pool, shared by every arm."""
    used: set[str] = set()
    names: dict[str, str] = {}
    for index, tool in enumerate(candidates):
        identity = str(tool.get("corpus_id") or f"idx_{index}")
        if identity in names:
            continue
        base = _slug(identity)
        name = base
        suffix = 2
        while name in used:
            extra = f"_{suffix}"
            name = base[: 64 - len(extra)] + extra
            suffix += 1
        used.add(name)
        names[identity] = name
    return names


def _param_key(name: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_]", "_", str(name)).strip("_")
    if not key or not key[0].isalpha():
        key = "p_" + key
    return key[:48]


def tool_schema(tool: dict[str, Any], function_name: str, description_chars: int) -> dict[str, Any]:
    description = tool.get("description") or ""
    text = tool.get("name") or function_name
    if description_chars > 0 and description:
        text = f"{text}. {description[:description_chars]}"
    properties = {}
    for parameter in tool.get("parameters") or []:
        key = _param_key(str(parameter))
        if key not in properties:
            properties[key] = {"type": "string"}
    return {
        "type": "function",
        "function": {
            "name": function_name,
            "description": text,
            "parameters": {"type": "object", "properties": properties},
        },
    }


def qwen_tool_prompt(query: str, tools: list[dict[str, Any]], system: str = SYSTEM_PROMPT) -> str:
    """Qwen2.5-Instruct tool-call template. One user query, no extra instruction."""
    rendered = "\n".join(json.dumps(tool, ensure_ascii=False, sort_keys=True) for tool in tools)
    return (
        "<|im_start|>system\n"
        f"{system}\n\n# Tools\n\n"
        "You may call one or more functions to assist with the user query.\n\n"
        "You are provided with function signatures within <tools></tools> XML tags:\n"
        f"<tools>\n{rendered}\n</tools>\n\n"
        "For each function call, return a json object with function name and arguments "
        "within <tool_call></tool_call> XML tags:\n"
        '<tool_call>\n{"name": <function-name>, "arguments": <args-json-object>}\n</tool_call>'
        "<|im_end|>\n"
        f"<|im_start|>user\n{query}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


_TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def parse_tool_calls(text: str) -> list[str]:
    """Function names in call order. Malformed calls are skipped."""
    names = []
    for match in _TOOL_CALL.finditer(text or ""):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        name = payload.get("name") if isinstance(payload, dict) else None
        if isinstance(name, str) and name:
            names.append(name)
    return names


def called_tool(text: str, allowed: set[str]) -> str | None:
    """First call whose name is on the menu this arm actually showed."""
    for name in parse_tool_calls(text):
        if name in allowed:
            return name
    return None


def arm_menus(candidates: list[dict[str, Any]], original_scores: list[float], tuned_scores: list[float], k: int = K) -> dict[str, list[dict[str, Any]]]:
    return {
        "full_menu": list(candidates),
        "keyword_search": keyword_top(candidates, k),
        "original_open_jev_2b": score_top(candidates, original_scores, k),
        "tuned_2b": score_top(candidates, tuned_scores, k),
    }


def example_accuracy(ground: str | None, predicted: str | None, arm: str) -> bool:
    if arm == "full_menu":
        return True
    return predicted == ground


def summarize_arms(examples: list[dict[str, Any]], costs: dict[str, float]) -> dict[str, dict[str, Any]]:
    summary = {}
    n = len(examples)
    for arm in RUNNING_ARMS:
        if arm == "full_menu":
            accuracy = 1.0 if n else None
        elif n == 0:
            accuracy = None
        else:
            accuracy = sum(1 for row in examples if row["arms"][arm]["match"]) / n
        summary[arm] = {
            "label": ARM_LABELS[arm],
            "accuracy": accuracy,
            "modal_cost_usd": costs.get(arm),
            "paused": False,
            "calls": n,
        }
    summary["hosted_jev"] = {
        "label": ARM_LABELS["hosted_jev"],
        "accuracy": None,
        "modal_cost_usd": None,
        "paused": True,
        "calls": 0,
    }
    return summary


def graph_points(arms: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for arm in RUNNING_ARMS:
        record = arms[arm]
        if record.get("paused") or record.get("accuracy") is None or record.get("modal_cost_usd") is None:
            continue
        points.append(
            {
                "label": record["label"],
                "accuracy": record["accuracy"],
                "modal_cost_usd": record["modal_cost_usd"],
            }
        )
    return points


def allocate_modal_costs(
    generate_seconds: dict[str, float],
    h100_load_seconds: float,
    prefetch_usd: float,
    rank_usd: float,
    h100_usd_per_second: float,
    cli_total_usd: float | None = None,
) -> dict[str, float]:
    """Split this run's Modal bill across the four arms that actually called the model."""
    raw = {arm: 0.0 for arm in RUNNING_ARMS}
    shared = (h100_load_seconds * h100_usd_per_second) + prefetch_usd
    each = shared / len(RUNNING_ARMS)
    for arm in RUNNING_ARMS:
        raw[arm] += each
        raw[arm] += float(generate_seconds.get(arm) or 0.0) * h100_usd_per_second
    raw["original_open_jev_2b"] += rank_usd / 2.0
    raw["tuned_2b"] += rank_usd / 2.0
    total = sum(raw.values())
    if cli_total_usd is not None and total > 0:
        scale = cli_total_usd / total
        raw = {arm: value * scale for arm, value in raw.items()}
    return raw


def hosted_jev_status(env_text: str) -> dict[str, Any]:
    """Paused when the key length is zero. The value is not returned."""
    value = parse_env_text(env_text).get("JEV_API_KEY", "")
    if len(value.strip()) == 0:
        reason = "JEV_API_KEY in /workspace/.env is empty. The hosted Jev arm was not called."
    else:
        reason = "JEV_API_KEY is present, but this comparison does not call the hosted Jev API."
    return {
        "in_design": True,
        "paused": True,
        "called": False,
        "included_in_graph": False,
        "reason": reason,
    }


def running_frontier_apps(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    running = []
    for app in apps:
        desc = str(app.get("Description") or app.get("description") or app.get("name") or "")
        state = str(app.get("State") or app.get("state") or app.get("status") or "").lower()
        if "frontier" not in desc.lower():
            continue
        if state in {"stopped", "complete", "completed", "cancelled", "canceled", "failed"}:
            continue
        running.append({"description": desc, "state": state, "app_id": app.get("App ID") or app.get("app_id") or app.get("object_id")})
    return running


def plot_cost_accuracy(points: list[dict[str, Any]], path: Path, title: str = "Frontier tool call: cost versus accuracy") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from frontier_plot import display_label, draw_labeled_scatter

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.2, 5.1), dpi=140)
    xs = [point["modal_cost_usd"] for point in points]
    ys = [point["accuracy"] for point in points]
    labels = [display_label(point["label"]) for point in points]
    ax.set_xlabel("Modal cost (USD)")
    ax.set_ylabel("Accuracy")
    ax.set_ylim(-0.06, 1.12)
    if xs:
        span = max(xs) - min(xs)
        pad = max(0.02, span * 0.22, max(abs(value) for value in xs) * 0.05)
        ax.set_xlim(min(xs) - pad * 0.55, max(xs) + pad * 2.6)
    ax.set_title(title)
    ax.grid(True, axis="both", linestyle=":", alpha=0.5)
    fig.tight_layout()
    draw_labeled_scatter(ax, xs, ys, labels)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_transcripts(examples: list[dict[str, Any]], path: Path, model: str) -> None:
    lines = [
        "# Frontier transcripts",
        "",
        f"Model: {model}, 4-bit. Each example is one query. The full menu is the 50-candidate pool. k=10.",
        "",
        "Hosted Jev is in the design and is paused. It has no transcript because it was not called.",
        "",
    ]
    for example in examples:
        lines.append(f"## {example['id']}")
        lines.append("")
        lines.append(example["query"])
        lines.append("")
        ground = example.get("ground_tool") or {}
        lines.append(
            "Ground truth is the full-menu call: "
            f"{ground.get('name') or '(no tool)'} ({ground.get('function_name') or 'none'})."
        )
        lines.append("")
        for arm in RUNNING_ARMS:
            record = example["arms"][arm]
            lines.append(f"### {ARM_LABELS[arm]}")
            lines.append("")
            called = record.get("called_name") or "(no tool)"
            lines.append(f"Called: {called} ({record.get('called_function') or 'none'}). Match: {record['match']}.")
            shown = ", ".join(record.get("shown_names") or [])
            lines.append("")
            lines.append(f"Tools shown: {shown}")
            lines.append("")
            lines.append("```")
            lines.append((record.get("raw") or "").rstrip())
            lines.append("```")
            lines.append("")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def frontier_h100_containers(containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for container in containers:
        blob = json.dumps(container).lower()
        if "h100" in blob and "frontier" in blob:
            hits.append(container)
    return hits
