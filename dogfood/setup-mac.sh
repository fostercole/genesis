#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo "Run this script in a native Apple Silicon terminal on your Mac." >&2
  exit 1
fi
python_cmd="${GENESIS_PYTHON:-python3}"
"$python_cmd" -c 'import sys; assert (3, 10) <= sys.version_info < (3, 14), "Use Python 3.10 through 3.13 (3.12 recommended)."'
if [[ ! -x "$root/.venv-dogfood/bin/python" ]]; then
  "$python_cmd" -m venv "$root/.venv-dogfood"
fi
py="$root/.venv-dogfood/bin/python"
"$py" -m pip install --upgrade pip
"$py" -m pip install -r "$root/dogfood/requirements-mac.txt"
upstream="$root/.cache/open-jev-dogfood"
revision=bd4118882f733574a3250a4b65fe4d884130c08b
if [[ ! -d "$upstream" ]]; then
  mkdir -p "$(dirname "$upstream")"
  git init "$upstream"
  git -C "$upstream" remote add origin https://github.com/Zefan-Cai/Open-Jev.git
  git -C "$upstream" fetch --depth 1 origin "$revision"
  git -C "$upstream" checkout --detach FETCH_HEAD
elif [[ "$(git -C "$upstream" rev-parse HEAD)" != "$revision" ]]; then
  echo "Existing Open-Jev checkout has a different revision: $upstream" >&2
  exit 1
fi
"$py" -m pip install --no-deps -e "$upstream"
npm ci --prefix "$root/dogfood/pi" --omit=dev --ignore-scripts --no-audit --no-fund
"$py" -c 'import torch; print("MPS available:", torch.backends.mps.is_available()); assert torch.backends.mps.is_available(), "Update macOS and use native arm64 Python."'
"$py" -m pip freeze > "$root/.cache/dogfood-environment.txt"
echo "Setup complete. Download the tuned checkpoint, then run bash dogfood/serve.sh."
