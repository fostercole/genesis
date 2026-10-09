"""Pi loop startup.

Loads JEV_API_KEY from /workspace/.env when that file exists. A missing file
or an empty value does not block, and this process does not start the full
menu, BM25, original Open-Jev-2B, or tuned 2B arms.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ENV_PATH = Path("/workspace/.env")
ARM_PATH = Path("results/normal-jev-arm.json")
PI_RESULT_PATH = Path("results/pi_loop.json")
HARD_CAP_USD = 15.0


def parse_env_text(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines. Blank lines and # comments are skipped."""
    found: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            found[key] = value
    return found


def load_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.is_file():
        return {}
    return parse_env_text(path.read_text())


def load_jev_api_key(path: Path = ENV_PATH) -> bool:
    """Set JEV_API_KEY from path when the value is non-empty.

    Returns True only when a key was loaded. Does not print the value.
    """
    value = load_env_file(path).get("JEV_API_KEY", "").strip()
    if not value:
        return False
    os.environ["JEV_API_KEY"] = value
    return True


def recorded_spend_usd(path: Path = PI_RESULT_PATH) -> float:
    if not path.is_file():
        return 0.0
    data = json.loads(path.read_text())
    return float(data.get("spend_usd") or 0)


def hosted_arm_record(loaded: bool, spend_usd: float) -> dict:
    if not loaded:
        return {
            "included": False,
            "called": False,
            "waiting_on": str(ENV_PATH),
            "spend_usd": 0,
            "reason": (
                "The hosted Jev arm is waiting on /workspace/.env and was not called. "
                "The file is present and JEV_API_KEY is empty."
            ),
        }
    if spend_usd >= HARD_CAP_USD:
        return {
            "included": False,
            "called": False,
            "spend_usd": 0,
            "reason": (
                f"Recorded Pi spend is already ${spend_usd:.2f}, so adding the "
                "hosted Jev arm would cross the $15 cap. The arm was not called."
            ),
        }
    return {
        "included": False,
        "called": False,
        "spend_usd": 0,
        "reason": (
            "JEV_API_KEY is loaded, but results/pi_loop.json has no full-menu "
            "Sonnet ground truth yet. The hosted Jev arm was not called, and "
            "this process did not start the other arms."
        ),
    }


def write_arm(record: dict, path: Path = ARM_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")


def main() -> None:
    loaded = load_jev_api_key(ENV_PATH)
    record = hosted_arm_record(loaded, recorded_spend_usd())
    write_arm(record)
    print(
        json.dumps(
            {
                "env_file_present": ENV_PATH.is_file(),
                "jev_api_key_loaded": loaded,
                "hosted_arm_called": record["called"],
                "included": record["included"],
            }
        )
    )


if __name__ == "__main__":
    main()
