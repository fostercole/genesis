"""Freeze the seed-0 split and write the 32 dev rows the T4 scorer smoke scores.

No GPU. The 50,000-row train file is the id list only. This script does not train.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from datasets import load_dataset

from toolret_smoke.tools import parse_tool

DATASET = "mangopy/ToolRet-Training-20w"
DATASET_SHA = "fdf5a317455b1e60785de7ba587496aa6cc878e4"
SEED = 0
TRAIN_N = 50_000
DEV_N = 2_000
SMOKE_N = 32
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    print("streaming ToolRet-train for ids and counts", flush=True)
    ds = load_dataset(DATASET, split="train", streaming=True)
    ids: list[str] = []
    pos_sum = 0
    neg_sum = 0
    for index, row in enumerate(ds):
        ids.append(row["id"])
        pos_sum += len(row["positive"])
        neg_sum += len(row["negative"])
        if index and index % 40000 == 0:
            print(f"counted {index}", flush=True)
    n = len(ids)
    if n <= TRAIN_N + DEV_N:
        raise SystemExit(f"dataset has {n} rows, need more than {TRAIN_N + DEV_N}")
    if len(set(ids)) != n:
        raise SystemExit("ToolRet train ids are not unique; refusing to freeze the split")

    order = list(range(n))
    random.Random(SEED).shuffle(order)
    train_idx = order[:TRAIN_N]
    dev_idx = order[TRAIN_N : TRAIN_N + DEV_N]
    smoke_idx = dev_idx[:SMOKE_N]
    if set(train_idx) & set(dev_idx):
        raise SystemExit("train and dev indices overlap")

    (DATA / "train_50k.ids").write_text("".join(ids[i] + "\n" for i in train_idx))
    (DATA / "dev_2k.ids").write_text("".join(ids[i] + "\n" for i in dev_idx))

    want = set(smoke_idx)
    found: dict[int, dict] = {}
    print("second pass for 32 dev rows", flush=True)
    ds = load_dataset(DATASET, split="train", streaming=True)
    for index, row in enumerate(ds):
        if index not in want:
            continue
        positives = [parse_tool(raw) for raw in row["positive"]]
        negatives = [parse_tool(raw) for raw in row["negative"]]
        found[index] = {
            "id": row["id"],
            "source_index": index,
            "query": row["query"],
            "instruction": row["prompt"],
            "positives": positives,
            "negatives": negatives,
        }
        if len(found) == SMOKE_N:
            break
    if len(found) != SMOKE_N:
        raise SystemExit(f"found {len(found)} smoke rows, expected {SMOKE_N}")

    smoke_path = DATA / "dev_smoke_32.jsonl"
    with smoke_path.open("w") as handle:
        for index in smoke_idx:
            handle.write(json.dumps(found[index], ensure_ascii=False) + "\n")

    smoke_pos = sum(len(found[i]["positives"]) for i in smoke_idx)
    smoke_neg = sum(len(found[i]["negatives"]) for i in smoke_idx)
    manifest = {
        "dataset": DATASET,
        "dataset_sha": DATASET_SHA,
        "n_rows": n,
        "paper_stated_rows": 205826,
        "avg_targets": pos_sum / n,
        "avg_negatives": neg_sum / n,
        "seed": SEED,
        "shuffle": "random.Random(0).shuffle of dataset row indices",
        "train_ids": "data/train_50k.ids",
        "dev_ids": "data/dev_2k.ids",
        "train_n": TRAIN_N,
        "dev_n": DEV_N,
        "smoke_file": "data/dev_smoke_32.jsonl",
        "smoke_n": SMOKE_N,
        "smoke_ids": [found[i]["id"] for i in smoke_idx],
        "smoke_avg_targets": smoke_pos / SMOKE_N,
        "smoke_avg_negatives": smoke_neg / SMOKE_N,
        "train_dev_disjoint": True,
        "note": "Id lists are the seed-0 train and dev draws. Bodies for the 32 scored dev rows are in dev_smoke_32.jsonl. The 50,000-row training run is not started.",
    }
    (DATA / "split_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in (
        "n_rows", "avg_targets", "avg_negatives", "smoke_avg_targets", "smoke_avg_negatives"
    )}, indent=2), flush=True)


if __name__ == "__main__":
    main()
