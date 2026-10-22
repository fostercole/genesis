"""Time actual local inference with an exported Pi menu. No main-model calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, default=Path.home() / ".pi/agent/genesis/tools.json")
    parser.add_argument("--query", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8791")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--candidate-limit", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path(".cache/dogfood-benchmark.json"))
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100 or not 1 <= args.timeout <= 120:
        parser.error("repetitions must be 1..100 and timeout must be 1..120 seconds")
    tools = json.loads(args.tools.expanduser().read_text())
    rows = []
    for repetition in range(args.repetitions):
        request = urllib.request.Request(args.url.rstrip("/") + "/rank", data=json.dumps({
            "query": args.query, "tools": tools, "candidate_limit": args.candidate_limit,
            "top_k": 10, "budget_ms": args.timeout * 1000,
        }).encode(), headers={"Content-Type": "application/json"})
        started = time.monotonic()
        with urllib.request.urlopen(request, timeout=args.timeout + 2) as response:
            row = json.load(response)
        row["wall_ms"] = (time.monotonic() - started) * 1000
        rows.append(row)
        print(f"request {repetition + 1}: {row['wall_ms']:.0f} ms, {row['candidate_count']} candidates", flush=True)
    # Include the first request separately; it may contain cold-kernel overhead.
    report = {"runs": rows, "first_request_ms": rows[0]["wall_ms"],
              "median_wall_ms": statistics.median(row["wall_ms"] for row in rows),
              "warmed_median_ms": statistics.median(row["wall_ms"] for row in rows[1:]) if len(rows) > 1 else None,
              "main_model_calls": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
