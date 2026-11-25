#!/usr/bin/env bash
# Runtime evidence for seamless hooks (no Cursor UI required).
# Exit 0 when sessionStart / every-3rd-stop / drift notes all behave.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
SESSION="$(mktemp)"
export CONTEXT_ROT_SESSION="$SESSION"
trap 'rm -f "$SESSION"' EXIT

has_followup() { printf '%s' "$1" | grep -q 'followup_message'; }
has_text() { printf '%s' "$1" | grep -q "$2"; }

echo "1) sessionStart"
out="$(bash .cursor/hooks/rot-session-start.sh)"
has_text "$out" 'Background pulse is on'

echo "2) clean stops (3rd speaks)"
s1="$(printf '%s' '{"status":"completed","loop_count":0}' | bash .cursor/hooks/rot-pulse.sh | tr -d '\n')"
s2="$(printf '%s' '{"status":"completed","loop_count":0}' | bash .cursor/hooks/rot-pulse.sh | tr -d '\n')"
s3="$(printf '%s' '{"status":"completed","loop_count":0}' | bash .cursor/hooks/rot-pulse.sh | tr -d '\n')"
if has_followup "$s1"; then echo "unexpected speak on stop 1: $s1" >&2; exit 1; fi
if has_followup "$s2"; then echo "unexpected speak on stop 2: $s2" >&2; exit 1; fi
has_text "$s3" 'no drift detected'

echo "3) force drift + postToolUse + stop"
python3 - <<'PY'
from pathlib import Path
import os
from context_guard import ContextRotGuard
path = Path(os.environ["CONTEXT_ROT_SESSION"])
g = ContextRotGuard.load(path)
g.config.mention_gap = 3
for _ in range(3):
    g.add_turn("assistant", "Reworking marketing homepage hero spacing only")
g._save()
assert g.evaluate().drift
print("drift_ready")
PY
tool="$(printf '%s' '{"tool_name":"Shell"}' | bash .cursor/hooks/rot-after-tool.sh | tr -d '\n')"
has_text "$tool" 'additional_context'
has_text "$tool" 'drift detected'
stop="$(printf '%s' '{"status":"completed","loop_count":0}' | bash .cursor/hooks/rot-pulse.sh | tr -d '\n')"
has_text "$stop" 'followup_message'
has_text "$stop" 'drift detected'

echo "OK: seamless hook runtime evidence passed"
echo "stop3=$s3"
echo "tool=$tool"
echo "stop_drift=$stop"
