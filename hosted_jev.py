"""Hosted Jev API menu ranking. No GPU and no Modal spend.

The hosted arm is the OpenJEV decision API, not the local Open-Jev-2B
checkpoint. A choice over the 50-tool menu returns one selected tool and a
probability for every option. The top 10 are the highest probabilities.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

# TypeSafe hosts Jev. JEV_API_KEY authenticates here. openjev.sh is a different key.
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
HOSTED_LABEL = "hosted Jev top 10"
K = 10
DESCRIPTION_CHARS = 240


def option_key(index: int) -> str:
    return f"t{index:02d}"


def tool_blurb(tool: dict[str, Any]) -> str:
    name = str(tool.get("name") or tool.get("call_name") or "tool").strip()
    description = str(tool.get("description") or "").strip()
    if len(description) > DESCRIPTION_CHARS:
        description = description[:DESCRIPTION_CHARS].rstrip()
    parameters = [str(item).strip() for item in (tool.get("parameters") or []) if str(item).strip()]
    text = name if not description else f"{name}. {description}"
    if parameters:
        text = f"{text} Parameters: {', '.join(parameters[:8])}."
    return text


def build_choice_body(query: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    if len(tools) < 2:
        raise ValueError("hosted Jev choice needs at least two tools")
    criteria = {option_key(index): tool_blurb(tool) for index, tool in enumerate(tools)}
    return {
        "model": MODEL,
        "state": query,
        "questions": {
            "tool": {
                "type": "choice",
                "instructions": "Which one tool best fulfills the request? Pick exactly one of the listed tools.",
                "criteria": criteria,
            }
        },
    }


def _probability(probabilities: dict[str, Any], index: int) -> float:
    raw = probabilities.get(option_key(index), 0.0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def rank_indices(answer: dict[str, Any], n_tools: int) -> list[int]:
    """Highest probability first. Equal probabilities keep menu order."""
    probabilities = answer.get("probabilities") if isinstance(answer, dict) else None
    if not isinstance(probabilities, dict):
        probabilities = {}
    return sorted(range(n_tools), key=lambda index: (-_probability(probabilities, index), index))


def menu_order(answer: dict[str, Any], n_tools: int) -> tuple[list[int], str]:
    """Best-first indexes for the tools the API actually scored.

    A probability entry is a rank. Missing entries stay unranked, so a partial
    map is not filled in with menu order. A choice and no probabilities is
    that one tool at rank 1.
    """
    probabilities = answer.get("probabilities") if isinstance(answer, dict) else None
    if isinstance(probabilities, dict) and probabilities:
        present = [index for index in range(n_tools) if option_key(index) in probabilities]
        if present:
            ranked = sorted(present, key=lambda index: (-_probability(probabilities, index), index))
            return ranked, "probabilities"
    chosen = choice_index(answer, n_tools)
    if chosen is None:
        return [], "empty"
    return [chosen], "choice_only"


def choice_index(answer: dict[str, Any], n_tools: int) -> int | None:
    if not isinstance(answer, dict):
        return None
    choice = answer.get("choice")
    if not isinstance(choice, str) or len(choice) < 2 or not choice[1:].isdigit():
        return None
    index = int(choice[1:])
    if index < 0 or index >= n_tools:
        return None
    return index


def top_indices(answer: dict[str, Any], n_tools: int, k: int = K) -> list[int]:
    ranked = rank_indices(answer, n_tools)
    chosen = choice_index(answer, n_tools)
    if chosen is None:
        return ranked[:k]
    head = [chosen]
    head.extend(index for index in ranked if index != chosen)
    return head[:k]


def called_call_name(tools: list[dict[str, Any]], answer: dict[str, Any]) -> str | None:
    index = choice_index(answer, len(tools))
    if index is None:
        ranked = rank_indices(answer, len(tools))
        if not ranked or not (answer.get("probabilities") if isinstance(answer, dict) else None):
            return None
        index = ranked[0]
    name = tools[index].get("call_name")
    return str(name) if name else None


def redact(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def post_json(
    url: str,
    body: dict[str, Any],
    api_key: str,
    opener: Callable[..., Any] | None = None,
    timeout: float = 60,
) -> tuple[int, dict[str, Any]]:
    payload = json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
    if not raw.strip():
        return status, {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"hosted Jev returned non-JSON status {status}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"hosted Jev returned status {status} without an object")
    return status, parsed


def rank_query(
    query: str,
    tools: list[dict[str, Any]],
    api_key: str,
    opener: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = 4,
) -> dict[str, Any]:
    """One menu. Retries 429 and 503. Never includes the API key in the result."""
    body = build_choice_body(query, tools)
    started = time.perf_counter()
    last_status = 0
    last_error = ""
    for attempt in range(attempts):
        try:
            status, payload = post_json(ENDPOINT, body, api_key, opener=opener)
        except Exception as exc:
            last_status = 0
            last_error = redact(f"{type(exc).__name__}", api_key)
            if attempt + 1 == attempts:
                break
            sleep(min(8.0, 1.5 ** attempt))
            continue
        last_status = status
        if status == 200:
            answer = (payload.get("answers") or {}).get("tool") or {}
            if not isinstance(answer, dict):
                answer = {}
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            order, ranking = menu_order(answer, len(tools))
            top = [tools[index] for index in top_indices(answer, len(tools), K)]
            return {
                "ok": True,
                "status": status,
                "called": called_call_name(tools, answer),
                "choice": answer.get("choice"),
                "confidence": answer.get("confidence"),
                "order": order,
                "ranking": ranking,
                "top": [
                    {
                        "call_name": tool.get("call_name"),
                        "name": tool.get("name") or "",
                        "corpus_id": tool.get("corpus_id"),
                    }
                    for tool in top
                ],
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "seconds": time.perf_counter() - started,
                "model": payload.get("model") or MODEL,
            }
        if status in {429, 503} and attempt + 1 < attempts:
            sleep(min(20.0, 2.0 ** attempt))
            continue
        error = payload.get("error")
        if not isinstance(error, str):
            error = f"http {status}"
        last_error = redact(error, api_key)[:300]
        break
    return {
        "ok": False,
        "status": last_status,
        "called": None,
        "order": [],
        "ranking": "empty",
        "top": [],
        "seconds": time.perf_counter() - started,
        "error": last_error or f"http {last_status}",
    }
