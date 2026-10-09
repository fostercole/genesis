"""Build the dev BM25 top 50. No GPU, no test split, no training.

Each dev query is searched against mangopy/ToolRet-Tools. The indexed text is
the tool truncated to name, description, and parameter names. The query is the
row's query field, not the instruction. The plan does not say to force a
missed positive into that list, so every positive is kept and the rest of the
50 is filled from BM25.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import bm25s
from datasets import load_dataset
from huggingface_hub import dataset_info

from toolret_smoke.dev_eval import CANDIDATES, assemble_candidates
from toolret_smoke.tools import parse_tool, render_tool

ROOT = Path(__file__).resolve().parent
DEV_IDS = ROOT / "data" / "dev_2k.ids"
OUTPUT = ROOT / "data" / "dev_bm25_top50.jsonl"
MANIFEST = ROOT / "data" / "dev_bm25_manifest.json"
ROW_CACHE = ROOT / "data" / "dev_2k.raw.jsonl"
FETCH = 200
TOOL_REPO = "mangopy/ToolRet-Tools"
TRAIN_REPO = "mangopy/ToolRet-Training-20w"
TRAIN_SHA = "fdf5a317455b1e60785de7ba587496aa6cc878e4"
CONFIGS = ("code", "customized", "web")


def canonical_json(raw: str) -> str | None:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def corpus_tool(config: str, row: dict) -> dict:
    raw = row["documentation"]
    parsed = parse_tool(raw)
    text = render_tool(parsed)
    if not (parsed["name"] or parsed["description"] or parsed["parameters"]):
        text = raw
    return {
        "corpus_id": f"{config}:{row['id']}",
        "name": parsed["name"],
        "description": parsed["description"] if text != raw else raw,
        "parameters": list(parsed["parameters"]),
        "text": text,
        "raw": raw,
    }


def load_corpus() -> list[dict]:
    tools = []
    for config in CONFIGS:
        for row in load_dataset(TOOL_REPO, config, split="tools"):
            tools.append(corpus_tool(config, row))
    if len(tools) != 44453:
        raise SystemExit(f"expected 44,453 tools, found {len(tools)}")
    if len({tool["corpus_id"] for tool in tools}) != len(tools):
        raise SystemExit("tool ids are not unique across configs")
    return tools


def index_matches(tools: list[dict]) -> tuple[dict, dict, dict]:
    by_raw: dict[str, int] = {}
    by_canonical: dict[str, int] = {}
    by_identity: dict[tuple, int] = {}
    for index, tool in enumerate(tools):
        by_raw.setdefault(tool["raw"], index)
        canonical = canonical_json(tool["raw"])
        if canonical is not None:
            by_canonical.setdefault(canonical, index)
        identity = (tool["name"], tool["description"], tuple(tool["parameters"]))
        if any(identity):
            by_identity.setdefault(identity, index)
    return by_raw, by_canonical, by_identity


def match_positive(raw: str, tools: list[dict], by_raw: dict, by_canonical: dict, by_identity: dict):
    if raw in by_raw:
        return tools[by_raw[raw]], "exact"
    canonical = canonical_json(raw)
    if canonical is not None and canonical in by_canonical:
        return tools[by_canonical[canonical]], "canonical"
    parsed = parse_tool(raw)
    identity = (parsed["name"], parsed["description"], tuple(parsed["parameters"]))
    if any(identity) and identity in by_identity:
        return tools[by_identity[identity]], "fields"
    return {
        "corpus_id": None,
        "name": parsed["name"],
        "description": parsed["description"],
        "parameters": list(parsed["parameters"]),
        "text": render_tool(parsed),
        "raw": raw,
    }, "unmatched"


def load_dev_rows(wanted: list[str]) -> dict[str, dict]:
    need = set(wanted)
    if ROW_CACHE.is_file():
        found = {}
        with ROW_CACHE.open() as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    found[row["id"]] = row
        if set(found) == need:
            print(f"loaded {len(found)} cached dev rows", flush=True)
            return found
    found = {}
    print(f"streaming {TRAIN_REPO} for {len(need)} dev rows", flush=True)
    dataset = load_dataset(TRAIN_REPO, split="train", streaming=True)
    for seen, row in enumerate(dataset, start=1):
        row_id = row["id"]
        if row_id in need and row_id not in found:
            found[row_id] = {
                "id": row_id,
                "query": row["query"] or "",
                "prompt": row["prompt"] or "",
                "positive": list(row["positive"]),
            }
            if len(found) == len(need):
                break
        if seen % 40000 == 0:
            print(f"scanned {seen}, found {len(found)}", flush=True)
    if len(found) != len(need):
        raise SystemExit(f"found {len(found)} of {len(need)} dev rows")
    with ROW_CACHE.open("w") as handle:
        for row_id in wanted:
            handle.write(json.dumps(found[row_id], ensure_ascii=False) + "\n")
    return found


def retrieve(tools: list[dict], queries: list[str]) -> tuple[list[list[int]], list[list[float]]]:
    tokens = bm25s.tokenize([tool["text"] for tool in tools], stopwords="english", show_progress=False)
    retriever = bm25s.BM25()
    retriever.index(tokens, show_progress=False)
    texts = []
    for query in queries:
        text = (query or "").strip() or "NONE"
        tokenized = bm25s.tokenize(text, stopwords="english", show_progress=False)
        if len(tokenized.ids[0]) == 0:
            text = "NONE"
        texts.append(text)
    batched = bm25s.tokenize(texts, stopwords="english", show_progress=False)
    results, scores = retriever.retrieve(batched, k=FETCH, show_progress=False)
    return results.tolist(), scores.tolist()


def main() -> None:
    wanted = [line.strip() for line in DEV_IDS.read_text().splitlines() if line.strip()]
    if len(wanted) != 2000 or len(set(wanted)) != 2000:
        raise SystemExit(f"expected 2,000 unique dev ids, found {len(wanted)}")
    tool_sha = dataset_info(TOOL_REPO).sha
    train_sha = dataset_info(TRAIN_REPO).sha
    if train_sha != TRAIN_SHA:
        raise SystemExit(f"training set sha is {train_sha}, expected {TRAIN_SHA}")

    tools = load_corpus()
    by_raw, by_canonical, by_identity = index_matches(tools)
    rows = load_dev_rows(wanted)
    queries = [rows[row_id]["query"] or "" for row_id in wanted]
    print("indexing BM25", flush=True)
    rankings, score_rows = retrieve(tools, queries)

    match_counts: Counter[str] = Counter()
    totals = Counter()
    unmatched_examples = []
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w") as handle:
        for row_id, ranking, bm25_scores in zip(wanted, rankings, score_rows):
            source = rows[row_id]
            positives = []
            for raw in source["positive"]:
                tool, how = match_positive(raw, tools, by_raw, by_canonical, by_identity)
                match_counts[how] += 1
                positives.append(tool)
                if how == "unmatched" and len(unmatched_examples) < 5:
                    unmatched_examples.append({"id": row_id, "raw": raw[:240]})
            bm25_ranked = []
            for index, score in zip(ranking, bm25_scores):
                tool = tools[int(index)]
                bm25_ranked.append({**tool, "bm25_score": float(score)})
            packed = assemble_candidates(positives, bm25_ranked, k=CANDIDATES)
            n_relevant = sum(1 for tool in packed["candidates"] if tool["relevant"])
            if len(packed["candidates"]) != CANDIDATES:
                raise SystemExit(f"{row_id} has {len(packed['candidates'])} candidates")
            if packed["n_positive"] < 1:
                raise SystemExit(f"{row_id} has no positive")
            if n_relevant + packed["n_positive_outside"] != packed["n_positive"]:
                raise SystemExit(f"{row_id} lost a positive while building the candidate list")
            totals["n_positive"] += packed["n_positive"]
            totals["n_positive_in_bm25"] += packed["n_positive_in_bm25"]
            totals["n_injected"] += packed["n_injected"]
            totals["n_positive_outside"] += packed["n_positive_outside"]
            record = {
                "id": row_id,
                "query": source["query"] or "",
                "instruction": source["prompt"] or "",
                "n_positive": packed["n_positive"],
                "n_positive_in_bm25": packed["n_positive_in_bm25"],
                "n_injected": packed["n_injected"],
                "n_positive_outside": packed["n_positive_outside"],
                "candidates": [
                    {
                        "corpus_id": tool["corpus_id"],
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"],
                        "relevant": tool["relevant"],
                        "bm25_rank": tool["bm25_rank"],
                        "injected": tool["injected"],
                    }
                    for tool in packed["candidates"]
                ],
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest = {
        "rows": len(wanted),
        "candidates_per_row": CANDIDATES,
        "tool_repo": TOOL_REPO,
        "tool_sha": tool_sha,
        "tool_rows": len(tools),
        "train_repo": TRAIN_REPO,
        "train_sha": train_sha,
        "bm25": {
            "library": "bm25s",
            "version": bm25s.__version__,
            "method": "lucene",
            "k1": 1.5,
            "b": 0.75,
            "stopwords": "english",
            "fetch_k": FETCH,
            "query": "row query only; the instruction is not concatenated",
            "document": "name, description, and parameter names via parse_tool and render_tool",
        },
        "candidate_policy": (
            "The plan does not say to keep a positive BM25 missed. "
            "Every unique positive is kept, and the remaining slots up to 50 "
            "are filled from the BM25 ranking. Lowest non-positives are dropped "
            "to stay at 50. A positive that still does not fit counts as a miss."
        ),
        "positive_match_counts": dict(match_counts),
        "n_positive": totals["n_positive"],
        "n_positive_in_bm25": totals["n_positive_in_bm25"],
        "n_injected": totals["n_injected"],
        "n_positive_outside": totals["n_positive_outside"],
        "unmatched_examples": unmatched_examples,
        "output": "data/dev_bm25_top50.jsonl",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({key: manifest[key] for key in (
        "rows", "positive_match_counts", "n_positive", "n_positive_in_bm25",
        "n_injected", "n_positive_outside",
    )}, indent=2), flush=True)


if __name__ == "__main__":
    main()
