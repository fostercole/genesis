#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
exec "$root/.venv-dogfood/bin/python" -m dogfood.server \
  --checkpoint "${GENESIS_CHECKPOINT:-$root/checkpoints/genesis}" \
  --device mps --dtype float32 --batch-size 1 "$@"
