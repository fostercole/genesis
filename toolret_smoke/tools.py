"""Parse ToolRet tool strings down to name, description, and parameter names."""

from __future__ import annotations

import json
from typing import Any


def parameter_names(parameters: Any) -> list[str]:
    if isinstance(parameters, dict):
        return [str(key) for key in parameters.keys()]
    if isinstance(parameters, list):
        names = []
        for item in parameters:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or ""
                if name:
                    names.append(str(name))
            elif item not in (None, ""):
                names.append(str(item))
        return names
    return []


def parse_tool(raw: str) -> dict[str, Any]:
    """Keep name, description, and parameter names. Drop example bodies."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        text = raw if isinstance(raw, str) else str(raw)
        return {
            "name": "",
            "description": text,
            "parameters": [],
            "parsed": False,
        }
    if not isinstance(obj, dict):
        return {
            "name": "",
            "description": raw if isinstance(raw, str) else str(raw),
            "parameters": [],
            "parsed": False,
        }
    description = obj.get("description") or ""
    if not isinstance(description, str):
        description = json.dumps(description, ensure_ascii=False, sort_keys=True)
    return {
        "name": str(obj.get("name") or ""),
        "description": description,
        "parameters": parameter_names(obj.get("parameters")),
        "parsed": True,
    }


def render_tool(tool: dict[str, Any], description_chars: int | None = None) -> str:
    description = tool.get("description") or ""
    if description_chars is not None:
        description = description[:description_chars]
    params = ", ".join(tool.get("parameters") or [])
    name = tool.get("name") or ""
    return f"{name}: {description}\nparameters: {params}"
