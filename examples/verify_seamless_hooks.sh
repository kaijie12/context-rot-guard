#!/usr/bin/env bash
# Smoke the context-guard Cursor hooks (no IDE required).
# Exit 0 when arm → on-unit silence → sidetrack redirect behave.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
TMP="$(mktemp -d)"
export CONTEXT_GUARD_ROOT="$TMP"
trap 'rm -rf "$TMP"' EXIT

cid="hook-smoke"

echo "1) sessionStart (investigate — empty)"
out="$(bash .cursor/hooks/guard-session-start.sh)"
test "$out" = '{}' || { echo "expected empty sessionStart, got $out" >&2; exit 1; }

echo "2) beforeSubmitPrompt arms Current unit"
printf '%s' "{\"conversation_id\":\"$cid\",\"prompt\":\"Current unit: add a function add(a, b) that returns the sum of two numbers\"}" \
  | bash .cursor/hooks/guard-before-prompt.sh >/dev/null
state="$TMP/.context-guard/chats/${cid}.json"
test -f "$state" || { echo "missing chat state $state" >&2; exit 1; }
python3 - <<PY
import json
from pathlib import Path
data = json.loads(Path("$state").read_text())
assert data.get("unit") and "add(a, b)" in data["unit"]["goal"], data
print("unit_armed")
PY

echo "3) stop after on-unit reply → silence"
printf '%s' "{\"conversation_id\":\"$cid\",\"text\":\"The check passed. add(a, b) returns the sum of two numbers.\"}" \
  | bash .cursor/hooks/guard-after-response.sh >/dev/null
stop_quiet="$(printf '%s' "{\"conversation_id\":\"$cid\",\"status\":\"completed\"}" | bash .cursor/hooks/guard-pulse.sh | tr -d '\n')"
test "$stop_quiet" = '{}' || { echo "expected quiet stop, got $stop_quiet" >&2; exit 1; }

echo "4) stop after homepage sidetrack → Still the unit"
printf '%s' "{\"conversation_id\":\"$cid\",\"text\":\"I wrote a marketing homepage with a signup line instead.\"}" \
  | bash .cursor/hooks/guard-after-response.sh >/dev/null
stop_loud="$(printf '%s' "{\"conversation_id\":\"$cid\",\"status\":\"completed\"}" | bash .cursor/hooks/guard-pulse.sh)"
printf '%s' "$stop_loud" | grep -qi 'Still the unit' || { echo "expected redirect, got $stop_loud" >&2; exit 1; }
printf '%s' "$stop_loud" | grep -qi 'no drift' && { echo "must not say no drift: $stop_loud" >&2; exit 1; }

echo "OK: guard hook smoke passed"
echo "redirect=$stop_loud"
