#!/usr/bin/env bash
# beforeSubmitPrompt: record the user prompt. Questions do not lock a mission.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 0
input="$(cat || true)"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
fi
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
printf '%s' "$input" | "$PY" -m context_guard hook --event beforeSubmitPrompt --root "$ROOT" >/dev/null 2>&1 || true
printf '%s\n' '{}'
exit 0
