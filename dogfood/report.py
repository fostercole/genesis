"""Summarize local dogfood logs. Schema bytes are not token or dollar savings."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def summarize(rows: list[dict]) -> dict:
    selections = {row["selection_id"]: row for row in rows if row.get("event") == "selection"}
    # The last manual rating for a task supersedes an earlier rating.
    final_ratings = {row["selection_id"]: row for row in rows if row.get("event") == "quality" and row.get("selection_id")}
    coverage = [row for row in rows if row.get("event") == "tool_call" and
                row.get("selection_id") in selections and row.get("mode") == "shadow"]
    by_mode = {}
    for mode in ("off", "shadow", "filter"):
        choices = [row for row in selections.values() if row["mode"] == mode]
        usage = [row for row in rows if row.get("event") == "usage" and row.get("mode") == mode]
        ratings = [row for row in final_ratings.values() if row.get("mode") == mode]
        tasks = [row for row in rows if row.get("event") == "task_end" and row.get("mode") == mode]
        by_mode[mode] = {
            "completed_tasks": len(tasks),
            "median_task_wall_ms": statistics.median(row["wall_ms"] for row in tasks) if tasks else None,
            "selections": len(choices),
            "median_selection_wall_ms": statistics.median(row["wall_ms"] for row in choices) if choices else None,
            "main_model_requests": len(usage),
            "input_tokens": sum(row.get("input", 0) for row in usage),
            "cache_read_tokens": sum(row.get("cache_read", 0) for row in usage),
            "cache_write_tokens": sum(row.get("cache_write", 0) for row in usage),
            "output_tokens": sum(row.get("output", 0) for row in usage),
            "provider_reported_cost_usd": sum(row.get("cost_usd", 0) for row in usage),
            "manual_ratings": dict(Counter(row["rating"] for row in ratings)),
        }
    return {
        "by_mode": by_mode,
        "fallbacks": sum(row.get("event") == "fallback" for row in rows),
        "expansions": sum(row.get("event") == "expand" for row in rows),
        "shadow_tool_calls_observed": len(coverage),
        "shadow_tool_calls_covered": sum(bool(row["would_be_available"]) for row in coverage),
        "notes": ["Compare the same tasks across modes; aggregate totals alone do not establish savings.",
                  "Shadow coverage observes the full-menu agent's calls; it is not a task-success benchmark.",
                  "Logs contain tool schema byte counts, not a tokenizer-based estimate of saved tokens.",
                  "Provider cost excludes local electricity and hardware. Manual ratings are subjective."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", type=Path, default=Path.home() / ".pi/agent/genesis/events.jsonl")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.log.expanduser().read_text().splitlines() if line.strip()]
    print(json.dumps(summarize(rows), indent=2))


if __name__ == "__main__":
    main()
