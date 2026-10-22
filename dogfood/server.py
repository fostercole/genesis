"""Loopback-only, raw-score inference. Run with: python -m dogfood.server."""
from __future__ import annotations

import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import threading
import time

from toolret_smoke.score_rows import _forward, fit_tool_text
from toolret_smoke.tools import render_tool

INSTRUCTION = "Select the tools needed to complete the user's task."
MAX_BODY_BYTES = 8 * 1024 * 1024


def bounded_int(value, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def validate_request(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError("request must be an object")
    query = body.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 20000:
        raise ValueError("query must contain 1 to 20000 characters")
    tools = body.get("tools")
    if not isinstance(tools, list) or not 1 <= len(tools) <= 5000:
        raise ValueError("tools must contain 1 to 5000 entries")
    clean, names = [], set()
    for tool in tools:
        if not isinstance(tool, dict):
            raise ValueError("each tool must be an object")
        name, description = tool.get("name"), tool.get("description", "")
        if not isinstance(name, str) or not 1 <= len(name) <= 256 or name in names:
            raise ValueError("tool names must be unique nonempty strings, at most 256 characters")
        if not isinstance(description, str) or len(description) > 65536:
            raise ValueError("tool description must be a string of at most 65536 characters")
        params = tool.get("parameters", [])
        if isinstance(params, dict):
            params = list(params.get("properties", {}))
        if not isinstance(params, list) or len(params) > 200 or any(
            not isinstance(p, str) or len(p) > 256 for p in params
        ):
            raise ValueError("parameters must be a list of names or an object schema")
        clean.append({"name": name, "description": description, "parameters": params})
        names.add(name)
    return {
        "query": query,
        "tools": clean,
        "top_k": bounded_int(body.get("top_k", 10), 1, 50, "top_k"),
        "candidate_limit": bounded_int(body.get("candidate_limit", 50), 1, 100, "candidate_limit"),
        "budget_ms": bounded_int(body.get("budget_ms", 10000), 1, 120000, "budget_ms"),
    }


def terms(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return re.findall(r"[^\W_]+", text.casefold())


def preselect(query: str, tools: list[dict], limit: int) -> list[dict]:
    """BM25 shortlist, with stable ties. Never inject known-positive tools."""
    if len(tools) <= limit:
        return tools
    docs = [Counter(terms(render_tool(tool))) for tool in tools]
    lengths = [sum(doc.values()) for doc in docs]
    average = sum(lengths) / len(docs) or 1.0
    query_terms = set(terms(query))
    frequency = {word: sum(word in doc for doc in docs) for word in query_terms}
    scores = []
    for index, (doc, length) in enumerate(zip(docs, lengths)):
        score = 0.0
        for word in query_terms:
            tf = doc[word]
            if tf:
                idf = math.log(1 + (len(docs) - frequency[word] + 0.5) / (frequency[word] + 0.5))
                score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / average))
        scores.append((score, index))
    ranked = sorted(scores, key=lambda item: (-item[0], item[1]))
    return [tools[index] for _, index in ranked[:limit]]


class Ranker:
    def __init__(self, model, batch_size: int = 1, clock=time.monotonic):
        self.model = model
        self.batch_size = bounded_int(batch_size, 1, 16, "batch_size")
        self.clock = clock
        self.lock = threading.Lock()

    def rank(self, request: dict) -> dict:
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError("scorer is busy; keep the full tool menu")
        try:
            started = self.clock()
            deadline = started + request["budget_ms"] / 1000
            shortlist = preselect(request["query"], request["tools"], request["candidate_limit"])
            ranked = []
            for start in range(0, len(shortlist), self.batch_size):
                if self.clock() >= deadline:
                    raise TimeoutError("scoring budget exceeded; keep the full tool menu")
                chunk = shortlist[start:start + self.batch_size]
                options = [fit_tool_text(
                    self.model.tokenizer, request["query"], INSTRUCTION, tool, self.model.max_length
                ) for tool in chunk]
                values = _forward(self.model, {"id": "dogfood", "state": request["query"],
                                  "kind": "choice", "question": INSTRUCTION, "options": options})
                if not all(math.isfinite(value) for value in values):
                    raise RuntimeError("model produced non-finite scores")
                ranked.extend({"name": tool["name"], "score": value} for tool, value in zip(chunk, values))
            if self.clock() >= deadline:
                raise TimeoutError("scoring budget exceeded; keep the full tool menu")
            ranked.sort(key=lambda item: -item["score"])
            return {
                "selected": [item["name"] for item in ranked[:request["top_k"]]],
                "ranking": ranked,
                "input_count": len(request["tools"]),
                "candidate_count": len(shortlist),
                "prefilter": "bm25" if len(shortlist) < len(request["tools"]) else "none",
                "elapsed_ms": round((self.clock() - started) * 1000, 2),
                "score_type": "raw_logit_not_calibrated_probability",
            }
        finally:
            self.lock.release()


def make_server(ranker, host: str, port: int, metadata: dict) -> ThreadingHTTPServer:
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError("bind the local scorer to a loopback IP address")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log prompts, tool definitions, or request bodies.

        def reply(self, status: int, body: dict):
            encoded = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path != "/health":
                return self.reply(404, {"error": "not found"})
            self.reply(200, {"ready": True, **metadata})

        def do_POST(self):
            if self.path != "/rank":
                return self.reply(404, {"error": "not found"})
            if self.headers.get("Origin") or self.headers.get_content_type() != "application/json":
                return self.reply(415, {"error": "use a local application/json client"})
            try:
                self.connection.settimeout(10)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY_BYTES:
                    return self.reply(413, {"error": "body is empty or too large"})
                request = validate_request(json.loads(self.rfile.read(length)))
                self.reply(200, ranker.rank(request))
            except (ValueError, TypeError) as error:
                self.reply(400, {"error": str(error)})
            except (TimeoutError, BlockingIOError) as error:
                self.reply(503, {"error": str(error)})
            except Exception as error:
                # Model errors can include input text. Return only the exception type.
                self.reply(500, {"error": f"scoring failed ({type(error).__name__}); keep the full menu"})

    return ThreadingHTTPServer((host, port), Handler)


def load_model(checkpoint: Path, device: str, dtype: str):
    for name in ("model.json", "head.pt", "adapter/adapter_config.json", "adapter/adapter_model.safetensors"):
        if not (checkpoint / name).is_file():
            raise ValueError(f"checkpoint is missing {name}; download the tuned pass1/final directory")
    # The Mac path intentionally does not use CUDA quantization or device maps.
    for key in ("JEV_LOAD_4BIT", "JEV_LOAD_8BIT", "JEV_DEVICE_MAP", "JEV_MAX_MEMORY"):
        os.environ.pop(key, None)
    os.environ["JEV_TORCH_DTYPE"] = dtype
    import torch
    if device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS is unavailable. Use native arm64 Python on an updated macOS, or --device cpu.")
    from jev.model import DecisionModel
    model = DecisionModel.load(checkpoint, device=device)
    model.requires_grad_(False)
    return model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=("mps", "cpu"), default="mps")
    parser.add_argument("--dtype", choices=("float32", "float16"), default="float32")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args()
    model = load_model(args.checkpoint.expanduser().resolve(), args.device, args.dtype)
    server = make_server(Ranker(model, args.batch_size), args.host, args.port, {
        "device": args.device, "dtype": args.dtype, "batch_size": args.batch_size,
        "max_length": model.max_length, "checkpoint": str(args.checkpoint),
        "score_type": "raw_logit_not_calibrated_probability",
    })
    print(f"Genesis ready at http://{args.host}:{args.port} ({args.device}, {args.dtype})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
