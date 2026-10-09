"""Attach the hosted Jev top-10 arm to a finished frontier sample.

Uses saved full-menu calls as ground truth. Does not launch a GPU.
"""

from __future__ import annotations

import json
from pathlib import Path

from frontier_driver import GRAPH_MEDIA, GRAPH_REPO, LABELS, RESULT_PATH, TRANSCRIPT_PATH
from frontier_menu import calls_match, load_jsonl
from frontier_plot import write_both
from hosted_jev import HOSTED_LABEL

RANK_PATH = Path("results/hosted_jev_rank.json")
DEV_JSONL = Path("data/dev_bm25_top50.jsonl")
# Published Jev 1.13 price. Output tokens are free. This is not a Modal charge.
INPUT_USD_PER_TOKEN = 0.042 / 1_000_000
HOSTED_ARM = "hosted"


def attach(record: dict, ranks: dict[str, dict]) -> dict:
    queries = record.get("queries") or []
    if not queries:
        raise RuntimeError("no saved queries")
    hits = 0
    input_tokens = 0
    output_tokens = 0
    attached = []
    for query in queries:
        rank = ranks.get(query["id"])
        if not rank or not rank.get("ok"):
            raise RuntimeError(f"missing hosted rank for {query['id']}")
        called = rank.get("called")
        truth = query["arms"]["full"]["called"]
        match = calls_match(truth, [called] if called else [])
        hits += int(match)
        input_tokens += int(rank.get("input_tokens") or 0)
        output_tokens += int(rank.get("output_tokens") or 0)
        arms = dict(query["arms"])
        arms[HOSTED_ARM] = {
            "called": [called] if called else [],
            "seconds": float(rank.get("seconds") or 0),
            "match": match,
        }
        attached.append({"id": query["id"], "query": query.get("query"), "arms": arms, "top": rank.get("top") or []})
    n = len(attached)
    accuracy = hits / n if n else 0.0
    api_cost = input_tokens * INPUT_USD_PER_TOKEN
    arms = dict(record.get("arms") or {})
    arms[HOSTED_ARM] = {
        "label": HOSTED_LABEL,
        "accuracy": accuracy,
        "cost_usd": 0.0,
        "seconds": sum(item["arms"][HOSTED_ARM]["seconds"] for item in attached),
        "modal_cost_usd": 0.0,
        "api_cost_usd": api_cost,
    }
    record = dict(record)
    record["queries"] = [
        {
            "id": item["id"],
            "arms": {
                arm: {"called": body["called"], "seconds": body["seconds"]}
                for arm, body in item["arms"].items()
            },
        }
        for item in attached
    ]
    # Keep the hosted top-10 on the side so transcripts can name the menu.
    record["hosted_menus"] = {item["id"]: item["top"] for item in attached}
    record["arms"] = arms
    record["hosted_jev"] = {
        "in_design": True,
        "paused": False,
        "called": True,
        "included_in_graph": True,
        "endpoint": "https://api.typesafe.ai/v1/systemone",
        "model": next(iter(ranks.values())).get("model") if ranks else "jev-latest",
        "modal_cost_usd": 0.0,
        "api_cost_usd": api_cost,
        "api_input_tokens": input_tokens,
        "api_output_tokens": output_tokens,
        "reason": (
            "Hosted Jev chose one tool from the same 50-tool menu. "
            "Accuracy is whether that choice matches the frontier model's full-menu call. "
            "The API bill is separate from Modal and was not a reason to spend more GPU credit."
        ),
    }
    record["hosted_jev_included"] = True
    record["hosted_jev_reason"] = record["hosted_jev"]["reason"]
    record["accuracy_hits"] = hits
    return record


def graph_arms(record: dict) -> list[dict]:
    order = ("full", "bm25", "original", "tuned", HOSTED_ARM)
    points = []
    for arm in order:
        body = record["arms"][arm]
        points.append(
            {
                "label": body.get("label") or LABELS.get(arm) or HOSTED_LABEL,
                "cost_usd": float(body["cost_usd"]),
                "accuracy": float(body["accuracy"]),
            }
        )
    return points


def write_readable_transcript(
    path: Path,
    inference_queries: list[dict],
    record: dict,
    queries_text: dict[str, str],
) -> None:
    """Human labels. The keyword arm is never titled BM25."""
    labels = {
        "full": "full menu",
        "bm25": "keyword search",
        "original": "original Open-Jev-2B top 10",
        "tuned": "tuned 2B top 10",
        "hosted": HOSTED_LABEL,
    }
    order = ("full", "bm25", "original", "tuned", "hosted")
    lines = [
        "# Frontier tool-call transcripts",
        "",
        f"Model `{record['model']}`, 4-bit. Sample size {record['sample_size']}. k=10.",
        "Ground truth is the tool the model called on the full menu.",
        "Keyword search, original Open-Jev-2B, and tuned 2B each keep 10 tools, and the same model calls one tool from that menu.",
        "Hosted Jev is the TypeSafe API (`jev-latest`), not the local Open-Jev-2B checkpoint.",
        "It chooses one tool from the same 50-tool menu. Accuracy is whether that choice matches the full-menu call.",
        "The hosted arm did not start another GPU. Its API cost is separate from the Modal bill.",
        "",
    ]
    by_id = {query["id"]: query for query in inference_queries}
    menus = record.get("hosted_menus") or {}
    for saved in record["queries"]:
        full = by_id[saved["id"]]
        lines.append(f"## {saved['id']}")
        lines.append("")
        lines.append(queries_text.get(saved["id"]) or full.get("query") or "")
        lines.append("")
        lines.append("| Arm | Tools shown | Called | Matched full menu | Seconds |")
        lines.append("| --- | ---: | --- | --- | ---: |")
        truth = saved["arms"]["full"]["called"]
        for arm in order:
            if arm == "hosted":
                item = saved["arms"]["hosted"]
                shown = len(menus.get(saved["id"]) or [])
            else:
                item = full["arms"][arm]
                shown = item.get("n_shown", "")
            called = ", ".join(item["called"]) if item["called"] else "(none)"
            matched = "yes" if calls_match(truth, item["called"]) else "no"
            lines.append(
                f"| {labels[arm]} | {shown} | {called} | {matched} | {float(item.get('seconds') or 0):.2f} |"
            )
        lines.append("")
        for arm in ("full", "bm25", "original", "tuned"):
            item = full["arms"][arm]
            names = ", ".join(tool["call_name"] for tool in item.get("shown") or [])
            lines.append(f"### {labels[arm]}")
            lines.append("")
            lines.append(f"Menu: {names}")
            lines.append("")
            lines.append("```")
            lines.append((item.get("output") or "").rstrip())
            lines.append("```")
            lines.append("")
        names = ", ".join(tool.get("call_name") or "" for tool in menus.get(saved["id"]) or [])
        lines.append(f"### {labels['hosted']}")
        lines.append("")
        lines.append(f"Top 10: {names}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def render_hosted_sections(record: dict, queries_text: dict[str, str]) -> str:
    lines = [
        "",
        "## Hosted Jev top 10",
        "",
        "Hosted Jev is the TypeSafe Jev API (`jev-latest`), not the local Open-Jev-2B checkpoint.",
        "For each query it picks one tool from the same 50-tool menu. The ten highest-probability tools are listed.",
        "Ground truth remains the tool the frontier model called on the full menu.",
        "This arm did not start another GPU. Its API cost is separate from the Modal bill.",
        "",
    ]
    for query in record["queries"]:
        hosted = query["arms"]["hosted"]
        truth = query["arms"]["full"]["called"]
        match = "yes" if calls_match(truth, hosted["called"]) else "no"
        called = ", ".join(hosted["called"]) if hosted["called"] else "(none)"
        menu = record.get("hosted_menus", {}).get(query["id"]) or []
        names = ", ".join(tool.get("call_name") or "" for tool in menu)
        lines.append(f"### {query['id']}")
        lines.append("")
        lines.append(queries_text.get(query["id"]) or "")
        lines.append("")
        lines.append(f"Called: {called}. Matched full menu: {match}.")
        lines.append("")
        lines.append(f"Top 10: {names}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    record = json.loads(RESULT_PATH.read_text())
    model = str(record.get("model") or "")
    if "72B" not in model:
        raise SystemExit(f"refusing to attach hosted Jev onto model {model or '(none)'}")
    if not record.get("queries"):
        raise SystemExit("frontier sample has no saved calls")
    rank_doc = json.loads(RANK_PATH.read_text())
    ranks = {row["id"]: row for row in rank_doc["rows"]}
    updated = attach(record, ranks)
    texts = {row["id"]: row.get("query") or "" for row in load_jsonl(DEV_JSONL)}
    RESULT_PATH.write_text(json.dumps(updated, indent=2) + "\n")
    title = f"{updated['model']}  n={updated['sample_size']}  k=10"
    write_both(graph_arms(updated), title, GRAPH_REPO, GRAPH_MEDIA)
    section = render_hosted_sections(updated, texts)
    existing = TRANSCRIPT_PATH.read_text() if TRANSCRIPT_PATH.exists() else "# Frontier tool-call transcripts\n"
    if "## Hosted Jev top 10" in existing:
        existing = existing.split("## Hosted Jev top 10", 1)[0].rstrip() + "\n"
    TRANSCRIPT_PATH.write_text(existing.rstrip() + "\n" + section)
    print(
        json.dumps(
            {
                "event": "hosted_attached",
                "sample_size": updated["sample_size"],
                "accuracy": updated["arms"]["hosted"]["accuracy"],
                "api_cost_usd": updated["hosted_jev"]["api_cost_usd"],
                "modal_cost_usd": 0.0,
                "graph": str(GRAPH_MEDIA),
            }
        )
    )


if __name__ == "__main__":
    main()
