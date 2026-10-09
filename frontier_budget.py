"""Credit gate for the Modal frontier loop. No GPU and no network."""

from __future__ import annotations

STARTER_CREDIT_USD = 30.0
BUFFER_USD = 1.0
# Leave this on the account so a query cannot finish the balance at zero.
SMALL_BUFFER_USD = 0.40
COMPARISON_CEILING_USD = 7.0
MIN_REMAINING_TO_LAUNCH_USD = 2.0
FULL_SAMPLE = 90
# Published-rate estimates are padded because the probe has not run yet.
RATE_SAFETY = 1.05

# Pessimistic load and per-query times. The 1-query probe replaces the
# per-query number before the rest of the sample runs.
FRONTIER_MODELS = (
    {
        "key": "qwen72b-awq",
        "model_id": "Qwen/Qwen2.5-72B-Instruct-AWQ",
        "revision": "698703eae6604af048a3d2f509995dc302088217",
        "gpu": "H100",
        "rate_key": "gpu_hour_cost_h100",
        "cores": 8,
        "mem_gib": 48,
        "load_seconds": 240,
        "seconds_per_query": 20,
        "prefetch_minutes": 20,
        "timeout_seconds": 2400,
    },
    {
        "key": "qwen32b-awq",
        "model_id": "Qwen/Qwen2.5-32B-Instruct-AWQ",
        "revision": "5c7cb76a268fc6cfbb9c4777eb24ba6e27f9ee6c",
        "gpu": "L40S",
        "rate_key": "gpu_hour_cost_l40s",
        "cores": 4,
        "mem_gib": 48,
        "load_seconds": 420,
        "seconds_per_query": 25,
        "prefetch_minutes": 12,
        "timeout_seconds": 1500,
    },
    {
        "key": "qwen14b-awq",
        "model_id": "Qwen/Qwen2.5-14B-Instruct-AWQ",
        "revision": "539535859b135b0244c91f3e59816150c8056698",
        "gpu": "L4",
        "rate_key": "gpu_hour_cost_l4",
        "cores": 4,
        "mem_gib": 24,
        "load_seconds": 240,
        "seconds_per_query": 20,
        "prefetch_minutes": 8,
        "timeout_seconds": 1800,
    },
    {
        "key": "qwen7b-awq",
        "model_id": "Qwen/Qwen2.5-7B-Instruct-AWQ",
        "revision": "b25037543e9394b818fdfca67ab2a00ecc7dd641",
        "gpu": "L4",
        "rate_key": "gpu_hour_cost_l4",
        "cores": 4,
        "mem_gib": 16,
        "load_seconds": 180,
        "seconds_per_query": 12,
        "prefetch_minutes": 6,
        "timeout_seconds": 1800,
    },
)

FILTER_SCORE_FIXED_SECONDS = 240
FILTER_SCORE_SECONDS_PER_ROW = 6
ARM_ORDER = ("full", "bm25", "original", "tuned", "hosted")
TARGET_SAMPLE = 30
# Arms already produced for a saved pair. The hosted menu is added later.
CORE_ARMS = ("full", "bm25", "original", "tuned")


def remaining_starter_credit(
    metered_cost: float,
    credits_applied: float,
    starter: float = STARTER_CREDIT_USD,
) -> float:
    """Dollars of the monthly Starter grant still unused.

    The billing summary reports credits as a negative adjustment equal to the
    amount applied, which is not the remaining grant. Remaining is the grant
    minus the larger of metered cost and credits already applied.
    """
    used = max(float(metered_cost), abs(float(credits_applied)))
    return float(starter) - used


def may_launch(remaining_credit: float, minimum: float = MIN_REMAINING_TO_LAUNCH_USD) -> bool:
    return float(remaining_credit) >= float(minimum)


def spend_cap(remaining_credit: float, buffer_usd: float = BUFFER_USD) -> float:
    return float(remaining_credit) - float(buffer_usd)


def comparison_cap(
    remaining_credit: float,
    already_spent_usd: float = 0.0,
    ceiling_usd: float = COMPARISON_CEILING_USD,
    buffer_usd: float = SMALL_BUFFER_USD,
) -> float:
    """Dollars the next GPU job may spend.

    The account keeps a small buffer. The comparison itself also stops at the
    ceiling, counting Modal dollars already spent on it.
    """
    room = float(remaining_credit) - float(buffer_usd)
    ceiling_left = float(ceiling_usd) - float(already_spent_usd)
    return max(0.0, min(room, ceiling_left))


def affordable_sample(
    cap_usd: float,
    hourly_usd: float,
    load_seconds: float,
    seconds_per_new_query: float,
    hosted_tail_seconds: float,
    score_fixed_seconds: float,
    score_seconds_per_row: float,
    already_done: int,
    full_sample: int,
) -> int:
    """Largest total sample, including rows already scored, that fits cap_usd."""
    best = int(already_done)
    done = int(already_done)
    for total in range(done, int(full_sample) + 1):
        new = total - done
        score_s = 0.0 if new == 0 else float(score_fixed_seconds) + float(score_seconds_per_row) * new
        infer_s = float(load_seconds) + float(seconds_per_new_query) * new + float(hosted_tail_seconds)
        cost = (score_s + infer_s) / 3600.0 * float(hourly_usd)
        if cost <= float(cap_usd):
            best = total
        else:
            break
    return best


def pending_items(items: list[dict], done_pairs: set[tuple[str, str]]) -> list[dict]:
    """Drop example/arm pairs that already have a frontier call."""
    return [item for item in items if (item["id"], item["arm"]) not in done_pairs]


def job_budget(remaining_credit: float) -> float:
    """What the next GPU launch may spend: the live remaining Starter balance.

    A one-dollar or two-dollar holdback is what pinned earlier launches near
    $1.14. The launch uses the live number, and the running job checkpoints
    if that balance runs out.
    """
    return max(0.0, float(remaining_credit))


def loaded_hourly(
    gpu_hour: float,
    cores: float,
    mem_gib: float,
    cpu_hour: float,
    mem_gib_hour: float,
) -> float:
    return float(gpu_hour) + float(cores) * float(cpu_hour) + float(mem_gib) * float(mem_gib_hour)


def model_hourly(model: dict, rates: dict, safety: float = RATE_SAFETY) -> float:
    return loaded_hourly(
        float(rates[model["rate_key"]]),
        float(model["cores"]),
        float(model["mem_gib"]),
        float(rates["cpu_hour_cost"]),
        float(rates["mem_gib_hour_cost"]),
    ) * float(safety)


def prefetch_hourly(rates: dict, safety: float = RATE_SAFETY) -> float:
    return loaded_hourly(0.0, 2, 16, float(rates["cpu_hour_cost"]), float(rates["mem_gib_hour_cost"])) * float(
        safety
    )


def filter_hourly(rates: dict, safety: float = RATE_SAFETY) -> float:
    # Same shape as the finished L4 dev pass: 8 cores and 32 GiB.
    return loaded_hourly(
        float(rates["gpu_hour_cost_l4"]),
        8,
        32,
        float(rates["cpu_hour_cost"]),
        float(rates["mem_gib_hour_cost"]),
    ) * float(safety)


def filter_cost(n_rows: int, rates: dict, safety: float = RATE_SAFETY) -> float:
    seconds = FILTER_SCORE_FIXED_SECONDS + FILTER_SCORE_SECONDS_PER_ROW * int(n_rows)
    return seconds / 3600 * filter_hourly(rates, safety)


def prefetch_cost(model: dict, rates: dict, safety: float = RATE_SAFETY) -> float:
    return float(model["prefetch_minutes"]) / 60 * prefetch_hourly(rates, safety)


def gpu_cost(model: dict, n_queries: int, rates: dict, safety: float = RATE_SAFETY) -> float:
    seconds = float(model["load_seconds"]) + float(model["seconds_per_query"]) * int(n_queries)
    return seconds / 3600 * model_hourly(model, rates, safety)


def plan_cost(
    model: dict,
    n_queries: int,
    rates: dict,
    sunk_usd: float = 0.0,
    include_filter: bool = True,
    include_prefetch: bool = True,
    safety: float = RATE_SAFETY,
) -> float:
    total = float(sunk_usd) + gpu_cost(model, n_queries, rates, safety)
    if include_prefetch:
        total += prefetch_cost(model, rates, safety)
    if include_filter:
        total += filter_cost(n_queries, rates, safety)
    return total


def choose_plan(
    rates: dict,
    spend_cap_usd: float,
    full_sample: int = FULL_SAMPLE,
    models: tuple[dict, ...] = FRONTIER_MODELS,
    sunk_usd: float = 0.0,
    include_filter: bool = True,
    include_prefetch: bool = True,
    safety: float = RATE_SAFETY,
) -> dict:
    """Pick the strongest model whose 1-query estimate fits, then shrink n.

    Returns a plan dict. `model` is None when nothing fits under the cap.
    """
    cap = float(spend_cap_usd)
    rejected = []
    for model in models:
        one = plan_cost(
            model,
            1,
            rates,
            sunk_usd=sunk_usd,
            include_filter=include_filter,
            include_prefetch=include_prefetch,
            safety=safety,
        )
        if one > cap:
            rejected.append({"key": model["key"], "one_query_estimate_usd": one, "reason": "one_query_over_cap"})
            continue
        best = 1
        lo, hi = 1, int(full_sample)
        while lo <= hi:
            mid = (lo + hi) // 2
            cost = plan_cost(
                model,
                mid,
                rates,
                sunk_usd=sunk_usd,
                include_filter=include_filter,
                include_prefetch=include_prefetch,
                safety=safety,
            )
            if cost <= cap:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        estimate = plan_cost(
            model,
            best,
            rates,
            sunk_usd=sunk_usd,
            include_filter=include_filter,
            include_prefetch=include_prefetch,
            safety=safety,
        )
        return {
            "model": model,
            "sample_size": best,
            "estimate_usd": estimate,
            "one_query_estimate_usd": one,
            "shrunk": best < int(full_sample),
            "rejected": rejected,
        }
    return {
        "model": None,
        "sample_size": 0,
        "estimate_usd": None,
        "one_query_estimate_usd": None,
        "shrunk": False,
        "rejected": rejected,
    }


def shrink_after_probe(
    sample_planned: int,
    spent_usd: float,
    seconds_per_query: float,
    hourly_usd: float,
    job_cap_usd: float,
    safety: float = 1.25,
) -> int:
    """How many queries to finish, including the probe, without crossing job_cap."""
    planned = max(1, int(sample_planned))
    per = max(0.0, float(seconds_per_query)) / 3600 * float(hourly_usd) * float(safety)
    money_left = float(job_cap_usd) - float(spent_usd)
    if per <= 0:
        extra = planned - 1
    else:
        extra = int(money_left // per)
    extra = max(0, extra)
    return min(planned, 1 + extra)


def allocate_arm_costs(cli_usd: float, arm_seconds: dict[str, float]) -> dict[str, float]:
    total = sum(float(value) for value in arm_seconds.values())
    if total <= 0:
        share = float(cli_usd) / max(1, len(arm_seconds))
        return {key: share for key in arm_seconds}
    return {key: float(cli_usd) * (float(value) / total) for key, value in arm_seconds.items()}


def timeout_for_cap(job_cap_usd: float, hourly_usd: float, ceiling_seconds: int) -> int:
    if hourly_usd <= 0:
        return 60
    priced = int(float(job_cap_usd) / float(hourly_usd) * 3600)
    return max(60, min(int(ceiling_seconds), priced))
