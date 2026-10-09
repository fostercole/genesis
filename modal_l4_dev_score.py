"""Score the 2,000-row dev split on one Modal L4. Inference only.

The function times a handful of rows, estimates the loaded-L4 cost of both
checkpoints on all 2,000 rows, and returns without scoring the rest when that
estimate is over $10. A running pass stops once the estimate reaches $9.50.
There is no second training epoch, no ToolRet test split, and no Voyage call.
"""

from __future__ import annotations

import json
from pathlib import Path

import modal

from toolret_smoke.dev_eval import DEV_ROWS, DEV_SCORE_CAP_USD, LOADED_L4_USD_PER_SEC, full_pass_estimate_usd

APP_NAME = "toolret-l4-dev-score"
OPEN_JEV_COMMIT = "bd4118882f733574a3250a4b65fe4d884130c08b"
QWEN_REVISION = "15852e8c16360a2fea060d615a32b45270f8a8fc"
PROBE_ROWS = 16
STOP_USD = 9.50
# A hard timeout priced at about $9.80 so a stuck kernel still ends under $10.
GPU_TIMEOUT_SEC = int(9.80 / LOADED_L4_USD_PER_SEC)
ORIGINAL_SHA256 = {
    "model.json": "d985eafa4d635113ee8cc912e0512a95aac0bed3426e9256931235b75cb3d6c5",
    "head.pt": "3532cd576c58d5ad5bf17c3e9f2df4be8c70e08c07fa6bb7fa673dcd7b401f2a",
    "adapter_config.json": "d27624bdbbe984cf175e10c7fa3d9beaea9876231ce943a248ad40e12742fe74",
    "adapter_model.safetensors": "2d23935b1a7380db444abac572c04646918ba794e59002d1588236182a3ca18f",
}

app = modal.App(APP_NAME)
hf_volume = modal.Volume.from_name("toolret-t4-scorer-hf", create_if_missing=False)
run_volume = modal.Volume.from_name("toolret-h100-train", create_if_missing=False)

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
    .add_local_file("data/dev_bm25_top50.jsonl", "/data/dev_bm25_top50.jsonl")
)


def _checkpoint_files(checkpoint: Path) -> dict[str, Path]:
    return {
        "model.json": checkpoint / "model.json",
        "head.pt": checkpoint / "head.pt",
        "adapter_config.json": checkpoint / "adapter" / "adapter_config.json",
        "adapter_model.safetensors": checkpoint / "adapter" / "adapter_model.safetensors",
    }


def _sha256_checkpoint(checkpoint: Path) -> dict[str, str]:
    from toolret_smoke.score_rows import file_sha256

    return {name: file_sha256(path) for name, path in _checkpoint_files(checkpoint).items()}


def _original_checkpoint() -> Path:
    marker = Path("/cache/hf/READY").read_text().splitlines()
    return Path(marker[1]) / "package" / "checkpoint"


def _tuned_checkpoint() -> Path:
    return Path("/vol/pass1/final")


def _read_rows() -> list[dict]:
    rows = []
    with Path("/data/dev_bm25_top50.jsonl").open() as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if len(rows) != DEV_ROWS:
        raise SystemExit(f"refusing to score {len(rows)} rows; the dev split is {DEV_ROWS}")
    return rows


@app.function(
    image=image,
    cpu=2,
    memory=8192,
    timeout=30 * 60,
    volumes={"/cache": hf_volume, "/vol": run_volume},
)
def preflight() -> dict:
    """Hash both checkpoints on CPU. The L4 is not billed for this."""
    import json as json_lib

    original = _original_checkpoint()
    tuned = _tuned_checkpoint()
    original_sha = _sha256_checkpoint(original)
    if original_sha != ORIGINAL_SHA256:
        raise SystemExit("original checkpoint hash does not match the T4 smoke")
    tuned_sha = _sha256_checkpoint(tuned)
    config = json_lib.loads((tuned / "model.json").read_text())
    if config.get("model_id") != "Qwen/Qwen3.5-2B" or config.get("revision") != QWEN_REVISION:
        raise SystemExit(f"tuned model.json is not the pinned Qwen revision: {config}")
    if int(config.get("lora_rank") or 0) != 8 or int(config.get("max_length") or 0) != 4096:
        raise SystemExit(f"tuned model.json is not the Open-Jev 2B head setup: {config}")
    return {
        "original_sha256": original_sha,
        "tuned_sha256": tuned_sha,
        "tuned_model": config,
        "open_jev_commit": OPEN_JEV_COMMIT,
        "base_revision": QWEN_REVISION,
    }


@app.function(
    image=image,
    gpu="L4",
    cpu=8,
    memory=32768,
    timeout=GPU_TIMEOUT_SEC,
    volumes={"/cache": hf_volume, "/vol": run_volume},
)
def score() -> dict:
    import os
    import time

    import torch

    started = time.perf_counter()

    def spent() -> float:
        return (time.perf_counter() - started) * LOADED_L4_USD_PER_SEC

    if abs(LOADED_L4_USD_PER_SEC * 3600 - 1.433024) > 1e-6:
        raise SystemExit("refusing to start with a loaded L4 rate other than the plan")
    os.environ["HF_HOME"] = "/cache/hf"
    os.environ["HF_HUB_CACHE"] = "/cache/hf/hub"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.pop("JEV_LOAD_4BIT", None)
    os.environ.pop("JEV_LOAD_8BIT", None)

    gpu_name = torch.cuda.get_device_name(0)
    if "L4" not in gpu_name:
        raise SystemExit(f"refusing non-L4 GPU: {gpu_name}")
    dtype = "bfloat16" if torch.cuda.is_bf16_supported() else "float16"
    os.environ["JEV_TORCH_DTYPE"] = dtype

    from jev.model import DecisionModel
    from toolret_smoke.score_dev import fit_row, ranks_for_row, score_fitted

    rows = _read_rows()
    for row in rows:
        if len(row["candidates"]) != 50:
            raise SystemExit(f"{row['id']} does not have 50 candidates")
        if int(row["n_positive"]) < 1:
            raise SystemExit(f"{row['id']} has no positive")

    def load(checkpoint: Path):
        model = DecisionModel.load(checkpoint)
        model.requires_grad_(False)
        model.eval()
        trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
        if trainable:
            raise SystemExit(f"refusing to score with {trainable} trainable parameters")
        if int(model.max_length) != 4096:
            raise SystemExit(f"refusing max_length {model.max_length}")
        return model

    original = load(_original_checkpoint())
    tuned = load(_tuned_checkpoint())
    loaded_at = time.perf_counter()
    load_seconds = loaded_at - started
    tokenizer = original.tokenizer
    max_length = int(original.max_length)

    partial_path = Path("/vol/dev-score/partial.json")

    def save_partial(original_rows: list[dict], tuned_rows: list[dict], estimate: float | None, probe_seconds: float | None) -> None:
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "rows_scored": len(original_rows),
            "estimate_usd": estimate,
            "probe_score_seconds": probe_seconds,
            "load_seconds": load_seconds,
            "original": original_rows,
            "tuned": tuned_rows,
        }
        temporary = partial_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload))
        temporary.replace(partial_path)
        run_volume.commit()

    def score_slice(
        begin: int,
        end: int,
        original_rows: list[dict],
        tuned_rows: list[dict],
        estimate: float | None,
        probe_seconds: float | None,
    ) -> None:
        for index in range(begin, end):
            if spent() >= STOP_USD:
                save_partial(original_rows, tuned_rows, estimate, probe_seconds)
                raise RuntimeError("approached_10")
            row = rows[index]
            options, lengths = fit_row(tokenizer, row, max_length)
            original_rows.append(ranks_for_row(row, score_fitted(original, row, options, lengths)))
            if spent() >= STOP_USD:
                save_partial(original_rows, tuned_rows, estimate, probe_seconds)
                raise RuntimeError("approached_10")
            tuned_rows.append(ranks_for_row(row, score_fitted(tuned, row, options, lengths)))
            done = len(original_rows)
            if done % 25 == 0 or done == end:
                print(
                    json.dumps(
                        {
                            "event": "progress",
                            "rows": done,
                            "spent_usd": spent(),
                            "elapsed_seconds": time.perf_counter() - started,
                        }
                    ),
                    flush=True,
                )
            if done % 100 == 0:
                save_partial(original_rows, tuned_rows, estimate, probe_seconds)

    resumed = None
    if partial_path.is_file():
        resumed = json.loads(partial_path.read_text())
        if (
            len(resumed.get("original") or []) != int(resumed.get("rows_scored") or -1)
            or len(resumed.get("tuned") or []) != int(resumed.get("rows_scored") or -1)
            or resumed["original"][0]["id"] != rows[0]["id"]
            or resumed["original"][-1]["id"] != rows[int(resumed["rows_scored"]) - 1]["id"]
        ):
            raise SystemExit("refusing to resume a partial file that does not match this dev split")

    if resumed and int(resumed["rows_scored"]) >= PROBE_ROWS and float(resumed["estimate_usd"]) <= DEV_SCORE_CAP_USD:
        original_rows = list(resumed["original"])
        tuned_rows = list(resumed["tuned"])
        estimate = float(resumed["estimate_usd"])
        probe_score_seconds = float(resumed["probe_score_seconds"])
        print(
            json.dumps(
                {
                    "event": "resume",
                    "rows": len(original_rows),
                    "estimate_usd": estimate,
                    "spent_usd": spent(),
                }
            ),
            flush=True,
        )
    else:
        original_rows = []
        tuned_rows = []
        try:
            score_slice(0, PROBE_ROWS, original_rows, tuned_rows, None, None)
        except RuntimeError as error:
            if str(error) != "approached_10":
                raise
            return _finish(
                started,
                gpu_name,
                dtype,
                load_seconds,
                launched=False,
                stop_reason="approached_10_during_probe",
                estimate_usd=None,
                original_rows=[],
                tuned_rows=[],
            )
        probe_score_seconds = time.perf_counter() - loaded_at
        estimate = full_pass_estimate_usd(load_seconds, probe_score_seconds, PROBE_ROWS, DEV_ROWS)
        print(
            json.dumps(
                {
                    "event": "cost_gate",
                    "probe_rows": PROBE_ROWS,
                    "load_seconds": load_seconds,
                    "probe_score_seconds": probe_score_seconds,
                    "estimate_usd": estimate,
                    "spent_usd": spent(),
                }
            ),
            flush=True,
        )
        if estimate > DEV_SCORE_CAP_USD:
            return _finish(
                started,
                gpu_name,
                dtype,
                load_seconds,
                launched=False,
                stop_reason="estimate_over_10",
                estimate_usd=estimate,
                original_rows=[],
                tuned_rows=[],
                probe_score_seconds=probe_score_seconds,
            )
        save_partial(original_rows, tuned_rows, estimate, probe_score_seconds)

    try:
        score_slice(len(original_rows), DEV_ROWS, original_rows, tuned_rows, estimate, probe_score_seconds)
    except RuntimeError as error:
        if str(error) != "approached_10":
            raise
        return _finish(
            started,
            gpu_name,
            dtype,
            load_seconds,
            launched=True,
            stop_reason="approached_10",
            estimate_usd=estimate,
            original_rows=original_rows,
            tuned_rows=tuned_rows,
            probe_score_seconds=probe_score_seconds,
            partial=True,
        )
    return _finish(
        started,
        gpu_name,
        dtype,
        load_seconds,
        launched=True,
        stop_reason="",
        estimate_usd=estimate,
        original_rows=original_rows,
        tuned_rows=tuned_rows,
        probe_score_seconds=probe_score_seconds,
    )


def _finish(
    started: float,
    gpu_name: str,
    dtype: str,
    load_seconds: float,
    launched: bool,
    stop_reason: str,
    estimate_usd: float | None,
    original_rows: list[dict],
    tuned_rows: list[dict],
    probe_score_seconds: float | None = None,
    partial: bool = False,
) -> dict:
    import time

    from toolret_smoke.dev_eval import lock_k
    from toolret_smoke.score_dev import summarize_model

    complete = launched and not partial and not stop_reason and len(original_rows) == DEV_ROWS
    result = {
        "status": "complete" if complete else "not_launched" if not launched else "stopped",
        "job": "l4-dev-bm25-top50",
        "launched": launched,
        "stop_reason": stop_reason,
        "trained": False,
        "second_epoch": False,
        "rows_requested": DEV_ROWS,
        "rows_scored": len(original_rows),
        "probe_rows": PROBE_ROWS,
        "load_seconds": load_seconds,
        "probe_score_seconds": probe_score_seconds,
        "estimate_usd": estimate_usd,
        "spent_usd_estimated": (time.perf_counter() - started) * LOADED_L4_USD_PER_SEC,
        "elapsed_seconds": time.perf_counter() - started,
        "gpu": gpu_name,
        "dtype": dtype,
        "cap_usd": DEV_SCORE_CAP_USD,
        "stop_usd": STOP_USD,
        "loaded_l4_usd_per_hour": LOADED_L4_USD_PER_SEC * 3600,
        "two_runs": False,
        "candidate_k": 50,
        "sdp": "default",
    }
    if complete:
        original = summarize_model(original_rows)
        tuned = summarize_model(tuned_rows)
        completeness = {
            k: tuned["metrics"][f"completeness@{k}"] for k in (3, 5, 10)
        }
        locked = lock_k(completeness)
        original_c5 = original["metrics"]["completeness@5"]
        tuned_c5 = tuned["metrics"]["completeness@5"]
        result["locked_k"] = locked
        result["tuned_completeness_at_5_beats_original"] = tuned_c5 > original_c5
        result["completeness_at_5"] = {"original": original_c5, "tuned": tuned_c5}
        result["models"] = {
            "original": {"metrics": original["metrics"], "per_row": original["per_row"]},
            "tuned": {"metrics": tuned["metrics"], "per_row": tuned["per_row"]},
        }
    out = Path("/vol/dev-score/result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result) + "\n")
    run_volume.commit()
    result["elapsed_seconds"] = time.perf_counter() - started
    result["spent_usd_estimated"] = result["elapsed_seconds"] * LOADED_L4_USD_PER_SEC
    print(json.dumps({key: result[key] for key in result if key != "models"}), flush=True)
    return result


@app.local_entrypoint()
def main() -> None:
    """Spawn the scorer and return. A blocking remote() call was cancelled when the client heartbeat dropped."""
    checked = preflight.remote()
    call = score.spawn()
    out = Path("results/dev_bm25_spawn.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"function_call_id": call.object_id, "preflight": checked}, indent=2) + "\n"
    )
    print(json.dumps({"spawned": call.object_id}), flush=True)
