"""Score hosted Jev on the saved BM25 top-50 dev list. No GPU and no Modal.

Original and tuned metrics are copied from results/dev_bm25_top50.json.
This script does not rescore those checkpoints and does not rewrite the
frontier chart.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from attach_hosted_arm import INPUT_USD_PER_TOKEN
from frontier_menu import assign_call_names, load_jsonl
from hosted_jev import build_choice_body, choice_index, rank_query
from pi_loop import ENV_PATH, load_env_file
from toolret_smoke.dev_eval import aggregate_metrics

ROOT = Path(__file__).resolve().parent
DEV_JSONL = ROOT / "data" / "dev_bm25_top50.jsonl"
BASELINE_PATH = ROOT / "results" / "dev_bm25_top50.json"
PRIOR_RANK_PATH = ROOT / "results" / "hosted_jev_rank.json"
RESULT_PATH = ROOT / "results" / "hosted_jev_dev.json"
TABLE_PATH = ROOT / "results" / "hosted_jev_dev.md"
CHECKPOINT_PATH = ROOT / "results" / "hosted_jev_dev_checkpoint.jsonl"
NOTE_PATH = Path("/cursor/stores/bc-c73881fc-461b-4a9f-9679-fb150ab43075/docs/hosted-jev-dev.md")
CAP_USD = 5.0
# Stop launching another call once the bill is this close to the cap.
STOP_USD = 4.90
# Headroom for calls already in flight. Well above the ~$0.00011 mean.
RESERVE_USD = 0.002
WORKERS = 8
METRIC_KEYS = (
    "ndcg@10",
    "recall@3",
    "recall@5",
    "recall@10",
    "completeness@3",
    "completeness@5",
    "completeness@10",
)
TABLE_LABELS = (
    ("ndcg@10", "nDCG@10"),
    ("recall@3", "recall@3"),
    ("recall@5", "recall@5"),
    ("recall@10", "recall@10"),
    ("completeness@3", "completeness@3"),
    ("completeness@5", "completeness@5"),
    ("completeness@10", "completeness@10"),
    ("top-1", "top-1"),
)


def prefix_length(estimates: list[float], cap: float = CAP_USD) -> int:
    """Largest leading slice whose estimated bill is within the cap."""
    total = 0.0
    count = 0
    for estimate in estimates:
        if estimate < 0:
            raise ValueError("an estimate cannot be negative")
        if total + estimate > cap:
            break
        total += estimate
        count += 1
    return count


def tokens_per_char(rows: list[dict], prior_path: Path = PRIOR_RANK_PATH) -> tuple[float, dict[str, Any]]:
    """Input tokens per request-body character, from the earlier hosted calls."""
    prior = json.loads(prior_path.read_text())
    by_id = {row["id"]: row for row in prior.get("rows") or []}
    chars = 0
    tokens = 0
    matched = 0
    for row in rows:
        prior_row = by_id.get(row["id"])
        if not isinstance(prior_row, dict) or not prior_row.get("ok"):
            continue
        used = prior_row.get("input_tokens")
        if not isinstance(used, int):
            continue
        body = build_choice_body(row["query"], assign_call_names(row["candidates"]))
        chars += len(json.dumps(body))
        tokens += used
        matched += 1
    if chars <= 0 or matched == 0:
        raise RuntimeError("the prior hosted calls do not overlap this dev list")
    return tokens / chars, {
        "matched_prior_rows": matched,
        "prior_input_tokens": tokens,
        "prior_body_chars": chars,
        "prior_sample_size": prior.get("sample_size"),
        "prior_api_cost_usd": prior.get("api_cost_usd"),
        "prior_model": prior.get("model"),
        "usd_per_input_token": INPUT_USD_PER_TOKEN,
    }


def row_estimates(rows: list[dict], rate: float) -> list[float]:
    estimates = []
    for row in rows:
        body = build_choice_body(row["query"], assign_call_names(row["candidates"]))
        tokens = len(json.dumps(body)) * rate
        estimates.append(tokens * INPUT_USD_PER_TOKEN)
    return estimates


def ranks_from_order(candidates: list[dict], order: list[int], n_positive: int) -> list[int | None]:
    """1-based ranks of gold tools. Unranked golds are None, the same as a miss."""
    if n_positive <= 0:
        raise ValueError("a dev row needs at least one positive")
    relevant = [index for index, tool in enumerate(candidates) if tool.get("relevant")]
    if len(relevant) > n_positive:
        raise ValueError("more relevant candidates than positives")
    rank_of: dict[int, int] = {}
    for rank, index in enumerate(order, start=1):
        if index not in rank_of:
            rank_of[index] = rank
    # Same order as positive_ranks: golds in the returned ranking, best first,
    # then None for every gold the response did not rank.
    found = sorted(rank_of[index] for index in relevant if index in rank_of)
    missing = n_positive - len(found)
    return found + [None] * missing


def top1_hit(ranks: list[int | None]) -> float:
    """1 when the rank-1 tool is a labeled positive."""
    return 1.0 if any(rank == 1 for rank in ranks) else 0.0


def top1_rate(per_row: list[dict]) -> float:
    if not per_row:
        raise ValueError("no rows")
    return sum(top1_hit(row["ranks"]) for row in per_row) / len(per_row)


def load_baselines(path: Path = BASELINE_PATH) -> dict[str, Any]:
    """Copy the saved original and tuned metrics. Do not rescore them."""
    data = json.loads(path.read_text())
    models = {}
    for name in ("original", "tuned"):
        body = data["models"][name]
        models[name] = {
            "metrics": {key: body["metrics"][key] for key in METRIC_KEYS},
            "top-1": top1_rate(body["per_row"]),
            "rows": len(body["per_row"]),
            "source": "results/dev_bm25_top50.json",
        }
    return {
        "locked_k": data["locked_k"]["locked_k"],
        "best_completeness": data["locked_k"]["best_completeness"],
        "models": models,
    }


def choice_rank(choice: Any, order: list[int], n_tools: int) -> int | None:
    if not isinstance(choice, str):
        return None
    index = choice_index({"choice": choice}, n_tools)
    if index is None or index not in order:
        return None
    return order.index(index) + 1


def score_row(row: dict, api_key: str, rate: float) -> dict[str, Any]:
    """One hosted call. The result never includes the API key."""
    tools = assign_call_names(row["candidates"])
    body_chars = len(json.dumps(build_choice_body(row["query"], tools)))
    fallback = body_chars * rate * INPUT_USD_PER_TOKEN
    try:
        result = rank_query(row["query"], tools, api_key, attempts=5)
    except Exception as exc:
        return {
            "id": row["id"],
            "ok": False,
            "status": 0,
            "ranking": "empty",
            "n_ranked": 0,
            "ranks": [None] * int(row["n_positive"]),
            "n_positive": int(row["n_positive"]),
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": 0.0,
            "cost_estimated": False,
            "seconds": 0.0,
            "model": None,
            "choice_rank": None,
            "error": type(exc).__name__,
        }
    tokens = result.get("input_tokens")
    if isinstance(tokens, int):
        cost = tokens * INPUT_USD_PER_TOKEN
        estimated = False
    else:
        tokens = None
        # A failed call with no usage line is not counted as spend.
        # A success without usage uses the pre-run token rate so the cap still sees it.
        cost = fallback if result.get("ok") else 0.0
        estimated = bool(result.get("ok"))
    order = list(result.get("order") or [])
    ranking = result.get("ranking") or "empty"
    if not result.get("ok"):
        order = []
        ranking = "empty"
    n_positive = int(row["n_positive"])
    return {
        "id": row["id"],
        "ok": bool(result.get("ok")) and bool(order),
        "status": result.get("status"),
        "ranking": ranking if order else "empty",
        "n_ranked": len(order),
        "ranks": ranks_from_order(row["candidates"], order, n_positive),
        "n_positive": n_positive,
        "input_tokens": tokens,
        "output_tokens": result.get("output_tokens") if isinstance(result.get("output_tokens"), int) else None,
        "cost_usd": cost,
        "cost_estimated": estimated,
        "seconds": result.get("seconds"),
        "model": result.get("model"),
        "choice_rank": choice_rank(result.get("choice"), order, len(tools)),
        "error": result.get("error"),
    }


def _line(record: dict) -> str:
    return json.dumps(record, separators=(",", ":")) + "\n"


class Checkpoint:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.rows: dict[str, dict] = {}
        if path.is_file():
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                self.rows[row["id"]] = row

    def store(self, record: dict) -> None:
        with self._lock:
            self.rows[record["id"]] = record
            with self.path.open("a") as handle:
                handle.write(_line(record))
                handle.flush()

    def spend(self) -> float:
        with self._lock:
            return sum(float(row.get("cost_usd") or 0) for row in self.rows.values())


def _needs_call(record: dict | None) -> bool:
    return not isinstance(record, dict) or not record.get("ok")


def run_calls(rows: list[dict], api_key: str, rate: float, checkpoint: Checkpoint) -> dict[str, Any]:
    """Score rows in file order. Stop launching calls as the bill approaches $5."""
    pending_rows = [row for row in rows if _needs_call(checkpoint.rows.get(row["id"]))]
    stop_reason = ""
    auth_stop = False
    next_index = 0
    inflight: dict[Any, dict] = {}
    finished_since_print = 0
    observed_costs: list[float] = []

    def note_progress() -> None:
        ok = sum(1 for row in rows if checkpoint.rows.get(row["id"], {}).get("ok"))
        print(
            json.dumps(
                {
                    "event": "progress",
                    "scored": ok,
                    "attempted_target": len(rows),
                    "spend_usd": round(checkpoint.spend(), 6),
                }
            ),
            flush=True,
        )

    def would_pass_cap(extra_inflight: int) -> bool:
        spend = checkpoint.spend()
        if spend >= STOP_USD:
            return True
        mean = sum(observed_costs) / len(observed_costs) if observed_costs else RESERVE_USD
        upcoming = max(mean, RESERVE_USD)
        return spend + (extra_inflight + 1) * upcoming >= CAP_USD

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while next_index < len(pending_rows) or inflight:
            while next_index < len(pending_rows) and len(inflight) < WORKERS and not stop_reason:
                if would_pass_cap(len(inflight)):
                    stop_reason = "live spend approached the $5 cap"
                    break
                row = pending_rows[next_index]
                future = pool.submit(score_row, row, api_key, rate)
                inflight[future] = row
                next_index += 1
            if not inflight:
                break
            done, _waiting = wait(inflight, return_when=FIRST_COMPLETED)
            for future in done:
                inflight.pop(future)
                record = future.result()
                checkpoint.store(record)
                finished_since_print += 1
                if record.get("ok") and isinstance(record.get("input_tokens"), int):
                    observed_costs.append(float(record["cost_usd"]))
                if float(record.get("cost_usd") or 0) > 0.05:
                    stop_reason = "one hosted call cost more than $0.05; stopped under the cap"
                if record.get("status") in {401, 402, 403}:
                    stop_reason = f"hosted Jev returned HTTP {record.get('status')}"
                    auth_stop = True
                if checkpoint.spend() >= CAP_USD:
                    stop_reason = "live spend reached the $5 cap"
            if finished_since_print >= 25:
                note_progress()
                finished_since_print = 0
        if finished_since_print:
            note_progress()
    return {"stop_reason": stop_reason, "auth_stop": auth_stop}


def collect_scored(rows: list[dict], checkpoint: Checkpoint, cap_stopped: bool) -> list[dict]:
    """File order. A cap stop keeps the leading successful rows and drops the tail."""
    taken = []
    for row in rows:
        saved = checkpoint.rows.get(row["id"])
        ok = isinstance(saved, dict) and bool(saved.get("ok"))
        if ok:
            taken.append(saved)
        elif cap_stopped:
            break
    return taken


def hosted_summary(scored: list[dict]) -> dict[str, Any]:
    metrics = aggregate_metrics(scored)
    ranked_counts: dict[str, int] = {}
    choice_matches = 0
    for row in scored:
        kind = str(row.get("ranking") or "empty")
        ranked_counts[kind] = ranked_counts.get(kind, 0) + 1
        if row.get("choice_rank") == 1:
            choice_matches += 1
    n_ranked = [int(row.get("n_ranked") or 0) for row in scored]
    return {
        "rows": len(scored),
        "metrics": {key: metrics[key] for key in METRIC_KEYS},
        "top-1": top1_rate(scored),
        "choice_is_rank1": choice_matches / len(scored),
        "ranking_counts": ranked_counts,
        "n_ranked_min": min(n_ranked),
        "n_ranked_max": max(n_ranked),
        "per_row": [
            {"id": row["id"], "n_positive": row["n_positive"], "ranks": row["ranks"]}
            for row in scored
        ],
    }


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def comparison_table(models: dict[str, dict]) -> str:
    header = "| model | " + " | ".join(label for _key, label in TABLE_LABELS) + " |"
    rule = "| --- | " + " | ".join("---:" for _key, _label in TABLE_LABELS) + " |"
    lines = [header, rule]
    names = (("original", "original 2B"), ("tuned", "tuned 2B"), ("hosted_jev", "hosted Jev"))
    for key, label in names:
        body = models[key]
        cells = []
        for metric, _label in TABLE_LABELS:
            if metric == "top-1":
                cells.append(_fmt(body["top-1"]))
            else:
                cells.append(_fmt(body["metrics"][metric]))
        lines.append("| " + label + " | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    hosted = report["models"]["hosted_jev"]
    prefix = "yes" if report["prefix"] else "no"
    lines = [
        "# Hosted Jev on the dev BM25 top 50",
        "",
        "Same 50-tool candidate lists as the original and tuned 2B.",
        "Those two rows are copied from `results/dev_bm25_top50.json` and were not rescored.",
        f"Locked k is {report['locked_k']}. Hosted Jev did not move that lock.",
        "",
        comparison_table(report["models"]),
        "",
        f"Rows scored: {report['rows_scored']} of {report['rows_in_file']}.",
        f"Rows failed: {report['rows_failed']}.",
        f"API spend: ${report['api_cost_usd']:.6f}.",
        f"Prefix because of the $5 cap: {prefix}.",
        "",
        "Top-1 is the fraction of rows whose rank-1 tool is a labeled positive.",
        "Hosted ranks are the API probabilities, highest first. Ties keep menu order.",
        "A response with no probability map uses the single chosen tool as rank 1 and leaves every lower rank empty.",
        "Tools the response does not score stay unranked.",
        "",
        f"Pre-run estimate: ${report['estimate_usd']:.6f} for {report['estimate_rows']} rows",
        f"at ${INPUT_USD_PER_TOKEN * 1_000_000:.3f} per million input tokens. Output tokens are free.",
        f"The token rate comes from {report['estimate']['matched_prior_rows']} earlier hosted calls on this same client.",
        f"Reported model: {hosted.get('model') or report.get('model')}.",
        "",
        "Exact values are in `results/hosted_jev_dev.json`. The table rounds to four decimals.",
        "",
    ]
    if report.get("stop_reason"):
        lines.append(f"Stop note: {report['stop_reason']}.")
        lines.append("")
    return "\n".join(lines)


def render_note(report: dict[str, Any]) -> str:
    prefix = "yes" if report["prefix"] else "no"
    body = render_markdown(report)
    # Drop the repo-relative title block's first heading; the note has its own.
    return (
        "---\n"
        "cursor:\n"
        '  subagentId: "bc-86268829-28b0-5975-9772-c57e6a1022d4"\n'
        "---\n\n"
        + body
        + f"\nPrefix size: {report['rows_scored']} rows.\n"
        + f"Cap prefix: {prefix}.\n"
    )


def build_report(
    baselines: dict[str, Any],
    scored: list[dict],
    rows_in_file: int,
    estimate_usd: float,
    estimate_rows: int,
    estimate_detail: dict[str, Any],
    spend: float,
    prefix: bool,
    stop_reason: str,
    input_tokens: int,
    output_tokens: int,
    failed: int,
) -> dict[str, Any]:
    hosted = hosted_summary(scored)
    model_name = next((row.get("model") for row in scored if row.get("model")), None)
    hosted_public = {
        "metrics": hosted["metrics"],
        "top-1": hosted["top-1"],
        "rows": hosted["rows"],
        "choice_is_rank1": hosted["choice_is_rank1"],
        "ranking_counts": hosted["ranking_counts"],
        "n_ranked_min": hosted["n_ranked_min"],
        "n_ranked_max": hosted["n_ranked_max"],
        "model": model_name,
        "per_row": hosted["per_row"],
    }
    models["hosted_jev"] = hosted_public
    return {
        "status": "complete" if not prefix and failed == 0 else "partial",
        "rows_in_file": rows_in_file,
        "rows_scored": len(scored),
        "rows_failed": failed,
        "prefix": prefix,
        "prefix_because_of_cap": prefix,
        "stop_reason": stop_reason,
        "cap_usd": CAP_USD,
        "api_cost_usd": spend,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "output_priced_usd": 0.0,
        "estimate_usd": estimate_usd,
        "estimate_rows": estimate_rows,
        "estimate": estimate_detail,
        "model": model_name,
        "endpoint": "https://api.typesafe.ai/v1/systemone",
        "locked_k": baselines["locked_k"],
        "candidate_list": "data/dev_bm25_top50.jsonl",
        "baselines": "results/dev_bm25_top50.json",
        "key_length": estimate_detail.get("key_length"),
        "models": {
            "original": baselines["models"]["original"],
            "tuned": baselines["models"]["tuned"],
            "hosted_jev": hosted_public,
        },
    }


def _token_sum(rows: list[dict], key: str) -> int:
    return sum(int(row[key]) for row in rows if isinstance(row.get(key), int))


def append_ledger_once(report: dict[str, Any]) -> None:
    """One line for this API pass. A resumed process does not write a second line."""
    path = ROOT / "ledger.jsonl"
    existing = path.read_text() if path.is_file() else ""
    if '"job": "hosted-jev-dev"' in existing or '"job":"hosted-jev-dev"' in existing:
        return
    line = {
        "date": "2026-10-09",
        "job": "hosted-jev-dev",
        "gpu": None,
        "trained": False,
        "rows": report["rows_scored"],
        "rows_in_file": report["rows_in_file"],
        "status": report["status"],
        "prefix": report["prefix"],
        "api_cost_usd": report["api_cost_usd"],
        "input_tokens": report["input_tokens"],
        "output_tokens": report["output_tokens"],
        "note": "TypeSafe hosted Jev on the dev BM25 top 50. Output tokens are free. Not a Modal charge.",
    }
    with path.open("a") as handle:
        handle.write(json.dumps(line, separators=(",", ":")) + "\n")


def main() -> None:
    key = load_env_file(ENV_PATH).get("JEV_API_KEY", "").strip()
    print(json.dumps({"event": "key", "length": len(key), "present": bool(key)}), flush=True)
    if not key:
        raise SystemExit("JEV_API_KEY is empty")
    rows = load_jsonl(DEV_JSONL)
    if len(rows) != 2000:
        raise SystemExit(f"expected 2000 dev rows, found {len(rows)}")
    rate, detail = tokens_per_char(rows)
    detail["key_length"] = len(key)
    estimates = row_estimates(rows, rate)
    estimate_usd = sum(estimates)
    planned = len(rows) if estimate_usd <= CAP_USD else prefix_length(estimates, CAP_USD)
    print(
        json.dumps(
            {
                "event": "estimate",
                "rows": len(rows),
                "estimate_usd": estimate_usd,
                "planned_rows": planned,
                "prefix": planned < len(rows),
                "usd_per_million_input": INPUT_USD_PER_TOKEN * 1_000_000,
                "tokens_per_char": rate,
                "matched_prior_rows": detail["matched_prior_rows"],
            }
        ),
        flush=True,
    )
    if planned == 0:
        raise SystemExit("even one row estimates over the $5 cap")
    target = rows[:planned]
    checkpoint = Checkpoint(CHECKPOINT_PATH)
    # Ignore checkpoint rows outside this prefix so a resumed run cannot bill past it.
    outside = [row_id for row_id in list(checkpoint.rows) if row_id not in {row["id"] for row in target}]
    for row_id in outside:
        checkpoint.rows.pop(row_id, None)
    started = time.perf_counter()
    run = run_calls(target, key, rate, checkpoint)
    if not run["auth_stop"] and checkpoint.spend() < STOP_USD:
        retry = []
        for row in target:
            saved = checkpoint.rows.get(row["id"])
            if saved is None:
                break
            if not saved.get("ok"):
                retry.append(row)
        for row in retry:
            if checkpoint.spend() >= STOP_USD:
                run["stop_reason"] = run["stop_reason"] or "live spend approached the $5 cap"
                break
            checkpoint.store(score_row(row, key, rate))
    cap_stopped = planned < len(rows) or "cap" in (run["stop_reason"] or "")
    scored = collect_scored(target, checkpoint, cap_stopped)
    if not scored:
        raise SystemExit(run["stop_reason"] or "hosted Jev returned no scored rows")
    attempted = sum(1 for row in target if row["id"] in checkpoint.rows)
    failed = sum(1 for row in target if row["id"] in checkpoint.rows and not checkpoint.rows[row["id"]].get("ok"))
    prefix = cap_stopped and len(scored) < len(rows)
    spend = sum(float(checkpoint.rows[row["id"]].get("cost_usd") or 0) for row in target if row["id"] in checkpoint.rows)
    input_tokens = _token_sum([checkpoint.rows[row["id"]] for row in target if row["id"] in checkpoint.rows], "input_tokens")
    output_tokens = _token_sum([checkpoint.rows[row["id"]] for row in target if row["id"] in checkpoint.rows], "output_tokens")
    baselines = load_baselines()
    report = build_report(
        baselines,
        scored,
        rows_in_file=len(rows),
        estimate_usd=estimate_usd,
        estimate_rows=planned,
        estimate_detail=detail,
        spend=spend,
        prefix=prefix,
        stop_reason=run["stop_reason"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        failed=failed,
    )
    report["elapsed_seconds"] = time.perf_counter() - started
    report["rows_attempted"] = attempted
    RESULT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    TABLE_PATH.write_text(render_markdown(report))
    append_ledger_once(report)
    NOTE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTE_PATH.write_text(render_note(report))
    print(
        json.dumps(
            {
                "event": "done",
                "rows_scored": report["rows_scored"],
                "prefix": report["prefix"],
                "spend_usd": report["api_cost_usd"],
                "failed": failed,
                "stop_reason": run["stop_reason"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
