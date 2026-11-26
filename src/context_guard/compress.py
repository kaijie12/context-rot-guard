"""Layer 1 — extractive compaction into a SessionDigest."""

from __future__ import annotations

import re

from context_guard.models import CheckResult, GoalSpec, SessionDigest, Turn

_DONE_LINE = re.compile(
    r"\b(implemented|fixed|added|updated|passing|completed)\b",
    re.IGNORECASE,
)
_OPEN_LINE = re.compile(
    r"\b(TODO|FIXME|remaining|still need|not yet|next:)\b",
    re.IGNORECASE,
)
_EMPTY = "_(none recorded)_"


def estimate_tokens(text: str) -> int:
    """Rough budget: 4 characters ≈ 1 token. Empty text is 0."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def truncate_text(content: str, limit: int) -> str:
    """Keep the head and a short tail so a trailing assertion is not the first thing cut."""
    if limit <= 0 or len(content) <= limit:
        return content
    tail = min(120, max(0, limit // 4))
    marker = "\n…[truncated {n} chars]…\n"
    head = limit - tail - len(marker.format(n=0))
    if head < 40:
        return content[:limit] + "…"
    omitted = len(content) - head - tail
    return content[:head] + marker.format(n=omitted) + content[-tail:]


def _clip_lines(turns: list[Turn], pattern: re.Pattern[str], limit: int = 6) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for turn in turns:
        text = truncate_text(turn.content, 400) if turn.role == "tool" else turn.content
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if not line or len(line) > 180 or not pattern.search(line):
                continue
            item = "%s: %s" % (turn.role, line)
            if item in seen:
                continue
            seen.add(item)
            found.append(item)
            if len(found) >= limit:
                return found
    return found


def _merge(prior: list[str], extra: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    for item in list(prior) + list(extra):
        if not item or item == _EMPTY or item in merged:
            continue
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged or [_EMPTY]


def last_verify(spec: GoalSpec, checks: list[CheckResult]) -> dict[str, object] | None:
    if not checks:
        return None
    last = checks[-1]
    tail = last.output.strip()
    if len(tail) > 240:
        tail = tail[-240:]
    return {
        "cmd": spec.check_cmd,
        "exit_code": last.exit_code,
        "at_turn": last.at_turn,
        "output_tail": tail,
    }


def build_digest(
    spec: GoalSpec,
    dropped: list[Turn],
    checks: list[CheckResult],
    risks: list[str],
    prior: SessionDigest | None = None,
) -> SessionDigest:
    """Fold dropped turns into the frozen digest schema. Goal is always `spec.goal`."""
    done = _merge(
        prior.done_so_far if prior else [],
        _clip_lines(dropped, _DONE_LINE),
        6,
    )
    open_items = _merge(
        prior.open_items if prior else [],
        _clip_lines(dropped, _OPEN_LINE),
        6,
    )
    cleaned: list[str] = []
    for note in risks:
        text = " ".join(str(note).split())
        if text and text not in cleaned:
            cleaned.append(text)
    return SessionDigest(
        goal=spec.goal,
        constraints=list(spec.constraints),
        done_so_far=done,
        open_items=open_items,
        last_verify=last_verify(spec, checks),
        risks=cleaned[-6:] or [_EMPTY],
    )


def render_digest(digest: SessionDigest) -> str:
    constraints = ", ".join(digest.constraints) if digest.constraints else _EMPTY
    verify = digest.last_verify
    if verify:
        verify_text = "cmd={cmd}, exit_code={exit_code}, at_turn={at_turn}".format(
            cmd=verify.get("cmd"),
            exit_code=verify.get("exit_code"),
            at_turn=verify.get("at_turn"),
        )
        tail = verify.get("output_tail") or ""
        if tail:
            verify_text = "%s, output_tail=%s" % (verify_text, tail)
    else:
        verify_text = _EMPTY
    return (
        "## SessionDigest\n"
        "- Goal: {goal}\n"
        "- Constraints: {constraints}\n"
        "- Done so far: {done}\n"
        "- Open: {open_items}\n"
        "- Last verify: {verify}\n"
        "- Risks / drift notes: {risks}\n"
    ).format(
        goal=digest.goal,
        constraints=constraints,
        done="; ".join(digest.done_so_far),
        open_items="; ".join(digest.open_items),
        verify=verify_text,
        risks="; ".join(digest.risks),
    )
