"""T4 scorer smoke: 32 dev rows, original Open-Jev-2B, no training.

Hard stop: this function requests a T4 for at most 30 minutes. At the loaded
T4 rate in the plan (~$0.91/hour) that is about $0.46, under the $5 ceiling.
There is no H100 function and no 50,000-row training entrypoint in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import modal

APP_NAME = "toolret-t4-scorer-smoke"
OPEN_JEV_COMMIT = "bd4118882f733574a3250a4b65fe4d884130c08b"
QWEN_REVISION = "15852e8c16360a2fea060d615a32b45270f8a8fc"
SMOKE_ROWS = 32
# Plan rates: T4 GPU $0.59/hr, CPU $0.0000131/core/s, memory $0.00000222/GiB/s.
LOADED_T4_USD_PER_SEC = (0.59 / 3600) + (4 * 0.0000131) + (16 * 0.00000222)
GPU_TIMEOUT_SEC = 30 * 60
MAX_GPU_USD = GPU_TIMEOUT_SEC * LOADED_T4_USD_PER_SEC

app = modal.App(APP_NAME)
volume = modal.Volume.from_name("toolret-t4-scorer-hf", create_if_missing=True)

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
    )
    .run_commands(
        "git clone --filter=blob:none --no-checkout https://github.com/Zefan-Cai/Open-Jev.git /opt/open-jev"
        " && git -C /opt/open-jev sparse-checkout init --cone"
        " && git -C /opt/open-jev sparse-checkout set jev pyproject.toml README.md LICENSE"
        f" && git -C /opt/open-jev checkout {OPEN_JEV_COMMIT}"
        " && pip install -e /opt/open-jev"
        " && python -c 'import jev.model'"
    )
    .env(
        {
            "HF_HOME": "/cache/hf",
            "HF_HUB_CACHE": "/cache/hf/hub",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    .add_local_python_source("toolret_smoke")
    .add_local_file("data/dev_smoke_32.jsonl", "/data/dev_smoke_32.jsonl")
)


@app.function(image=image, cpu=2, memory=8192, timeout=45 * 60, volumes={"/cache": volume})
def prefetch() -> dict:
    """Download weights on CPU so the T4 is not billed for the transfer."""
    import os
    import time
    from pathlib import Path

    from huggingface_hub import snapshot_download

    started = time.perf_counter()
    os.environ["HF_HOME"] = "/cache/hf"
    os.environ["HF_HUB_CACHE"] = "/cache/hf/hub"
    marker = Path("/cache/hf/READY")
    if marker.is_file():
        qwen, jev = marker.read_text().splitlines()[:2]
    else:
        qwen = snapshot_download("Qwen/Qwen3.5-2B", revision=QWEN_REVISION)
        jev = snapshot_download("ZefanCai/Open-Jev-2B")
        marker.write_text(qwen + "\n" + jev + "\n")
    checkpoint = Path(jev) / "package" / "checkpoint"
    required = [
        checkpoint / "model.json",
        checkpoint / "head.pt",
        checkpoint / "adapter" / "adapter_config.json",
        checkpoint / "adapter" / "adapter_model.safetensors",
        Path(qwen) / "config.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("weight cache is incomplete: " + ", ".join(missing))
    volume.commit()
    return {
        "status": "cached",
        "elapsed_seconds": time.perf_counter() - started,
        "qwen_revision": QWEN_REVISION,
        "open_jev_commit": OPEN_JEV_COMMIT,
    }


@app.function(
    image=image,
    gpu="T4",
    cpu=4,
    memory=16384,
    timeout=GPU_TIMEOUT_SEC,
    volumes={"/cache": volume},
)
def score() -> dict:
    import os
    import time
    from pathlib import Path

    if MAX_GPU_USD > 5:
        raise SystemExit(f"refusing to start: T4 timeout could cost ${MAX_GPU_USD:.2f}")

    os.environ["HF_HOME"] = "/cache/hf"
    os.environ["HF_HUB_CACHE"] = "/cache/hf/hub"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    import torch

    started = time.perf_counter()
    gpu_name = torch.cuda.get_device_name(0)
    if "T4" not in gpu_name:
        raise SystemExit(f"refusing non-T4 GPU: {gpu_name}")

    dtype = "bfloat16" if torch.cuda.is_bf16_supported() else "float16"
    os.environ["JEV_TORCH_DTYPE"] = dtype
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)

    from jev.model import DecisionModel
    from toolret_smoke.score_rows import score_rows, summarize

    marker = Path("/cache/hf/READY").read_text().splitlines()
    checkpoint = Path(marker[1]) / "package" / "checkpoint"
    rows = [
        json.loads(line)
        for line in Path("/data/dev_smoke_32.jsonl").read_text().splitlines()
        if line.strip()
    ]
    if len(rows) != SMOKE_ROWS:
        raise SystemExit(f"refusing to score {len(rows)} rows; the smoke is {SMOKE_ROWS}")

    model = DecisionModel.load(checkpoint)
    model.requires_grad_(False)
    model.eval()
    trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    if trainable:
        raise SystemExit(f"refusing to score with {trainable} trainable parameters")

    reports = score_rows(model, rows)
    elapsed = time.perf_counter() - started
    summary = summarize(reports, checkpoint, dtype, gpu_name, elapsed)
    summary["trainable_parameters_left_unfrozen"] = trainable
    summary["estimated_loaded_t4_usd"] = elapsed * LOADED_T4_USD_PER_SEC
    summary["gpu_timeout_seconds"] = GPU_TIMEOUT_SEC
    summary["max_gpu_usd_if_timeout"] = MAX_GPU_USD
    summary["base_revision"] = QWEN_REVISION
    summary["open_jev_commit"] = OPEN_JEV_COMMIT
    print(json.dumps({k: summary[k] for k in summary if k != "per_row"}), flush=True)
    return summary


@app.local_entrypoint()
def main() -> None:
    pre = prefetch.remote()
    summary = score.remote()
    summary["prefetch"] = pre
    out = Path("results/t4_scorer_smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"status": summary["status"], "wrote": str(out)}), flush=True)
