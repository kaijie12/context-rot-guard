#!/usr/bin/env bash
# beforeSubmitPrompt: record the user prompt. Questions do not lock a mission.
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
printf '%s' "$input" | "$PY" -m context_guard hook --event beforeSubmitPrompt --root "$ROOT" >/dev/null 2>&1 || true
printf '%s\n' '{}'
exit 0
