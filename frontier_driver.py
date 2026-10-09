"""Local driver for the frontier loop. Decides whether a GPU job can launch."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from frontier_budget import (
    ARM_ORDER,
    BUFFER_USD,
    CORE_ARMS,
    FRONTIER_MODELS,
    FULL_SAMPLE,
    SMALL_BUFFER_USD,
    STARTER_CREDIT_USD,
    TARGET_SAMPLE,
    allocate_arm_costs,
    choose_plan,
    filter_hourly,
    job_budget,
    loaded_hourly,
    model_hourly,
    prefetch_hourly,
    remaining_starter_credit,
    timeout_for_cap,
)
from frontier_menu import (
    ARM_LABELS,
    K,
    arm_accuracy,
    assign_call_names,
    build_prompts,
    core_done,
    has_arm,
    load_dev_ids,
    load_jsonl,
    merge_queries,
    render_transcripts,
    select_rows,
    write_text,
)
from hosted_jev import rank_query
from frontier_plot import write_both
from pi_loop import ENV_PATH, load_env_file

APP_NAME = "toolret-frontier-loop"
RESULT_PATH = Path("results/modal_frontier_loop.json")
TRANSCRIPT_PATH = Path("results/frontier_transcripts.md")
GRAPH_REPO = Path("results/pi-cost-accuracy.png")
GRAPH_MEDIA = Path("/cursor/stores/bc-c73881fc-461b-4a9f-9679-fb150ab43075/media/pi-cost-accuracy.png")
LEDGER_PATH = Path("ledger.jsonl")
PARTIAL_PATH = Path("results/frontier_72b_partial.json")
HOSTED_RANK_PATH = Path("results/hosted_jev_ranks.json")
DEV_JSONL = Path("data/dev_bm25_top50.jsonl")
DEV_IDS = Path("data/dev_2k.ids")
LABELS = ARM_LABELS
FRONTIER_72B = FRONTIER_MODELS[0]


def modal_bin() -> str:
    return shutil.which("modal") or str(Path.home() / ".local/bin/modal")


def _loads_cli_json(raw: str):
    text = (raw or "").strip()
    if not text or "no container" in text.lower():
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        values = []
        index = 0
        while index < len(text):
            while index < len(text) and text[index] not in "{[":
                index += 1
            if index >= len(text):
                break
            try:
                value, end = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                index += 1
                continue
            values.append(value)
            index = end
        if not values:
            raise
        return values[-1]


def modal_json(args: list[str]):
    """Call the Modal CLI. A local entrypoint sometimes races the CLI, so retry."""
    binary = str(Path.home() / ".local/bin/modal")
    last_error = "no attempt"
    for _ in range(4):
        completed = subprocess.run(
            [binary, *args, "--profile", "fostercole"],
            capture_output=True,
            text=True,
        )
        blob = completed.stdout or ""
        try:
            if completed.returncode != 0:
                raise RuntimeError(f"modal exited {completed.returncode}")
            return _loads_cli_json(blob)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}; stdout_len={len(blob)} stderr_len={len(completed.stderr or '')}"
            time.sleep(2)
    raise RuntimeError(f"modal {' '.join(args)} failed: {last_error}")


def _billing():
    """Same workspace billing service the CLI uses. The nested CLI races inside a local entrypoint."""
    import modal

    return modal.Workspace.from_context().billing


def frontier_containers() -> list[dict]:
    """Running frontier containers. Uses the API, because the nested CLI races inside an entrypoint."""
    import asyncio

    from modal.client import _Client
    from modal_proto import api_pb2

    async def _list() -> list[dict]:
        client = await _Client.from_env()
        response = await client._stub.TaskList(api_pb2.TaskListRequest(environment_name="main"))
        rows = []
        for task in response.tasks:
            rows.append(
                {
                    "container_id": task.task_id,
                    "app_id": task.app_id,
                    "app_name": task.app_description,
                    "start_time": str(task.started_at),
                }
            )
        return rows

    try:
        rows = asyncio.run(_list())
    except RuntimeError:
        rows = asyncio.get_event_loop().run_until_complete(_list())
    return [
        row
        for row in rows
        if row.get("app_name") == APP_NAME or "frontier" in json.dumps(row).lower()
    ]


def refuse_if_another_frontier(this_app_id: str | None) -> None:
    """Do not start a second frontier GPU while one from this session is up."""
    apps = modal_json(["app", "list", "--json"])
    containers = modal_json(["container", "list", "--json"])
    others = []
    for item in apps:
        if "frontier" not in str(item.get("description") or "").lower():
            continue
        if this_app_id and str(item.get("app_id")) == str(this_app_id):
            continue
        state = str(item.get("state") or "").lower()
        if state in {"stopped", "complete", "completed", "cancelled", "canceled", "failed"}:
            continue
        others.append(str(item.get("app_id")))
    busy = []
    for container in containers:
        if this_app_id and str(container.get("app_id")) == str(this_app_id):
            continue
        blob = json.dumps(container).lower()
        if "frontier" in blob:
            busy.append(str(container.get("container_id")))
    if others or busy:
        raise SystemExit(f"another frontier run is already active: apps={others} containers={busy}")


def live_rates() -> dict:
    rates = _billing().rates()
    needed = [
        "cpu_hour_cost",
        "mem_gib_hour_cost",
        "gpu_hour_cost_h100",
        "gpu_hour_cost_l4",
        "gpu_hour_cost_l40s",
        "gpu_hour_cost_a100_80gb",
    ]
    missing = [key for key in needed if key not in rates]
    if missing:
        raise RuntimeError("billing rates missing " + ", ".join(missing))
    return {key: float(rates[key]) for key in needed}


def live_summary() -> dict:
    summary = _billing().summary("this month")
    adjustments = {str(key).lower().replace(" ", "_"): value for key, value in summary.adjustments.items()}
    return {
        "metered_cost": float(summary.metered_cost),
        "credits_applied": abs(float(adjustments.get("credits", 0))),
        "billed_cost": float(summary.billed_cost),
    }


def today_report() -> list[dict]:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # The report drops a partial trailing interval, so end at the next midnight.
    rows = []
    for item in _billing().report(start=start, end=start + timedelta(days=1), resolution="d"):
        resources = dict(item.cost_by_resource or {})
        if not resources:
            rows.append(
                {
                    "object_id": item.object_id,
                    "description": item.description,
                    "resource": "total",
                    "cost": float(item.cost),
                }
            )
            continue
        for resource, cost in resources.items():
            rows.append(
                {
                    "object_id": item.object_id,
                    "description": item.description,
                    "resource": resource,
                    "cost": float(cost),
                }
            )
    return rows


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


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def median_core_query_seconds(queries: list[dict]) -> float:
    """Median generation time of the four non-hosted arms. Ignores a one-arm probe."""
    samples = []
    for query in queries:
        arms = query.get("arms") or {}
        if not all(arm in arms for arm in CORE_ARMS):
            continue
        samples.append(sum(float((arms[arm] or {}).get("seconds") or 0) for arm in CORE_ARMS))
    if not samples:
        return 0.0
    samples.sort()
    return float(samples[len(samples) // 2])


def _core_queries(payload: dict) -> list[dict]:
    model = str(payload.get("model") or payload.get("model_id") or "")
    if payload.get("queries") and "72B" not in model and model not in {"", "None"}:
        return []
    if payload.get("queries") and model and "72B" not in model:
        return []
    return [query for query in payload.get("queries") or [] if isinstance(query, dict) and query.get("id") and core_done(query)]


def _prefer_saved(local_queries: list[dict], remote_queries: list[dict]) -> list[dict]:
    """Keep the copy that has more finished pairs, then the one that still has model text."""

    def rank(queries: list[dict]) -> tuple[int, int]:
        text = 0
        for query in queries:
            for item in (query.get("arms") or {}).values():
                if isinstance(item, dict) and item.get("output"):
                    text += 1
        return len(queries), text

    return local_queries if rank(local_queries) >= rank(remote_queries) else remote_queries


def execute(prefetch, score_sample, infer, read_saved, results_volume) -> None:
    self_started = time.time()
    # The container list is checked in the shell before this entrypoint starts.
    # Calling it here deadlocks the Modal client, so it does not run again until the GPU gate.
    summary = live_summary()
    remaining = remaining_starter_credit(summary["metered_cost"], summary["credits_applied"])
    # Live remaining Starter balance. Not $7, and not the old $1.14 holdback.
    cap = job_budget(remaining)
    hosted_key = load_env_file(ENV_PATH).get("JEV_API_KEY", "").strip()
    hosted = len(hosted_key) > 0
    record = _base_record(summary, remaining, cap, hosted)
    print(
        json.dumps(
            {
                "event": "balance",
                "remaining_credit_usd": remaining,
                "spend_cap_usd": cap,
                "metered_cost_usd": summary["metered_cost"],
                "credits_applied_usd": summary["credits_applied"],
                "billed_cost_usd": summary["billed_cost"],
                "hosted_jev_key_nonempty": hosted,
                "cap_rule": "live_remaining_balance",
            }
        ),
        flush=True,
    )
    local_saved = _read_json(RESULT_PATH)
    partial_saved = _read_json(PARTIAL_PATH)
    remote_saved: dict = {}
    try:
        remote_saved = read_saved.remote() or {}
    except Exception as exc:
        record["saved_read_error"] = f"{type(exc).__name__}"
    saved_queries = _prefer_saved(_core_queries(local_saved), _core_queries(remote_saved))
    saved_queries = _prefer_saved(saved_queries, _core_queries(partial_saved))
    if not saved_queries and local_saved.get("queries"):
        saved_queries = [query for query in local_saved["queries"] if isinstance(query, dict) and core_done(query)]
    record["resumed_query_ids"] = [query["id"] for query in saved_queries]
    local_done = _core_queries(local_saved)
    same_local = {query["id"] for query in local_done} == {query["id"] for query in saved_queries} and bool(saved_queries)
    if same_local:
        record["prior_spend_usd"] = float(local_saved.get("spend_usd") or 0)
    else:
        record["prior_spend_usd"] = float(remote_saved.get("spent_usd_estimated") or 0) if saved_queries else 0.0
    if saved_queries and record["prior_spend_usd"] and not local_saved.get("arms"):
        seconds: dict[str, float] = {}
        for query in saved_queries:
            for arm, item in (query.get("arms") or {}).items():
                seconds[arm] = seconds.get(arm, 0.0) + float((item or {}).get("seconds") or 0)
        if seconds:
            record["prior_arm_costs"] = allocate_arm_costs(record["prior_spend_usd"], seconds)
    record["hosted_jev"] = {
        "in_design": False,
        "paused": not hosted,
        "called": False,
        "included_in_graph": False,
        "reason": "" if hosted else "JEV_API_KEY in /workspace/.env is empty. The hosted Jev arm was not called.",
    }
    record["hosted_jev_reason"] = record["hosted_jev"]["reason"]
    record["hosted_jev_included"] = False
    if not hosted:
        record["stop_reason"] = record["hosted_jev"]["reason"]
        write_json(RESULT_PATH, record)
        print(json.dumps({"event": "stop", "reason": record["stop_reason"]}), flush=True)
        return
    if cap <= 0:
        record["paused_for_balance"] = True
        record["stop_reason"] = f"Remaining Starter credit is ${remaining:.2f}. Checkpointed without a GPU call."
        _write_from_saved(record, saved_queries)
        return

    rates = live_rates()
    measured = {}
    for candidate in (remote_saved, partial_saved, local_saved):
        if candidate.get("probe_query_seconds") and candidate.get("load_seconds"):
            measured = candidate
            break
    observed = median_core_query_seconds(saved_queries)
    if observed > float(measured.get("probe_query_seconds") or 0):
        measured = dict(measured)
        measured["probe_query_seconds"] = observed
        measured.setdefault("load_seconds", 73.0)
    model = dict(FRONTIER_72B)
    if measured.get("probe_query_seconds") and measured.get("load_seconds"):
        model["load_seconds"] = max(60.0, float(measured["load_seconds"]) * 1.25)
        model["seconds_per_query"] = max(4.0, float(measured["probe_query_seconds"]) * 1.25 * 5 / 4)
    finished_ids = {query["id"] for query in saved_queries}
    need = max(0, TARGET_SAMPLE - len(finished_ids))
    plan = choose_plan(
        rates,
        cap,
        need if need else 1,
        models=(model,),
        include_filter=False,
        include_prefetch=False,
    )
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
    if plan["model"] is None and need:
        record["paused_for_balance"] = True
        record["stop_reason"] = (
            f"One Qwen2.5-72B query does not fit the live remaining balance (${cap:.2f}). Checkpointed."
        )
        record["step_down_rejected"] = plan["rejected"]
        _write_from_saved(record, saved_queries)
        return

    model = plan["model"] or model
    record["model"] = "Qwen/Qwen2.5-72B-Instruct"
    record["weights"] = FRONTIER_72B["model_id"]
    record["revision"] = FRONTIER_72B["revision"]
    record["gpu"] = FRONTIER_72B["gpu"]
    record["quantization"] = "4-bit"
    before_report = today_report()
    seen_ids = {str(row["object_id"]) for row in before_report if row.get("description") == APP_NAME}
    if local_saved.get("arms"):
        record["prior_arm_costs"] = {
            arm: float(
                (local_saved["arms"].get(arm) or {}).get("cost_usd")
                or (local_saved["arms"].get(arm) or {}).get("modal_cost_usd")
                or 0
            )
            for arm in local_saved["arms"]
        }

    dev_ids = load_dev_ids(DEV_IDS)
    pool = select_rows(load_jsonl(DEV_JSONL), dev_ids, TARGET_SAMPLE, seed=0)
    saved_by_id = {query["id"]: query for query in saved_queries}
    if need:
        new_rows = [row for row in pool if row["id"] not in finished_ids][: int(plan["sample_size"] or 0)]
    else:
        new_rows = []
    backfill = [
        row
        for row in pool
        if row["id"] in saved_by_id and not has_arm(saved_by_id[row["id"]], "hosted")
    ]
    rows = backfill + new_rows
    arms_for = {row["id"]: ARM_ORDER for row in new_rows}
    arms_for.update({row["id"]: ("hosted",) for row in backfill})
    record["query_ids"] = [row["id"] for row in pool]
    record["new_query_ids"] = [row["id"] for row in new_rows]
    record["hosted_backfill_ids"] = [row["id"] for row in backfill]
    record["sample_size_planned"] = len(rows)
    record["prior_queries"] = saved_queries
    if not rows:
        record["stop_reason"] = ""
        record["paused_for_balance"] = False
        _write_from_saved(record, saved_queries)
        return
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
    prefetch_call = prefetch.spawn(FRONTIER_72B["model_id"], FRONTIER_72B["revision"], FRONTIER_72B["key"])
    score_call = score_sample.spawn([row["id"] for row in new_rows]) if new_rows else None
    try:
        prefetch_result = wait_call(prefetch_call, FRONTIER_72B["prefetch_minutes"] * 60 + 900, "prefetch")
        score_result = (
            wait_call(score_call, 900, "score")
            if score_call is not None
            else {"ok": True, "rows": {}, "elapsed_seconds": 0, "gpu_name": ""}
        )
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

    score_hour = filter_hourly(rates, safety=1.0)
    if "H100" in str(score_result.get("gpu_name") or ""):
        score_hour = loaded_hourly(
            rates["gpu_hour_cost_h100"],
            8,
            32,
            rates["cpu_hour_cost"],
            rates["mem_gib_hour_cost"],
        )
    sunk = _elapsed_cost(prefetch_result, prefetch_hourly(rates, safety=1.0), score_result, score_hour)
    record["sunk_estimate_usd"] = sunk
    fresh = live_summary()
    fresh_remaining = remaining_starter_credit(fresh["metered_cost"], fresh["credits_applied"])
    posted = max(0.0, remaining - fresh_remaining)
    unbilled = max(0.0, sunk - posted)
    budget_left = max(0.0, fresh_remaining - unbilled)
    record["remaining_credit_before_gpu_usd"] = fresh_remaining
    record["buffer_usd"] = 0.0
    record["spend_cap_usd"] = fresh_remaining
    gpu_hourly = model_hourly(FRONTIER_72B, rates, safety=1.0)
    one_query = (float(model.get("load_seconds") or 0) + float(model.get("seconds_per_query") or 0)) / 3600 * gpu_hourly
    print(
        json.dumps(
            {
                "event": "recheck",
                "remaining_credit_usd": fresh_remaining,
                "metered_cost_usd": fresh["metered_cost"],
                "gpu_budget_usd": budget_left,
                "one_query_estimate_usd": one_query,
            }
        ),
        flush=True,
    )
    if one_query > budget_left:
        record["paused_for_balance"] = True
        record["stop_reason"] = (
            f"After the cheap stage, one 72B query (${one_query:.2f}) does not fit the live "
            f"remaining balance (${fresh_remaining:.2f}). Checkpointed."
        )
        record["estimate_usd"] = sunk + one_query
        _finish_billing(record, seen_ids, None)
        _write_from_saved(record, saved_queries)
        return
    # Score and prefetch have returned. Give those containers a moment to exit
    # before the inference GPU starts, so two GPUs do not overlap.
    time.sleep(8)

    try:
        hosted_menus, hosted_note = _rank_hosted(rows, hosted_key)
        record["hosted_jev"] = hosted_note
        record["hosted_jev_reason"] = hosted_note["reason"]
        kept = []
        for row in rows:
            wanted = tuple(arm for arm in arms_for[row["id"]] if arm != "hosted" or row["id"] in hosted_menus)
            if not wanted:
                continue
            arms_for[row["id"]] = wanted
            kept.append(row)
        rows = kept
        if not rows:
            record["stop_reason"] = "Hosted Jev did not return a top-10 menu, so no GPU call was made."
            _finish_billing(record, seen_ids, None)
            _write_from_saved(record, saved_queries)
            return
        tokenizer = load_tokenizer(FRONTIER_72B["model_id"], FRONTIER_72B["revision"])
        prompts = build_prompts(tokenizer, rows, score_result["rows"], hosted_menus, arms_for)
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
        "sample_size": len(rows),
        "hourly_usd": gpu_hourly,
        "job_cap_usd": job_cap,
        "seconds_per_query_hint": float(measured.get("probe_query_seconds") or 0),
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
        memory=int(float(model["mem_gib"]) * 1024),
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
    record["first_attempt"] = {
        "model": FRONTIER_72B["model_id"],
        "error": record.get("infer_error") or (inference or {}).get("error"),
        "errors": (inference or {}).get("errors"),
        "spent_usd_estimated": failed_spent,
    }
    record["paused_for_balance"] = True
    record["stop_reason"] = "72B inference stopped before a scored sample. Checkpointed. No cheaper model was started."
    partial = merge_queries(saved_queries, (inference or {}).get("queries") or [])
    _finish_billing(record, seen_ids, inference)
    if partial:
        record["prior_queries"] = []
        inference_partial = dict(inference or {})
        inference_partial["queries"] = partial
        inference_partial["arm_seconds"] = (inference or {}).get("arm_seconds") or {}
        inference_partial["ok"] = True
        _write_success(record, inference_partial, score_result, seen_ids)
        return
    _write_from_saved(record, saved_queries)


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
        "job_cap_usd": budget_left,
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
        report = today_report()
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


def _container_epoch(container: dict) -> float:
    raw = str(container.get("start_time") or "")
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return 0.0


def _menu_from_names(named: list[dict], names: list) -> list[dict]:
    by_call = {tool["call_name"]: tool for tool in named}
    by_name = {str(tool.get("name") or ""): tool for tool in named}
    menu = []
    for name in names:
        if isinstance(name, dict):
            name = name.get("call_name") or name.get("name")
        tool = by_call.get(name) or by_name.get(str(name))
        if tool is not None and tool not in menu:
            menu.append(tool)
    return menu[:K]


def _rank_hosted(rows: list[dict], api_key: str) -> tuple[dict, dict]:
    menus: dict[str, list] = {}
    errors = []
    called = 0
    cached = _read_json(HOSTED_RANK_PATH).get("rows") or {}
    for row in rows:
        named = assign_call_names(row["candidates"])
        prior = cached.get(row["id"]) if isinstance(cached, dict) else None
        if isinstance(prior, dict) and prior.get("ok") and prior.get("top"):
            menu = _menu_from_names(named, prior["top"])
            if len(menu) >= K:
                menus[row["id"]] = menu
                called += 1
                continue
        ranked = rank_query(row["query"], named, api_key)
        called += 1
        if not ranked.get("ok"):
            errors.append({"id": row["id"], "status": ranked.get("status"), "error": ranked.get("error") or "failed"})
            continue
        by_name = {tool["call_name"]: tool for tool in named}
        menu = []
        for item in ranked.get("top") or []:
            tool = by_name.get(item.get("call_name"))
            if tool is not None:
                menu.append(tool)
        if len(menu) >= K:
            menus[row["id"]] = menu[:K]
        else:
            errors.append({"id": row["id"], "status": ranked.get("status"), "error": "short menu"})
    note = {
        "in_design": False,
        "paused": called == 0 or len(menus) == 0,
        "called": called > 0,
        "included_in_graph": False,
        "queries": called,
        "ranked": len(menus),
        "errors": errors[:8],
        "reason": "" if menus else "Hosted Jev did not return a 10-tool menu.",
    }
    return menus, note


def _emit_artifacts(record: dict, queries: list[dict], costs: dict) -> None:
    record["model"] = "Qwen/Qwen2.5-72B-Instruct"
    record["revision"] = record.get("revision") or FRONTIER_72B["revision"]
    write_text(TRANSCRIPT_PATH, render_transcripts(queries, record["model"], record["revision"]))
    points = []
    for arm in ARM_ORDER:
        item = (record.get("arms") or {}).get(arm)
        if not item:
            continue
        points.append(
            {
                "label": item["label"],
                "cost_usd": float(item.get("cost_usd") if item.get("cost_usd") is not None else costs.get(arm) or 0),
                "accuracy": float(item["accuracy"]),
            }
        )
    if points:
        write_both(points, f"{record['model']}  n={len(queries)}  k=10", GRAPH_REPO, GRAPH_MEDIA)
    record["graph"] = str(GRAPH_REPO)
    record["graph_media"] = str(GRAPH_MEDIA)
    record["transcripts"] = str(TRANSCRIPT_PATH)


def _write_from_saved(record: dict, queries: list[dict]) -> None:
    record["queries"] = queries
    record["sample_size"] = len(queries)
    record["model"] = "Qwen/Qwen2.5-72B-Instruct"
    record["revision"] = record.get("revision") or FRONTIER_72B["revision"]
    record["paused_for_balance"] = bool(record.get("paused_for_balance") or record.get("stop_reason"))
    arms = {}
    for arm in ARM_ORDER:
        present = [query for query in queries if has_arm(query, "full") and has_arm(query, arm)]
        if not present:
            continue
        arms[arm] = {
            "label": LABELS[arm],
            "accuracy": 1.0 if arm == "full" else arm_accuracy(present, arm),
            "cost_usd": float((record.get("prior_arm_costs") or {}).get(arm) or 0),
            "n": len(present),
        }
    record["arms"] = arms
    if "hosted" in arms:
        record["hosted_jev_included"] = True
    if queries:
        _emit_artifacts(record, queries, {arm: arms[arm]["cost_usd"] for arm in arms})
        write_json(RESULT_PATH, record)
    else:
        write_json(RESULT_PATH, record)
    print(json.dumps({"event": "checkpoint", "reason": record.get("stop_reason"), "sample_size": len(queries)}), flush=True)


def _write_success(record: dict, inference: dict, score_result: dict, seen_ids: set[str]) -> None:
    queries = merge_queries(record.get("prior_queries") or [], inference["queries"])
    record.pop("prior_queries", None)
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
    prior_spend = float(record.get("prior_spend_usd") or 0)
    record["this_app_spend_usd"] = cli_usd
    record["spend_usd"] = cli_usd + prior_spend
    record["cli_breakdown_usd"] = breakdown
    record["app_ids"] = app_ids
    if app_ids:
        record["app_url"] = f"https://modal.com/apps/fostercole/main/{app_ids[0]}"
    record["weights"] = FRONTIER_72B["model_id"]
    record["model"] = "Qwen/Qwen2.5-72B-Instruct"
    record["revision"] = record.get("revision") or FRONTIER_72B["revision"]
    record["vllm_quantization"] = inference.get("quantization")
    record["quantization"] = "4-bit"
    record["stopped_at_credit_wall"] = (inference.get("stop_reason") or "") in {
        "stopped_before_cap",
        "shrunk_after_probe",
        "partial_query",
        "time_backstop",
    }
    if record["stopped_at_credit_wall"] or len(queries) < TARGET_SAMPLE:
        record["paused_for_balance"] = bool(record["stopped_at_credit_wall"])
    seconds = dict(inference.get("arm_seconds") or {})
    if not seconds:
        seconds = {"full": 1.0}
    new_costs = allocate_arm_costs(cli_usd, seconds)
    prior_costs = record.get("prior_arm_costs") or {}
    costs = {arm: float(prior_costs.get(arm) or 0) + float(new_costs.get(arm) or 0) for arm in set(prior_costs) | set(new_costs) | set(ARM_ORDER)}
    arms = {}
    for arm in ARM_ORDER:
        present = [query for query in queries if has_arm(query, "full") and has_arm(query, arm)]
        if not present:
            continue
        arms[arm] = {
            "label": LABELS[arm],
            "accuracy": 1.0 if arm == "full" else arm_accuracy(present, arm),
            "cost_usd": float(costs.get(arm) or 0),
            "seconds": float(seconds.get(arm) or 0),
            "n": len(present),
        }
    record["arms"] = arms
    if "hosted" in arms:
        record["hosted_jev_included"] = True
        record["hosted_jev"]["included_in_graph"] = True
        record["hosted_jev"]["paused"] = False
    record["queries"] = queries
    if record.get("stopped_at_credit_wall") and not record.get("stop_reason"):
        record["stop_reason"] = "Stopped at the live remaining balance and checkpointed."
        record["paused_for_balance"] = True
    elif not record.get("stop_reason"):
        record["stop_reason"] = ""
    record["launched"] = True
    _emit_artifacts(record, queries, costs)
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
