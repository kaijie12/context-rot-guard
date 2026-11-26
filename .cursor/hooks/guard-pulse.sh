#!/usr/bin/env bash
# stop: follow up only when the open goal was abandoned or the loop says escalate.
set -u
PKG="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT="${CONTEXT_GUARD_ROOT:-$PKG}"
cd "$PKG" || exit 0
input="$(cat || true)"
if [[ -x "$PKG/.venv/bin/python" ]]; then
  PY="$PKG/.venv/bin/python"
else
  PY="python3"
fi
export PYTHONPATH="${PKG}/src${PYTHONPATH:+:$PYTHONPATH}"
printf '%s' "$input" | "$PY" -m context_guard hook --event stop --root "$ROOT"
exit 0
