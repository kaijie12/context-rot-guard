#!/usr/bin/env bash
# sessionStart: pin mission/unit when one exists. Investigating chats stay silent.
set -u
PKG="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT="${CONTEXT_GUARD_ROOT:-$PKG}"
cd "$PKG" || exit 0
if [[ -x "$PKG/.venv/bin/python" ]]; then
  PY="$PKG/.venv/bin/python"
else
  PY="python3"
fi
export PYTHONPATH="${PKG}/src${PYTHONPATH:+:$PYTHONPATH}"
"$PY" -m context_guard hook --event sessionStart --root "$ROOT"
exit 0
