#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(pi --version)"
if [[ "$version" != "0.85.1" ]]; then
  echo "Genesis targets Pi 0.85.1; found $version. Verify the extension API if errors occur." >&2
fi
exec pi --extension "$root/dogfood/pi/genesis.ts" "$@"
