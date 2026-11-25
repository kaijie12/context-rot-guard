#!/usr/bin/env bash
# sessionStart: pin mission/unit when one exists. Investigating chats stay silent.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 0
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
fi
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
"$PY" -m context_guard hook --event sessionStart --root "$ROOT"
exit 0
