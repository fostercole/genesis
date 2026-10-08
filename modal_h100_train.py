"""50,000-row QLoRA epoch on one Modal H100.

The function measures tokens per second for four optimizer steps, estimates the
all-in cost, and refuses the rest of the epoch when that estimate is over $29.
A running epoch stops once estimated spend reaches $28, before the $29 line.
There is no second epoch in this app.
"""

from __future__ import annotations

import json
from pathlib import Path

import modal

from toolret_smoke.train_epoch import ALL_IN_PER_SEC, CUTOFF_USD, STOP_USD

APP_NAME = "toolret-h100-train"
OPEN_JEV_COMMIT = "bd4118882f733574a3250a4b65fe4d884130c08b"
QWEN_REVISION = "15852e8c16360a2fea060d615a32b45270f8a8fc"
TIMEOUT_SEC = int(STOP_USD / ALL_IN_PER_SEC)

app = modal.App(APP_NAME)
hf_volume = modal.Volume.from_name("toolret-t4-scorer-hf", create_if_missing=True)
run_volume = modal.Volume.from_name("toolret-h100-train", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install("torch==2.8.0", index_url="https://download.pytorch.org/whl/cu128")
    .pip_install(
        "transformers==5.10.2",
        "peft==0.19.1",
        "accelerate==1.13.0",
        "safetensors==0.7.0",
        "huggingface_hub==1.33.0",
        "einops==0.8.2",
        "bitsandbytes",
    )
    .run_commands(
        "git clone --filter=blob:none --no-checkout https://github.com/Zefan-Cai/Open-Jev.git /opt/open-jev"
        " && git -C /opt/open-jev sparse-checkout init --cone"
        " && git -C /opt/open-jev sparse-checkout set jev pyproject.toml README.md LICENSE"
        f" && git -C /opt/open-jev checkout {OPEN_JEV_COMMIT}"
        " && pip install -e /opt/open-jev"
        " && python -c 'import jev.model, bitsandbytes'"
    )
    .env(
        {
            "HF_HOME": "/cache/hf",
            "HF_HUB_CACHE": "/cache/hf/hub",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    .add_local_python_source("toolret_smoke")
    .add_local_file("data/train_50k.jsonl", "/data/train_50k.jsonl")
)


def _load_model():
    import os

    import torch

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["JEV_LOAD_4BIT"] = "1"
    os.environ["JEV_TORCH_DTYPE"] = "bfloat16"
    from jev.model import DecisionModel

    checkpoint = Path("/cache/hf/READY").read_text().splitlines()[1]
    checkpoint = Path(checkpoint) / "package" / "checkpoint"
    model = DecisionModel.load(checkpoint)
    model.requires_grad_(False)
    for name, parameter in model.named_parameters():
        if name.startswith("head.") or ".lora_" in name:
            parameter.requires_grad_(True)
    if hasattr(model.backbone, "peft_config"):
        for config in model.backbone.peft_config.values():
            config.inference_mode = False
    model.train()
    trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    if trainable <= 0:
        raise RuntimeError("no trainable parameters after loading the adapter")
    torch.cuda.reset_peak_memory_stats()
    return model, checkpoint, trainable


def _read_rows() -> list[dict]:
    rows = []
    with Path("/data/train_50k.jsonl").open() as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if len(rows) != 50_000:
        raise SystemExit(f"refusing to train on {len(rows)} rows")
    return rows


@app.function(
    image=image,
    gpu="H100",
    cpu=8,
    memory=32768,
    timeout=TIMEOUT_SEC,
    volumes={"/cache": hf_volume, "/vol": run_volume},
)
def train() -> dict:
    import gc
    import os
    import time

    import torch

    if CUTOFF_USD != 29.0:
        raise SystemExit("refusing to start with a cutoff other than $29")
    os.environ["HF_HOME"] = "/cache/hf"
    os.environ["HF_HUB_CACHE"] = "/cache/hf/hub"
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.backends.cuda.matmul.allow_tf32 = True
    gpu_name = torch.cuda.get_device_name(0)
    if "H100" not in gpu_name:
        raise SystemExit(f"refusing non-H100 GPU: {gpu_name}")
    started = time.perf_counter()
    rows = _read_rows()
    from toolret_smoke.train_epoch import all_in_usd, run_epoch

    def launch_one(base_lrs: tuple[float, float], directory: str, enforce_gate: bool = True) -> dict:
        model, checkpoint, trainable = _load_model()
        output = Path("/vol") / directory
        output.mkdir(parents=True, exist_ok=True)

        def commit() -> None:
            run_volume.commit()

        summary = run_epoch(
            model,
            rows,
            started=started,
            output=output,
            base_lrs=base_lrs,
            on_checkpoint=commit,
            enforce_gate=enforce_gate,
        )
        summary["trainable_parameters"] = trainable
        summary["checkpoint"] = str(checkpoint)
        summary["gpu"] = gpu_name
        del model
        gc.collect()
        torch.cuda.empty_cache()
        commit()
        return summary

    first = launch_one((1e-4, 1e-4), "pass1")
    result = first
    if first.get("status") == "restart":
        gate = first.get("cost_gate") or {}
        rows_per_sec = float(gate.get("measured_rows_per_sec") or 0)
        spent = all_in_usd(time.perf_counter() - started)
        full_epoch = (50_000 / rows_per_sec) if rows_per_sec else float("inf")
        projected = spent + full_epoch * ALL_IN_PER_SEC * 1.15
        if projected <= CUTOFF_USD:
            second = launch_one((2e-5, 2e-5), "pass2", enforce_gate=False)
            second["restarted_from"] = first.get("reason")
            second["first_pass_spent_usd"] = spent
            result = second
        else:
            first["status"] = "stopped"
            first["stop_reason"] = "spike_restart_would_pass_29"
            first["restart_projected_usd"] = projected
            result = first
    result["gpu"] = gpu_name
    result["timeout_seconds"] = TIMEOUT_SEC
    result["cutoff_usd"] = CUTOFF_USD
    result["stop_usd"] = STOP_USD
    result["all_in_usd_per_hour"] = ALL_IN_PER_SEC * 3600
    result["second_epoch"] = False
    result["second_epoch_reason"] = (
        "not started; dev completeness@5 on the BM25 top 50 was not measured, "
        "so the climb condition is not met"
    )
    # The history is already on the volume. Keep the tail in the return value.
    result.pop("history", None)
    print(json.dumps({k: v for k, v in result.items() if k != "history_tail"}, default=str), flush=True)
    run_volume.commit()
    return result


@app.local_entrypoint()
def main() -> None:
    summary = train.remote()
    out = Path("results/h100_train_summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n")
    gate = summary.get("cost_gate") or {}
    print(
        json.dumps(
            {
                "status": summary.get("status"),
                "launched": summary.get("launched"),
                "measured_tokens_per_sec": gate.get("measured_tokens_per_sec"),
                "estimate_usd": gate.get("estimate_usd"),
                "wrote": str(out),
            }
        ),
        flush=True,
    )
