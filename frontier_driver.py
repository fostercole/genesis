"""Local driver for the frontier loop. Decides whether a GPU job can launch."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path

from frontier_budget import (
    ARM_ORDER,
    BUFFER_USD,
    FRONTIER_MODELS,
    FULL_SAMPLE,
    STARTER_CREDIT_USD,
    allocate_arm_costs,
    choose_plan,
    filter_hourly,
    may_launch,
    model_hourly,
    prefetch_hourly,
    remaining_starter_credit,
    spend_cap,
    timeout_for_cap,
)
from frontier_menu import (
    K,
    arm_accuracy,
    build_prompts,
    load_dev_ids,
    load_jsonl,
    render_transcripts,
    select_rows,
    write_text,
)
from frontier_plot import write_both
from pi_loop import ENV_PATH, load_env_file

APP_NAME = "toolret-frontier-loop"
RESULT_PATH = Path("results/modal_frontier_loop.json")
TRANSCRIPT_PATH = Path("results/frontier_transcripts.md")
GRAPH_REPO = Path("results/pi-cost-accuracy.png")
GRAPH_MEDIA = Path("/cursor/stores/bc-c73881fc-461b-4a9f-9679-fb150ab43075/media/pi-cost-accuracy.png")
LEDGER_PATH = Path("ledger.jsonl")
DEV_JSONL = Path("data/dev_bm25_top50.jsonl")
DEV_IDS = Path("data/dev_2k.ids")
LABELS = {
    "full": "full menu",
    "bm25": "BM25 top 10",
    "original": "original Open-Jev-2B top 10",
    "tuned": "tuned 2B top 10",
}


def modal_bin() -> str:
    return shutil.which("modal") or str(Path.home() / ".local/bin/modal")


def modal_json(args: list[str]):
    raw = subprocess.check_output([modal_bin(), *args, "--profile", "fostercole"], text=True)
    return json.loads(raw)


def live_rates() -> dict:
    rates = modal_json(["billing", "rates", "--json"])
    needed = [
        "cpu_hour_cost",
        "mem_gib_hour_cost",
        "gpu_hour_cost_l4",
        "gpu_hour_cost_l40s",
        "gpu_hour_cost_a100_80gb",
    ]
    missing = [key for key in needed if key not in rates]
    if missing:
        raise RuntimeError("billing rates missing " + ", ".join(missing))
    return {key: float(rates[key]) for key in needed}


def live_summary() -> dict:
    summary = modal_json(["billing", "summary", "--for", "this month", "--json"])
    return {
        "metered_cost": float(summary["metered_cost"]),
        "credits_applied": abs(float(summary["adjustments"]["credits"])),
        "billed_cost": float(summary["billed_cost"]),
    }


def jev_key_nonempty() -> bool:
    value = load_env_file(ENV_PATH).get("JEV_API_KEY", "").strip()
    return bool(value)


def app_lines(report: list[dict], description: str, seen_ids: set[str]) -> list[dict]:
    return [
        row
        for row in report
        if row.get("description") == description and row.get("object_id") not in seen_ids
    ]


def sum_lines(rows: list[dict]) -> tuple[float, dict[str, float], list[str]]:
    breakdown: dict[str, float] = {}
    for row in rows:
        resource = str(row.get("resource") or "unknown")
        breakdown[resource] = breakdown.get(resource, 0.0) + float(row["cost"])
    ids = sorted({str(row["object_id"]) for row in rows})
    return sum(breakdown.values()), breakdown, ids


def wait_call(call, timeout_s: float, label: str):
    deadline = time.time() + timeout_s
    while True:
        try:
            return call.get(timeout=0)
        except TimeoutError:
            if time.time() > deadline:
                call.cancel(terminate_containers=True)
                raise TimeoutError(label)
            time.sleep(15)
            print(json.dumps({"event": "poll", "label": label}), flush=True)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def append_ledger(entry: dict) -> None:
    with LEDGER_PATH.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def load_tokenizer(model_id: str, revision: str):
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer

    dest = Path("/tmp/frontier-tokenizer") / revision
    snapshot_download(
        repo_id=model_id,
        revision=revision,
        local_dir=str(dest),
        allow_patterns=[
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
            "special_tokens_map.json",
            "added_tokens.json",
            "chat_template.jinja",
            "config.json",
        ],
    )
    return AutoTokenizer.from_pretrained(str(dest), trust_remote_code=False)


def _base_record(summary: dict, remaining: float, cap: float, hosted: bool) -> dict:
    return {
        "launched": False,
        "trained": False,
        "second_epoch": False,
        "official_test_split": False,
        "k": K,
        "menu": "The same dev BM25 top 50 for every arm. Filtered arms keep 10.",
        "hosted_jev_included": hosted,
        "starter_credit_usd": STARTER_CREDIT_USD,
        "metered_cost_before_usd": summary["metered_cost"],
        "credits_applied_before_usd": summary["credits_applied"],
        "billed_cost_before_usd": summary["billed_cost"],
        "remaining_credit_before_launch_usd": remaining,
        "buffer_usd": BUFFER_USD,
        "spend_cap_usd": cap,
        "full_sample": FULL_SAMPLE,
        "model": None,
        "revision": None,
        "sample_size": 0,
        "estimate_usd": None,
        "spend_usd": 0,
        "arms": {},
    }


def execute(prefetch, score_sample, infer, read_saved, results_volume) -> None:
    summary = live_summary()
    remaining = remaining_starter_credit(summary["metered_cost"], summary["credits_applied"])
    cap = spend_cap(remaining)
    hosted = jev_key_nonempty()
    record = _base_record(summary, remaining, cap, hosted)
    print(
        json.dumps(
            {
                "event": "balance",
                "remaining_credit_usd": remaining,
                "spend_cap_usd": cap,
                "metered_cost_usd": summary["metered_cost"],
                "hosted_jev_included": hosted,
            }
        ),
        flush=True,
    )
    if hosted:
        record["stop_reason"] = "JEV_API_KEY is non-empty; this driver does not call hosted Jev and did not launch."
        write_json(RESULT_PATH, record)
        raise SystemExit(record["stop_reason"])
    record["hosted_jev_reason"] = "JEV_API_KEY is empty, so the hosted Jev arm was left out."
    if not may_launch(remaining):
        record["stop_reason"] = (
            f"Remaining Starter credit is ${remaining:.2f}, under $3. No GPU job was launched."
        )
        write_json(RESULT_PATH, record)
        print(json.dumps({"event": "stop", "reason": record["stop_reason"]}), flush=True)
        return

    rates = live_rates()
    plan = choose_plan(rates, cap, FULL_SAMPLE)
    record["rates"] = rates
    record["prelaunch_plan"] = {
        "rejected": plan["rejected"],
        "estimate_usd": plan["estimate_usd"],
        "one_query_estimate_usd": plan["one_query_estimate_usd"],
        "sample_size": plan["sample_size"],
        "model": None if plan["model"] is None else plan["model"]["model_id"],
        "shrunk": plan["shrunk"],
    }
    record["estimate_usd"] = plan["estimate_usd"]
    if plan["model"] is None:
        record["stop_reason"] = (
            "Even one query of the cheapest tool-calling model does not fit under "
            f"remaining credit minus $2 (${cap:.2f}). No GPU job was launched."
        )
        write_json(RESULT_PATH, record)
        print(json.dumps({"event": "stop", "reason": record["stop_reason"], "rejected": plan["rejected"]}), flush=True)
        return

    model = plan["model"]
    record["model"] = model["model_id"]
    record["revision"] = model["revision"]
    record["gpu"] = model["gpu"]
    record["sample_size_planned"] = plan["sample_size"]
    before_report = modal_json(["billing", "report", "--for", "today", "--show-resources", "--json"])
    seen_ids = {str(row["object_id"]) for row in before_report if row.get("description") == APP_NAME}

    dev_ids = load_dev_ids(DEV_IDS)
    rows = select_rows(load_jsonl(DEV_JSONL), dev_ids, plan["sample_size"], seed=0)
    row_ids = [row["id"] for row in rows]
    record["query_ids"] = row_ids
    print(
        json.dumps(
            {
                "event": "launch_cheap",
                "model": model["model_id"],
                "revision": model["revision"],
                "sample_size": plan["sample_size"],
                "estimate_usd": plan["estimate_usd"],
            }
        ),
        flush=True,
    )
    record["launched"] = True
    prefetch_call = prefetch.spawn(model["model_id"], model["revision"], model["key"])
    score_call = score_sample.spawn(row_ids)
    try:
        prefetch_result = wait_call(prefetch_call, model["prefetch_minutes"] * 60 + 900, "prefetch")
        score_result = wait_call(score_call, 900, "score")
    except Exception as exc:
        record["stop_reason"] = f"cheap stage failed: {type(exc).__name__}"
        record["error"] = str(exc)[:500]
        _finish_billing(record, seen_ids, None)
        write_json(RESULT_PATH, record)
        raise
    if not prefetch_result.get("ok") or not score_result.get("ok"):
        record["stop_reason"] = "prefetch or 2B scoring returned ok=false"
        record["prefetch"] = {key: prefetch_result.get(key) for key in ("ok", "cached", "elapsed_seconds", "error")}
        record["score"] = {key: score_result.get(key) for key in ("ok", "elapsed_seconds", "error")}
        _finish_billing(record, seen_ids, None)
        write_json(RESULT_PATH, record)
        return

    sunk = _elapsed_cost(prefetch_result, prefetch_hourly(rates), score_result, filter_hourly(rates))
    record["sunk_estimate_usd"] = sunk
    budget_left = cap - sunk
    gpu_hourly = model_hourly(model, rates, safety=1.0)
    one_query = (float(model["load_seconds"]) + float(model["seconds_per_query"])) / 3600 * gpu_hourly
    if one_query > budget_left:
        record["stop_reason"] = (
            f"After the cheap stage (${sunk:.2f} estimated), one {model['key']} query "
            f"(${one_query:.2f}) does not fit the remaining buffer (${budget_left:.2f})."
        )
        record["estimate_usd"] = sunk + one_query
        _finish_billing(record, seen_ids, None)
        write_json(RESULT_PATH, record)
        return

    try:
        tokenizer = load_tokenizer(model["model_id"], model["revision"])
        prompts = build_prompts(tokenizer, rows, score_result["rows"])
    except Exception as exc:
        record["stop_reason"] = f"prompt build failed: {type(exc).__name__}"
        record["error"] = str(exc)[:500]
        _finish_billing(record, seen_ids, None)
        write_json(RESULT_PATH, record)
        return
    payload_path = Path("/tmp/frontier_payload.json")
    payload_path.write_text(json.dumps(prompts))
    with results_volume.batch_upload(force=True) as batch:
        batch.put_file(str(payload_path), "/payload.json")

    job_cap = budget_left
    timeout_s = timeout_for_cap(job_cap, gpu_hourly, int(model["timeout_seconds"]))
    spec = {
        "model_id": model["model_id"],
        "revision": model["revision"],
        "model_dir": f"/weights/{model['key']}",
        "gpu": model["gpu"],
        "sample_size": plan["sample_size"],
        "hourly_usd": gpu_hourly,
        "job_cap_usd": job_cap * 0.95,
    }
    print(
        json.dumps(
            {
                "event": "launch_gpu",
                "gpu": model["gpu"],
                "job_cap_usd": spec["job_cap_usd"],
                "timeout_seconds": timeout_s,
                "one_query_estimate_usd": one_query,
            }
        ),
        flush=True,
    )
    infer_fn = infer.with_options(
        gpu=model["gpu"],
        cpu=float(model["cores"]),
        memory=int(model["mem_gib"] * 1024),
        timeout=timeout_s,
    )
    infer_call = infer_fn.spawn(spec)
    inference = None
    try:
        inference = wait_call(infer_call, timeout_s + 1200, "infer")
    except Exception as exc:
        record["infer_error"] = f"{type(exc).__name__}: {exc}"[:500]
        try:
            inference = read_saved.remote()
        except Exception as read_exc:
            record["read_error"] = f"{type(read_exc).__name__}: {read_exc}"[:300]
    if inference and inference.get("ok") and inference.get("queries"):
        _write_success(record, inference, score_result, seen_ids)
        return

    failed_spent = float((inference or {}).get("spent_usd_estimated") or 0)
    if record.get("infer_error") and failed_spent <= 0:
        failed_spent = timeout_s / 3600 * gpu_hourly
    record["first_attempt"] = {
        "model": model["model_id"],
        "error": record.get("infer_error") or (inference or {}).get("error"),
        "spent_usd_estimated": failed_spent,
    }
    later = tuple(item for item in FRONTIER_MODELS if item["key"] != model["key"] and _model_rank(item) > _model_rank(model))
    plan2 = choose_plan(
        rates,
        cap,
        full_sample=len(rows),
        models=later,
        sunk_usd=sunk + failed_spent,
        include_filter=False,
        include_prefetch=True,
    )
    if plan2["model"] is None:
        record["stop_reason"] = (
            "Frontier inference did not return a scored sample, and no cheaper model "
            f"fits under the remaining buffer (${cap - sunk - failed_spent:.2f})."
        )
        record["estimate_usd"] = sunk + failed_spent
        record["step_down_rejected"] = plan2["rejected"]
        _finish_billing(record, seen_ids, inference)
        write_json(RESULT_PATH, record)
        return
    model = plan2["model"]
    record["model"] = model["model_id"]
    record["revision"] = model["revision"]
    record["gpu"] = model["gpu"]
    record["step_down"] = True
    record["estimate_usd"] = plan2["estimate_usd"]
    if plan2["sample_size"] < len(rows):
        rows = rows[: plan2["sample_size"]]
    try:
        prefetch_result = wait_call(
            prefetch.spawn(model["model_id"], model["revision"], model["key"]),
            model["prefetch_minutes"] * 60 + 900,
            "prefetch-step-down",
        )
    except Exception as exc:
        record["stop_reason"] = f"step-down prefetch failed: {type(exc).__name__}"
        record["error"] = str(exc)[:500]
        _finish_billing(record, seen_ids, None)
        write_json(RESULT_PATH, record)
        return
    sunk += failed_spent + float(prefetch_result.get("elapsed_seconds") or 0) / 3600 * prefetch_hourly(rates)
    record["sunk_estimate_usd"] = sunk
    budget_left = cap - sunk
    gpu_hourly = model_hourly(model, rates, safety=1.0)
    one_query = (float(model["load_seconds"]) + float(model["seconds_per_query"])) / 3600 * gpu_hourly
    if one_query > budget_left or not prefetch_result.get("ok"):
        record["stop_reason"] = "step-down model does not fit one query under the remaining buffer"
        record["estimate_usd"] = sunk + one_query
        _finish_billing(record, seen_ids, None)
        write_json(RESULT_PATH, record)
        return
    try:
        inference = _spawn_infer(
            infer,
            read_saved,
            results_volume,
            model,
            rows,
            score_result,
            gpu_hourly,
            budget_left,
            record,
        )
    except Exception as exc:
        record["stop_reason"] = f"step-down launch failed: {type(exc).__name__}"
        record["error"] = str(exc)[:500]
        _finish_billing(record, seen_ids, None)
        write_json(RESULT_PATH, record)
        return
    if not inference or not inference.get("ok") or not inference.get("queries"):
        record["stop_reason"] = "step-down inference did not return a scored sample"
        record["inference_error"] = None if not inference else inference.get("error")
        _finish_billing(record, seen_ids, inference)
        write_json(RESULT_PATH, record)
        return
    _write_success(record, inference, score_result, seen_ids)


def _model_rank(model: dict) -> int:
    return [item["key"] for item in FRONTIER_MODELS].index(model["key"])


def _spawn_infer(infer, read_saved, results_volume, model, rows, score_result, gpu_hourly, budget_left, record) -> dict | None:
    tokenizer = load_tokenizer(model["model_id"], model["revision"])
    prompts = build_prompts(tokenizer, rows, score_result["rows"])
    payload_path = Path("/tmp/frontier_payload.json")
    payload_path.write_text(json.dumps(prompts))
    with results_volume.batch_upload(force=True) as batch:
        batch.put_file(str(payload_path), "/payload.json")
    timeout_s = timeout_for_cap(budget_left, gpu_hourly, int(model["timeout_seconds"]))
    spec = {
        "model_id": model["model_id"],
        "revision": model["revision"],
        "model_dir": f"/weights/{model['key']}",
        "gpu": model["gpu"],
        "sample_size": len(rows),
        "hourly_usd": gpu_hourly,
        "job_cap_usd": budget_left * 0.95,
    }
    print(
        json.dumps(
            {
                "event": "launch_gpu",
                "model": model["model_id"],
                "gpu": model["gpu"],
                "job_cap_usd": spec["job_cap_usd"],
                "timeout_seconds": timeout_s,
                "sample_size": len(rows),
            }
        ),
        flush=True,
    )
    infer_fn = infer.with_options(
        gpu=model["gpu"],
        cpu=float(model["cores"]),
        memory=int(float(model["mem_gib"]) * 1024),
        timeout=timeout_s,
    )
    try:
        return wait_call(infer_fn.spawn(spec), timeout_s + 1200, "infer")
    except Exception as exc:
        record["infer_error"] = f"{type(exc).__name__}: {exc}"[:500]
        try:
            return read_saved.remote()
        except Exception as read_exc:
            record["read_error"] = f"{type(read_exc).__name__}: {read_exc}"[:300]
            return None


def _elapsed_cost(prefetch_result: dict, prefetch_hour: float, score_result: dict, filter_hour: float) -> float:
    prefetch_usd = float(prefetch_result.get("elapsed_seconds") or 0) / 3600 * prefetch_hour
    filter_usd = float(score_result.get("elapsed_seconds") or 0) / 3600 * filter_hour
    return prefetch_usd + filter_usd


def _finish_billing(record: dict, seen_ids: set[str], inference: dict | None) -> None:
    cli_usd, breakdown, app_ids = _poll_cli(seen_ids)
    record["spend_usd"] = cli_usd
    record["cli_breakdown_usd"] = breakdown
    record["app_ids"] = app_ids
    if cli_usd is None:
        return
    append_ledger(
        {
            "date": date.today().isoformat(),
            "job": "frontier-loop",
            "app_id": ",".join(app_ids),
            "gpu": record.get("gpu"),
            "model_id": record.get("model"),
            "revision": record.get("revision"),
            "sample_size": record.get("sample_size") or 0,
            "trained": False,
            "launched": bool(record.get("launched")),
            "status": "stopped" if record.get("stop_reason") else "complete",
            "cli_app_usd": f"{cli_usd:.8f}",
            "cli_breakdown_usd": {key: f"{value:.8f}" for key, value in breakdown.items()},
            "estimate_usd": record.get("estimate_usd"),
            "remaining_credit_before_launch_usd": record.get("remaining_credit_before_launch_usd"),
            "note": "cli_app_usd is the sum of this app's resource lines from modal billing report --for today --show-resources --json. Not a workspace total.",
        }
    )


def _poll_cli(seen_ids: set[str]) -> tuple[float | None, dict, list[str]]:
    """Wait until this app's GPU line is stable, so a partial post is not the total."""
    deadline = time.time() + 12 * 60
    stable: tuple[float, dict, list[str]] | None = None
    repeats = 0
    while True:
        report = modal_json(["billing", "report", "--for", "today", "--show-resources", "--json"])
        rows = app_lines(report, APP_NAME, seen_ids)
        if rows:
            current = sum_lines(rows)
            resources = set(current[1])
            has_gpu = any(resource not in {"CPU", "Memory", "Network Egress"} for resource in resources)
            if stable is not None and abs(current[0] - stable[0]) < 1e-8:
                repeats += 1
            else:
                stable = current
                repeats = 0
            if has_gpu and repeats >= 1:
                return stable
        if time.time() > deadline:
            return stable if stable is not None else (None, {}, [])
        time.sleep(30)


def _write_success(record: dict, inference: dict, score_result: dict, seen_ids: set[str]) -> None:
    queries = inference["queries"]
    record["sample_size"] = len(queries)
    record["sample_shrunk"] = len(queries) < int(record.get("sample_size_planned") or len(queries))
    record["probe_query_seconds"] = inference.get("probe_query_seconds")
    record["load_seconds"] = inference.get("load_seconds")
    record["quantization"] = inference.get("quantization")
    record["vllm_version"] = inference.get("vllm_version")
    record["gpu_name"] = inference.get("gpu_name")
    record["infer_stop_reason"] = inference.get("stop_reason") or ""
    record["open_jev_commit"] = score_result.get("open_jev_commit")
    record["filter_base_revision"] = score_result.get("base_revision")
    record["tuned_2b"] = {
        "model_id": "Qwen/Qwen3.5-2B",
        "revision": score_result.get("base_revision"),
        "checkpoint": "toolret-h100-train:pass1/final",
    }
    record["original_2b"] = {
        "model_id": "ZefanCai/Open-Jev-2B",
        "base_model_id": "Qwen/Qwen3.5-2B",
        "base_revision": score_result.get("base_revision"),
        "open_jev_commit": score_result.get("open_jev_commit"),
    }
    # Probe-based estimate of the sample we then ran, recorded before the rest finished
    # inside the GPU job. The prelaunch estimate is already on the record.
    if inference.get("probe_query_seconds") and inference.get("hourly_usd"):
        probe_cost = (
            float(inference["load_seconds"]) + float(inference["probe_query_seconds"]) * len(queries)
        ) / 3600 * float(inference["hourly_usd"])
        record["probe_scaled_estimate_usd"] = probe_cost + float(record.get("sunk_estimate_usd") or 0)
    cli_usd, breakdown, app_ids = _poll_cli(seen_ids)
    if cli_usd is None:
        cli_usd = float(inference.get("spent_usd_estimated") or 0) + float(record.get("sunk_estimate_usd") or 0)
        breakdown = {}
        record["cost_source"] = "rate_estimate_cli_not_posted"
    else:
        record["cost_source"] = "modal_billing_report"
    record["spend_usd"] = cli_usd
    record["cli_breakdown_usd"] = breakdown
    record["app_ids"] = app_ids
    costs = allocate_arm_costs(cli_usd, inference["arm_seconds"])
    arms = {}
    for arm in ARM_ORDER:
        arms[arm] = {
            "label": LABELS[arm],
            "accuracy": 1.0 if arm == "full" else arm_accuracy(queries, arm),
            "cost_usd": costs[arm],
            "seconds": inference["arm_seconds"][arm],
        }
    record["arms"] = arms
    record["queries"] = [
        {
            "id": query["id"],
            "arms": {
                arm: {"called": query["arms"][arm]["called"], "seconds": query["arms"][arm]["seconds"]}
                for arm in ARM_ORDER
            },
        }
        for query in queries
    ]
    record["stop_reason"] = ""
    record["launched"] = True
    write_text(
        TRANSCRIPT_PATH,
        render_transcripts(queries, record["model"], record["revision"]),
    )
    write_both(
        [
            {"label": arms[arm]["label"], "cost_usd": arms[arm]["cost_usd"], "accuracy": arms[arm]["accuracy"]}
            for arm in ARM_ORDER
        ],
        f"{record['model']}  n={len(queries)}  k=10",
        GRAPH_REPO,
        GRAPH_MEDIA,
    )
    record["graph"] = str(GRAPH_REPO)
    record["graph_media"] = str(GRAPH_MEDIA)
    record["transcripts"] = str(TRANSCRIPT_PATH)
    write_json(RESULT_PATH, record)
    append_ledger(
        {
            "date": date.today().isoformat(),
            "job": "frontier-loop",
            "app_id": ",".join(app_ids),
            "gpu": record.get("gpu"),
            "gpu_name": inference.get("gpu_name"),
            "model_id": record.get("model"),
            "revision": record.get("revision"),
            "sample_size": len(queries),
            "trained": False,
            "launched": True,
            "status": "complete",
            "cli_app_usd": f"{cli_usd:.8f}",
            "cli_breakdown_usd": {key: f"{value:.8f}" for key, value in breakdown.items()},
            "estimate_usd": record.get("estimate_usd"),
            "remaining_credit_before_launch_usd": record.get("remaining_credit_before_launch_usd"),
            "note": (
                "cli_app_usd is this app only, from modal billing report --for today --show-resources --json."
                if record.get("cost_source") == "modal_billing_report"
                else "Billing report had not posted a stable GPU line. cli_app_usd is the in-job rate estimate plus the cheap stage, not a CLI total."
            ),
        }
    )
    print(
        json.dumps(
            {
                "event": "done",
                "model": record["model"],
                "revision": record["revision"],
                "sample_size": len(queries),
                "spend_usd": cli_usd,
                "arms": arms,
            }
        ),
        flush=True,
    )
