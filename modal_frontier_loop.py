"""Frontier tool-calling loop on Modal.

The full menu is the dev BM25 top 50. Filtered arms keep 10 of those tools.
Ground truth is the tool the frontier model calls on the full menu. There is
no training, no second epoch, and no official ToolRet test split.
"""

from __future__ import annotations

import modal

APP_NAME = "toolret-frontier-loop"
OPEN_JEV_COMMIT = "bd4118882f733574a3250a4b65fe4d884130c08b"
QWEN_2B_REVISION = "15852e8c16360a2fea060d615a32b45270f8a8fc"
ORIGINAL_SHA256 = {
    "model.json": "d985eafa4d635113ee8cc912e0512a95aac0bed3426e9256931235b75cb3d6c5",
    "head.pt": "3532cd576c58d5ad5bf17c3e9f2df4be8c70e08c07fa6bb7fa673dcd7b401f2a",
    "adapter_config.json": "d27624bdbbe984cf175e10c7fa3d9beaea9876231ce943a248ad40e12742fe74",
    "adapter_model.safetensors": "2d23935b1a7380db444abac572c04646918ba794e59002d1588236182a3ca18f",
}
TUNED_SHA256 = {
    "model.json": "d985eafa4d635113ee8cc912e0512a95aac0bed3426e9256931235b75cb3d6c5",
    "head.pt": "739c461e34414598ec9bfbd921671512151aa9ea9d13610befff4951755be448",
    "adapter_config.json": "5f7426b8702fb9d47e8002ce6a0eccfc53623fc9ded146858254e223c429e9a8",
    "adapter_model.safetensors": "5f381b5fd95fe1805d2d0394398779ca4dbea937c5b48fa87ace4cde921eaad3",
}

app = modal.App(APP_NAME)
weights_volume = modal.Volume.from_name("toolret-frontier-weights", create_if_missing=True)
results_volume = modal.Volume.from_name("toolret-frontier-results", create_if_missing=True)
hf_volume = modal.Volume.from_name("toolret-t4-scorer-hf", create_if_missing=False)
run_volume = modal.Volume.from_name("toolret-h100-train", create_if_missing=False)

# Same stack as the finished L4 dev pass, defined here so the container does not
# import modal_l4_dev_score. That module is not on the image.
score_image = (
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

prefetch_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("huggingface_hub==1.33.0", "hf_transfer==0.1.9")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("vllm==0.8.5.post1")
    .env({"TOKENIZERS_PARALLELISM": "false", "VLLM_WORKER_MULTIPROC_METHOD": "spawn"})
    .add_local_python_source("frontier_menu", "frontier_budget")
)


@app.function(
    image=prefetch_image,
    cpu=2,
    memory=16384,
    timeout=2400,
    scaledown_window=2,
    volumes={"/weights": weights_volume},
)
def prefetch(model_id: str, revision: str, model_key: str) -> dict:
    """Download one instruct checkpoint on CPU. The GPU is not attached."""
    import json
    import os
    import time
    from pathlib import Path

    started = time.perf_counter()
    dest = Path("/weights") / model_key
    ready_path = dest / "READY"
    if ready_path.is_file() and (dest / "config.json").is_file():
        ready = json.loads(ready_path.read_text())
        if ready.get("model_id") == model_id and ready.get("revision") == revision:
            return {
                "ok": True,
                "cached": True,
                "model_id": model_id,
                "revision": revision,
                "model_dir": str(dest),
                "elapsed_seconds": time.perf_counter() - started,
            }
    dest.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import snapshot_download

    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    snapshot_download(repo_id=model_id, revision=revision, local_dir=str(dest))
    if not (dest / "config.json").is_file():
        raise RuntimeError("download finished without config.json")
    nbytes = sum(path.stat().st_size for path in dest.rglob("*") if path.is_file())
    ready_path.write_text(
        json.dumps({"model_id": model_id, "revision": revision, "bytes": nbytes}) + "\n"
    )
    weights_volume.commit()
    return {
        "ok": True,
        "cached": False,
        "model_id": model_id,
        "revision": revision,
        "model_dir": str(dest),
        "bytes": nbytes,
        "elapsed_seconds": time.perf_counter() - started,
    }


@app.function(
    image=score_image,
    gpu="L4",
    cpu=8,
    memory=32768,
    timeout=600,
    scaledown_window=2,
    retries=0,
    volumes={"/cache": hf_volume, "/vol": run_volume},
)
def score_sample(row_ids: list[str]) -> dict:
    """Score the sample menus with the original and tuned 2B checkpoints. No training."""
    import json
    import os
    import time
    from pathlib import Path

    started = time.perf_counter()
    os.environ["HF_HOME"] = "/cache/hf"
    os.environ["HF_HUB_CACHE"] = "/cache/hf/hub"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.pop("JEV_LOAD_4BIT", None)
    os.environ.pop("JEV_LOAD_8BIT", None)

    import torch

    from jev.model import DecisionModel
    from toolret_smoke.score_dev import fit_row, score_fitted
    from toolret_smoke.score_rows import file_sha256

    gpu_name = torch.cuda.get_device_name(0)
    if "L4" not in gpu_name or "L40" in gpu_name:
        raise SystemExit(f"refusing non-L4 GPU: {gpu_name}")
    dtype = "bfloat16" if torch.cuda.is_bf16_supported() else "float16"
    os.environ["JEV_TORCH_DTYPE"] = dtype

    def checkpoint_sha(checkpoint: Path) -> dict[str, str]:
        files = {
            "model.json": checkpoint / "model.json",
            "head.pt": checkpoint / "head.pt",
            "adapter_config.json": checkpoint / "adapter" / "adapter_config.json",
            "adapter_model.safetensors": checkpoint / "adapter" / "adapter_model.safetensors",
        }
        return {name: file_sha256(path) for name, path in files.items()}

    marker = Path("/cache/hf/READY").read_text().splitlines()
    original_dir = Path(marker[1]) / "package" / "checkpoint"
    tuned_dir = Path("/vol/pass1/final")
    original_sha = checkpoint_sha(original_dir)
    tuned_sha = checkpoint_sha(tuned_dir)
    if original_sha != ORIGINAL_SHA256:
        raise SystemExit("original checkpoint hash does not match the finished dev pass")
    if tuned_sha != TUNED_SHA256:
        raise SystemExit("tuned checkpoint hash does not match pass1/final")
    config = json.loads((tuned_dir / "model.json").read_text())
    if config.get("model_id") != "Qwen/Qwen3.5-2B" or config.get("revision") != QWEN_2B_REVISION:
        raise SystemExit("tuned checkpoint is not the pinned Qwen3.5-2B revision")

    wanted = set(row_ids)
    rows = []
    with Path("/data/dev_bm25_top50.jsonl").open() as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["id"] in wanted:
                rows.append(row)
    by_id = {row["id"]: row for row in rows}
    missing = [row_id for row_id in row_ids if row_id not in by_id]
    if missing:
        raise SystemExit(f"dev file is missing {len(missing)} requested rows")

    def load(checkpoint: Path):
        model = DecisionModel.load(checkpoint)
        model.requires_grad_(False)
        model.eval()
        trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
        if trainable:
            raise SystemExit(f"refusing to score with {trainable} trainable parameters")
        return model

    original = load(original_dir)
    tuned = load(tuned_dir)
    tokenizer = original.tokenizer
    max_length = int(original.max_length)
    scored = {}
    for row_id in row_ids:
        row = by_id[row_id]
        if len(row["candidates"]) != 50:
            raise SystemExit(f"{row_id} does not have the 50-tool menu")
        options, lengths = fit_row(tokenizer, row, max_length)
        scored[row_id] = {
            "original": score_fitted(original, row, options, lengths),
            "tuned": score_fitted(tuned, row, options, lengths),
        }
        print(json.dumps({"event": "scored", "id": row_id, "elapsed_seconds": time.perf_counter() - started}), flush=True)
    return {
        "ok": True,
        "trained": False,
        "gpu_name": gpu_name,
        "dtype": dtype,
        "elapsed_seconds": time.perf_counter() - started,
        "open_jev_commit": OPEN_JEV_COMMIT,
        "base_revision": QWEN_2B_REVISION,
        "tuned_model": config,
        "rows": scored,
    }


@app.function(
    image=prefetch_image,
    cpu=1,
    memory=2048,
    timeout=180,
    scaledown_window=2,
    volumes={"/out": results_volume},
)
def read_saved() -> dict:
    import json
    from pathlib import Path

    results_volume.reload()
    for name in ("result.json", "partial.json"):
        path = Path("/out") / name
        if path.is_file():
            return json.loads(path.read_text())
    return {"ok": False, "error": "no_saved_result"}


@app.function(
    image=vllm_image,
    gpu="H100",
    max_containers=1,
    cpu=4,
    memory=65536,
    timeout=1560,
    scaledown_window=2,
    retries=0,
    volumes={"/weights": weights_volume, "/out": results_volume},
)
def infer(spec: dict) -> dict:
    """One frontier model. Probe one query, then shrink before the rest."""
    import json
    import os
    import time
    from pathlib import Path

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    from frontier_budget import ARM_ORDER, shrink_after_probe
    from frontier_menu import extract_called_tools

    weights_volume.reload()
    results_volume.reload()
    started = time.perf_counter()
    hourly = float(spec["hourly_usd"])
    job_cap = float(spec["job_cap_usd"])

    def spent() -> float:
        return (time.perf_counter() - started) * hourly / 3600

    def gpu_matches(name: str, gpu: str) -> bool:
        if gpu == "H100":
            return "H100" in name
        if gpu == "A100-80GB":
            return "A100" in name and "80" in name
        if gpu == "L40S":
            return "L40S" in name
        if gpu == "L4":
            return "L4" in name and "L40" not in name
        return False

    import torch

    gpu_name = torch.cuda.get_device_name(0)
    if not gpu_matches(gpu_name, spec["gpu"]):
        return {
            "ok": False,
            "error": "unexpected_gpu",
            "gpu_name": gpu_name,
            "spent_usd_estimated": spent(),
            "elapsed_seconds": time.perf_counter() - started,
        }

    ready = json.loads((Path(spec["model_dir"]) / "READY").read_text())
    if ready.get("model_id") != spec["model_id"] or ready.get("revision") != spec["revision"]:
        return {
            "ok": False,
            "error": "revision_mismatch",
            "ready": {"model_id": ready.get("model_id"), "revision": ready.get("revision")},
            "spent_usd_estimated": spent(),
            "elapsed_seconds": time.perf_counter() - started,
        }

    from vllm import LLM, SamplingParams

    load_started = time.perf_counter()
    llm = None
    quant_used = ""
    errors = []
    for quant in ("awq_marlin", "awq"):
        try:
            llm = LLM(
                model=spec["model_dir"],
                quantization=quant,
                dtype="float16",
                max_model_len=8192,
                gpu_memory_utilization=0.90,
                enforce_eager=True,
                tensor_parallel_size=1,
                max_num_seqs=1,
                disable_log_stats=True,
            )
            quant_used = quant
            break
        except Exception as exc:
            errors.append(f"{quant}: {type(exc).__name__}: {exc}")
            llm = None
    if llm is None:
        return {
            "ok": False,
            "error": "load_failed",
            "errors": errors,
            "gpu_name": gpu_name,
            "spent_usd_estimated": spent(),
            "elapsed_seconds": time.perf_counter() - started,
        }
    load_seconds = time.perf_counter() - load_started
    import vllm

    payload = json.loads(Path("/out/payload.json").read_text())
    grouped: dict[str, list] = {}
    order = []
    for item in payload:
        if item["id"] not in grouped:
            order.append(item["id"])
            grouped[item["id"]] = []
        grouped[item["id"]].append(item)

    sampling = SamplingParams(
        temperature=0,
        max_tokens=192,
        seed=0,
        stop=["<|im_end|>", "<|endoftext|>"],
        skip_special_tokens=False,
    )
    queries = []
    arm_gen = {arm: 0.0 for arm in ARM_ORDER}
    planned = int(spec["sample_size"])
    n_target = planned
    probe_query_seconds = None
    stop_reason = ""

    def checkpoint(done_reason: str) -> dict:
        load_share = load_seconds / len(ARM_ORDER)
        body = {
            "ok": True,
            "model_id": spec["model_id"],
            "revision": spec["revision"],
            "vllm_version": vllm.__version__,
            "quantization": quant_used,
            "gpu_name": gpu_name,
            "gpu": spec["gpu"],
            "load_seconds": load_seconds,
            "probe_query_seconds": probe_query_seconds,
            "sample_size_planned": planned,
            "sample_size_ran": len(queries),
            "sample_size_target_after_probe": n_target,
            "stop_reason": done_reason,
            "queries": queries,
            "arm_seconds": {arm: arm_gen[arm] + load_share for arm in ARM_ORDER},
            "spent_usd_estimated": spent(),
            "elapsed_seconds": time.perf_counter() - started,
            "load_errors": errors,
            "hourly_usd": hourly,
            "job_cap_usd": job_cap,
        }
        Path("/out/partial.json").write_text(json.dumps(body))
        results_volume.commit()
        return body

    for index, row_id in enumerate(order):
        if index == 1 and probe_query_seconds is not None:
            n_target = shrink_after_probe(
                planned,
                spent(),
                probe_query_seconds,
                hourly,
                job_cap,
            )
        if index >= n_target:
            stop_reason = stop_reason or "shrunk_after_probe"
            break
        if index > 0 and probe_query_seconds is not None:
            next_cost = probe_query_seconds / 3600 * hourly * 1.25
            if spent() + next_cost > job_cap:
                stop_reason = "stopped_before_cap"
                break
        arms_out = {}
        query_seconds = 0.0
        query_text = grouped[row_id][0]["query"]
        incomplete = False
        for item in grouped[row_id]:
            if spent() > job_cap:
                stop_reason = "stopped_before_cap"
                incomplete = True
                break
            t0 = time.perf_counter()
            generated = llm.generate([item["prompt"]], sampling, use_tqdm=False)
            dt = time.perf_counter() - t0
            text = generated[0].outputs[0].text
            arm_gen[item["arm"]] += dt
            query_seconds += dt
            arms_out[item["arm"]] = {
                "called": extract_called_tools(text),
                "seconds": dt,
                "output": text[:2000],
                "n_shown": len(item["valid_names"]),
                "shown": item["shown"],
                "prompt_tokens": item["prompt_tokens"],
            }
        if incomplete or len(arms_out) != len(ARM_ORDER):
            stop_reason = stop_reason or "partial_query"
            break
        queries.append({"id": row_id, "query": query_text, "arms": arms_out})
        if index == 0:
            probe_query_seconds = query_seconds
        print(
            json.dumps(
                {
                    "event": "query",
                    "index": index,
                    "id": row_id,
                    "seconds": query_seconds,
                    "spent_usd_estimated": spent(),
                    "n_target": n_target,
                }
            ),
            flush=True,
        )
        checkpoint(stop_reason)

    result = checkpoint(stop_reason)
    Path("/out/result.json").write_text(json.dumps(result))
    results_volume.commit()
    return result


@app.local_entrypoint()
def main() -> None:
    from frontier_driver import execute

    execute(
        prefetch=prefetch,
        score_sample=score_sample,
        infer=infer,
        read_saved=read_saved,
        results_volume=results_volume,
    )
