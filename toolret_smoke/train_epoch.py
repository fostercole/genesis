"""One QLoRA epoch on the existing Open-Jev-2B adapter. Runs on the H100."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from toolret_smoke.loss import toolret_nll_torch
from toolret_smoke.score_rows import _encoded_len, candidate_content, fit_tool_text

EFFECTIVE_BATCH = 16
TRAIN_ROWS = 50_000
MEASURE_STEPS = 4
WARMUP_FRACTION = 0.03
BASE_LR = 1e-4
HEAD_LR = 1e-4
RESTART_LR = 2e-5
# Live Modal rates checked Oct 8, 2026.
H100_HOUR = 3.95
CPU_HOUR = 0.0473
MEM_GIB_HOUR = 0.008
CORES = 8
MEM_GIB = 32
ALL_IN_PER_SEC = (H100_HOUR + CORES * CPU_HOUR + MEM_GIB * MEM_GIB_HOUR) / 3600
LAUNCH_MARGIN = 1.15
STOP_USD = 28.0
CUTOFF_USD = 29.0


def all_in_usd(elapsed_seconds: float) -> float:
    return elapsed_seconds * ALL_IN_PER_SEC


def lr_multiplier(step: int, total_steps: int, warmup_steps: int) -> float:
    if step < warmup_steps:
        return (step + 1) / max(1, warmup_steps)
    span = max(1, total_steps - warmup_steps)
    return max(0.0, 1.0 - ((step - warmup_steps) / span))


def _options(tokenizer, row: dict, max_length: int) -> tuple[list[str], int]:
    options = []
    tools = list(row["positives"]) + list(row["negatives"])
    for tool in tools:
        text = tool.get("text") or ""
        if not text:
            raise ValueError(f"{row['id']} has an empty tool")
        if _encoded_len(tokenizer, candidate_content(row["query"], row["instruction"], text)) <= max_length:
            options.append(text)
            continue
        fitted = {
            "name": tool.get("name") or "",
            "description": text,
            "parameters": [],
        }
        options.append(fit_tool_text(tokenizer, row["query"], row["instruction"], fitted, max_length))
    return options, len(row["positives"])


def _record(row: dict, options: list[str]) -> dict:
    return {
        "id": row["id"],
        "state": row["query"],
        "kind": "choice",
        "question": row["instruction"] or "",
        "options": options,
    }


def microbatch_loss(model, rows: list[dict], prepared: list[tuple[list[str], int]]):
    records = [_record(row, options) for row, (options, _) in zip(rows, prepared)]
    scores = model(records)
    losses = [toolret_nll_torch(values, n_positive) for values, (_, n_positive) in zip(scores, prepared)]
    return sum(losses) / len(losses), int(getattr(model, "last_input_tokens", 0))


def _set_lrs(optimizer, step: int, total_steps: int, warmup_steps: int, base_lrs: list[float]) -> float:
    scale = lr_multiplier(step, total_steps, warmup_steps)
    for group, base in zip(optimizer.param_groups, base_lrs):
        group["lr"] = base * scale
    return scale


def _enable_training(model, checkpointing: bool) -> None:
    if checkpointing:
        model.backbone.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )
        model.backbone.enable_input_require_grads()
    elif hasattr(model.backbone, "gradient_checkpointing_disable"):
        model.backbone.gradient_checkpointing_disable()
    model.train()


def _oom(error: BaseException) -> bool:
    name = type(error).__name__
    return name == "OutOfMemoryError" or "out of memory" in str(error).lower()


def _try_backward(model, rows, prepared) -> bool:
    import torch

    model.zero_grad(set_to_none=True)
    try:
        loss, _ = microbatch_loss(model, rows, prepared)
        if not loss.requires_grad:
            raise RuntimeError("loss is not connected to the adapter")
        loss.backward()
        torch.cuda.synchronize()
        model.zero_grad(set_to_none=True)
        del loss
        return True
    except Exception as error:
        model.zero_grad(set_to_none=True)
        torch.cuda.empty_cache()
        if _oom(error):
            return False
        raise


def choose_microbatch(model, rows: list[dict], tokenizer, max_length: int) -> tuple[int, bool, list]:
    """Largest microbatch that divides 16 and fits every chunk of the first step.

    Checkpointing stays off unless no size fits without it.
    """
    import torch

    sample = rows[:EFFECTIVE_BATCH]
    prepared = [_options(tokenizer, row, max_length) for row in sample]
    for checkpointing in (False, True):
        _enable_training(model, checkpointing)
        for size in (16, 8, 4, 2, 1):
            fits = True
            for start in range(0, EFFECTIVE_BATCH, size):
                if not _try_backward(
                    model, sample[start : start + size], prepared[start : start + size]
                ):
                    fits = False
                    break
            torch.cuda.empty_cache()
            if fits:
                return size, checkpointing, prepared
    raise RuntimeError("even microbatch 1 with checkpointing does not fit")


def run_epoch(
    model,
    rows: list[dict],
    *,
    started: float,
    output: Path,
    base_lrs: tuple[float, float] = (BASE_LR, HEAD_LR),
    on_checkpoint: Callable[[], None] | None = None,
    enforce_gate: bool = True,
) -> dict[str, Any]:
    import torch

    if len(rows) != TRAIN_ROWS:
        raise RuntimeError(f"refusing to train on {len(rows)} rows")
    missing = [row["id"] for row in rows if not row["positives"]]
    if missing:
        raise RuntimeError(f"{len(missing)} rows have no targets, first {missing[0]}")
    tokenizer = model.tokenizer
    max_length = int(model.max_length)
    output.mkdir(parents=True, exist_ok=True)
    microbatch, checkpointing, sample_prepared = choose_microbatch(model, rows, tokenizer, max_length)
    accumulation = EFFECTIVE_BATCH // microbatch
    total_steps = TRAIN_ROWS // EFFECTIVE_BATCH
    warmup_steps = max(1, round(WARMUP_FRACTION * total_steps))
    adapter = [p for name, p in model.named_parameters() if p.requires_grad and not name.startswith("head.")]
    head = [p for name, p in model.named_parameters() if p.requires_grad and name.startswith("head.")]
    if not adapter or not head:
        raise RuntimeError("adapter or scalar head has no trainable parameters")
    optimizer = torch.optim.AdamW(
        [
            {"params": adapter, "lr": base_lrs[0]},
            {"params": head, "lr": base_lrs[1]},
        ],
        weight_decay=0.01,
        betas=(0.9, 0.999),
        eps=1e-8,
    )
    base_lr_list = [base_lrs[0], base_lrs[1]]
    prepared: list[Any] = list(sample_prepared) + [None] * (len(rows) - len(sample_prepared))

    def get_prepared(start: int, stop: int):
        chunk = []
        for index in range(start, stop):
            if prepared[index] is None:
                prepared[index] = _options(tokenizer, rows[index], max_length)
            chunk.append(prepared[index])
        return chunk

    log_path = output / "training.jsonl"
    history: list[dict] = []
    measure_started = time.perf_counter()
    launched = False
    stop_reason = ""
    step = 0
    oom_retries = 0
    step_ooms = 0

    def snapshot(name: str) -> None:
        destination = output / name
        if not destination.exists():
            model.save(destination)
        if on_checkpoint:
            on_checkpoint()

    while step < total_steps:
        if launched and all_in_usd(time.perf_counter() - started) >= STOP_USD:
            stop_reason = "approached_29"
            snapshot("stopped-budget")
            break
        scale = _set_lrs(optimizer, step, total_steps, warmup_steps, base_lr_list)
        optimizer.zero_grad(set_to_none=True)
        loss_sum = 0.0
        token_sum = 0
        try:
            for micro in range(accumulation):
                begin = step * EFFECTIVE_BATCH + micro * microbatch
                chunk_rows = rows[begin : begin + microbatch]
                chunk_prepared = get_prepared(begin, begin + microbatch)
                loss, tokens = microbatch_loss(model, chunk_rows, chunk_prepared)
                (loss / accumulation).backward()
                loss_sum += float(loss.detach().item()) / accumulation
                token_sum += tokens
                del loss
        except Exception as error:
            import gc

            optimizer.zero_grad(set_to_none=True)
            gc.collect()
            torch.cuda.empty_cache()
            if not _oom(error):
                raise
            oom_retries += 1
            step_ooms += 1
            print(
                json.dumps(
                    {
                        "event": "oom",
                        "step": step,
                        "microbatch": microbatch,
                        "checkpointing": checkpointing,
                        "retries": step_ooms,
                    }
                ),
                flush=True,
            )
            if step_ooms > 6:
                stop_reason = "oom_after_probe"
                snapshot("stopped-oom")
                break
            if microbatch > 1:
                microbatch //= 2
                accumulation = EFFECTIVE_BATCH // microbatch
                print(json.dumps({"event": "oom_shrink", "microbatch": microbatch}), flush=True)
                continue
            if not checkpointing:
                checkpointing = True
                _enable_training(model, True)
                print(json.dumps({"event": "oom_checkpointing"}), flush=True)
                continue
            stop_reason = "oom_after_probe"
            snapshot("stopped-oom")
            break
        grad_norm = torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        finite = bool(torch.isfinite(torch.tensor(loss_sum))) and bool(torch.isfinite(grad_norm))
        spiked = bool(history) and step < 200 and loss_sum > max(10.0, 5.0 * history[0]["loss"])
        if (not finite or spiked) and base_lrs[0] > RESTART_LR and step < 200:
            if on_checkpoint:
                on_checkpoint()
            return {
                "status": "restart",
                "step": step,
                "reason": "nonfinite" if not finite else "spike",
                "microbatch": microbatch,
                "gradient_checkpointing": checkpointing,
                "spent_usd": all_in_usd(time.perf_counter() - started),
                "cost_gate": json.loads((output / "cost_gate.json").read_text())
                if (output / "cost_gate.json").is_file()
                else None,
                "history": history,
            }
        if not finite:
            stop_reason = "nonfinite"
            snapshot("stopped-nonfinite")
            break
        optimizer.step()
        step_ooms = 0
        record = {
            "step": step + 1,
            "loss": loss_sum,
            "grad_norm": float(grad_norm.item()),
            "lr_scale": scale,
            "lr": base_lrs[0] * scale,
            "head_lr": base_lrs[1] * scale,
            "tokens": token_sum,
            "elapsed_seconds": time.perf_counter() - started,
            "spent_usd": all_in_usd(time.perf_counter() - started),
        }
        history.append(record)
        with log_path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        if step < 5 or (step + 1) % 25 == 0:
            print(json.dumps(record), flush=True)
        step += 1
        if step == MEASURE_STEPS and not launched:
            measured_seconds = max(1e-6, time.perf_counter() - measure_started)
            measure_tokens = sum(item["tokens"] for item in history)
            tokens_per_sec = measure_tokens / measured_seconds
            rows_done = MEASURE_STEPS * EFFECTIVE_BATCH
            rows_per_sec = rows_done / measured_seconds
            remain_sec = (TRAIN_ROWS - rows_done) / rows_per_sec
            estimate = all_in_usd(time.perf_counter() - started) + remain_sec * ALL_IN_PER_SEC * LAUNCH_MARGIN
            gate = {
                "measured_tokens_per_sec": tokens_per_sec,
                "measured_rows_per_sec": rows_per_sec,
                "measured_seconds": measured_seconds,
                "measured_tokens": measure_tokens,
                "estimate_usd": estimate,
                "microbatch": microbatch,
                "accumulation": accumulation,
                "gradient_checkpointing": checkpointing,
                "all_in_usd_per_hour": ALL_IN_PER_SEC * 3600,
                "launch_margin": LAUNCH_MARGIN,
            }
            print(json.dumps({"event": "cost_gate", **gate}), flush=True)
            (output / "cost_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
            if on_checkpoint:
                on_checkpoint()
            if enforce_gate and estimate > CUTOFF_USD:
                stop_reason = "estimate_over_29"
                break
            launched = True
        if launched and step % 500 == 0:
            snapshot(f"step-{step:05d}")

    spent = all_in_usd(time.perf_counter() - started)
    if launched and step == total_steps and not stop_reason:
        snapshot("final")
        status = "complete"
    elif stop_reason == "estimate_over_29":
        status = "not_launched"
    elif launched:
        status = "stopped"
    else:
        status = "not_launched"
    summary = {
        "status": status,
        "stop_reason": stop_reason,
        "launched": bool(launched),
        "trained_steps": step,
        "total_steps": total_steps,
        "rows_consumed": step * EFFECTIVE_BATCH,
        "microbatch": microbatch,
        "accumulation": accumulation,
        "effective_batch": EFFECTIVE_BATCH,
        "gradient_checkpointing": checkpointing,
        "oom_retries": oom_retries,
        "base_lr": base_lrs[0],
        "head_lr": base_lrs[1],
        "warmup_steps": warmup_steps,
        "spent_usd_estimated": spent,
        "elapsed_seconds": time.perf_counter() - started,
        "loss_first": history[0]["loss"] if history else None,
        "loss_last": history[-1]["loss"] if history else None,
        "history_tail": history[-5:],
        "history": history,
    }
    if (output / "cost_gate.json").is_file():
        summary["cost_gate"] = json.loads((output / "cost_gate.json").read_text())
    (output / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "history"}, indent=2) + "\n"
    )
    if on_checkpoint:
        on_checkpoint()
    return summary
