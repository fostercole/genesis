"""Write the seed-0 50,000-row train file from the frozen id list. No GPU."""

from __future__ import annotations

import json
from pathlib import Path

from datasets import load_dataset

from toolret_smoke.tools import parse_tool, render_tool

ROOT = Path(__file__).resolve().parent
IDS = ROOT / "data" / "train_50k.ids"
UNORDERED = ROOT / "data" / "train_50k.unordered.jsonl"
ORDERED = ROOT / "data" / "train_50k.jsonl"
DESC_CHARS = 2000
QUERY_CHARS = 3000
INSTRUCTION_CHARS = 1500


def compact_tool(raw: str) -> dict:
    tool = parse_tool(raw)
    tool["description"] = (tool.get("description") or "")[:DESC_CHARS]
    return {"name": tool.get("name") or "", "text": render_tool(tool), "parsed": bool(tool.get("parsed"))}


def main() -> None:
    wanted = IDS.read_text().splitlines()
    if len(wanted) != 50_000 or len(set(wanted)) != 50_000:
        raise SystemExit(f"expected 50,000 unique train ids, found {len(wanted)}")
    want = set(wanted)
    print("streaming train bodies", flush=True)
    ds = load_dataset("mangopy/ToolRet-Training-20w", split="train", streaming=True)
    found = 0
    unparsed = 0
    offsets: dict[str, int] = {}
    with UNORDERED.open("w") as handle:
        for index, row in enumerate(ds):
            row_id = row["id"]
            if row_id not in want or row_id in offsets:
                continue
            positives = [compact_tool(raw) for raw in row["positive"]]
            negatives = [compact_tool(raw) for raw in row["negative"]]
            unparsed += sum(1 for tool in positives + negatives if not tool["parsed"])
            record = {
                "id": row_id,
                "query": (row["query"] or "")[:QUERY_CHARS],
                "instruction": (row["prompt"] or "")[:INSTRUCTION_CHARS],
                "positives": positives,
                "negatives": negatives,
            }
            offsets[row_id] = handle.tell()
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            found += 1
            if found % 5000 == 0:
                print(f"wrote {found}", flush=True)
            if found == 50_000:
                break
        if found != 50_000:
            raise SystemExit(f"found {found} of 50,000 train rows")
    print("ordering to seed-0 shuffle", flush=True)
    with UNORDERED.open() as source, ORDERED.open("w") as handle:
        for row_id in wanted:
            source.seek(offsets[row_id])
            handle.write(source.readline())
    UNORDERED.unlink()
    print(
        json.dumps(
            {
                "rows": 50_000,
                "bytes": ORDERED.stat().st_size,
                "unparsed_tools": unparsed,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
