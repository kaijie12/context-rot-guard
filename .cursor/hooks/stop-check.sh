#!/usr/bin/env bash
# stop hook: run the goal oracle when the agent stops.
# Adapted from sample-harness-project, pointed at pytest instead of pnpm typecheck.
# Exit 0 = allow stop (pytest passed, or pytest is not installed → skip).
# Exit 1 = block stop (pytest ran and failed — fix and continue).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 0

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
fi

if ! "$PY" -c "import pytest" >/dev/null 2>&1; then
  echo "stop-check: pytest not installed — skipped" >&2
  exit 0
fi

LOG="$(mktemp)"
cleanup() { rm -f "$LOG"; }
trap cleanup EXIT

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
if "$PY" -m pytest -q >"$LOG" 2>&1; then
  echo "stop-check: pytest OK" >&2
  exit 0
fi

echo "stop-check: pytest FAILED — agent should fix and continue" >&2
tail -c 2000 "$LOG" >&2
exit 1
