"""Layer 3 — mechanical drift (Path B) and a Path A embedding stub."""

from __future__ import annotations

import re

from context_guard.models import CheckResult, DriftReport, GoalSpec, Turn

_STOP = {
    "that",
    "this",
    "with",
    "from",
    "your",
    "have",
    "will",
    "into",
    "than",
    "then",
    "them",
    "they",
    "what",
    "when",
    "where",
    "which",
    "while",
    "about",
    "after",
    "before",
    "under",
    "over",
    "done",
    "means",
    "must",
    "should",
    "dont",
    "don't",
    "the",
    "and",
    "for",
    "are",
    "was",
    "were",
    "you",
    "not",
    "but",
    "can",
    "all",
    "any",
    "our",
    "out",
    "use",
    "using",
    "only",
    "just",
    "like",
    "edit",
    "tests",
    "test",
    "file",
    "files",
    "code",
    "none",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")
_FILE = re.compile(
    r"(?:[\w.-]+/)*[\w.-]+\.(?:py|js|ts|tsx|jsx|md|css|json|toml|sh|yml|yaml)\b"
)
_DONE = re.compile(r"\b(done|completed|all set|finished|task complete)\b", re.IGNORECASE)


def goal_keywords(spec: GoalSpec) -> set[str]:
    blob = " ".join([spec.goal, spec.done_means, *spec.constraints])
    words = {match.group(0).lower() for match in _WORD.finditer(blob)}
    return {word for word in words if word not in _STOP}


def _contains_keyword(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    for word in keywords:
        if re.search(
            r"(?<![a-z0-9_-])%s(?![a-z0-9_-])" % re.escape(word),
            lowered,
        ):
            return True
    return False


def trailing_fail_streak(checks: list[CheckResult]) -> int:
    streak = 0
    for check in reversed(checks):
        if check.exit_code == 0:
            break
        streak += 1
    return streak


def allowlist_for(spec: GoalSpec) -> list[str]:
    derived = _FILE.findall(spec.goal + "\n" + spec.done_means + "\n" + "\n".join(spec.constraints))
    items: list[str] = []
    for raw in list(spec.allow_paths) + derived:
        text = raw.replace("\\", "/").strip()
        if text and text not in items:
            items.append(text)
    return items


def _path_allowed(path: str, allow: list[str]) -> bool:
    norm = path.replace("\\", "/")
    base = norm.rsplit("/", 1)[-1]
    for item in allow:
        token = item.replace("\\", "/")
        if not token:
            continue
        if token.endswith("/"):
            if norm.startswith(token) or norm.startswith(token.rstrip("/")):
                return True
            continue
        allow_base = token.rsplit("/", 1)[-1]
        if norm == token or base == allow_base or norm.endswith("/" + token):
            return True
    return False


def _files_in(turns: list[Turn]) -> list[str]:
    found: list[str] = []
    for turn in turns:
        for match in _FILE.findall(turn.content):
            if match not in found:
                found.append(match)
    return found


def render_drift_note(report: DriftReport) -> str:
    reasons = ", ".join(report.reasons) or "none"
    return (
        "[DRIFT]\n"
        "drift={drift} fail_streak={streak} block_done={block}\n"
        "reasons: {reasons}\n"
        "Stay on the pinned goal. Do not declare done while verify is red.\n"
    ).format(
        drift=str(report.drift).lower(),
        streak=report.fail_streak,
        block=str(report.block_done).lower(),
        reasons=reasons,
    )


def evaluate_mechanical(
    spec: GoalSpec,
    turns: list[Turn],
    checks: list[CheckResult],
    *,
    fail_streak_limit: int,
    mention_gap: int,
    side_quest_ratio: float,
    block_done_on_red: bool,
) -> DriftReport:
    """Path B sensor. `turns` should be the intent ring (recent), not the compacted window."""
    reasons: list[str] = []
    streak = trailing_fail_streak(checks)
    if streak >= fail_streak_limit:
        reasons.append("verify_stall")

    keywords = goal_keywords(spec)
    window = turns[-mention_gap:] if mention_gap > 0 else turns
    gap = False
    if keywords and len(turns) >= mention_gap:
        blob = "\n".join(turn.content for turn in window)
        gap = not _contains_keyword(blob, keywords)
        if gap:
            reasons.append("goal_mention_gap")

    allow = allowlist_for(spec)
    files = _files_in(window)
    outside_ratio: float | None = None
    if allow and len(files) >= 3:
        outside = [path for path in files if not _path_allowed(path, allow)]
        outside_ratio = len(outside) / float(len(files))
        if outside_ratio >= side_quest_ratio:
            reasons.append("side_quest")

    completion = False
    last = checks[-1] if checks else None
    if last is not None and last.exit_code != 0:
        recent_assistant = [turn for turn in turns if turn.role == "assistant"][-3:]
        completion = any(_DONE.search(turn.content) for turn in recent_assistant)
        if completion:
            reasons.append("completion_without_green")

    red = last is not None and last.exit_code != 0
    block = (block_done_on_red and red) or "verify_stall" in reasons or completion
    return DriftReport(
        drift=bool(reasons),
        reasons=reasons,
        fail_streak=streak,
        block_done=block,
        signals={
            "fail_streak": streak,
            "goal_mention_gap": gap,
            "side_quest_ratio": outside_ratio,
            "completion_without_green": completion,
            "keywords": sorted(keywords),
        },
    )


class MechanicalDriftDetector:
    """Path B detector. Construct with the same knobs as `GuardConfig`."""

    def __init__(
        self,
        *,
        fail_streak_limit: int = 3,
        mention_gap: int = 12,
        side_quest_ratio: float = 0.6,
        block_done_on_red: bool = True,
    ) -> None:
        self.fail_streak_limit = fail_streak_limit
        self.mention_gap = mention_gap
        self.side_quest_ratio = side_quest_ratio
        self.block_done_on_red = block_done_on_red

    def evaluate(
        self,
        spec: GoalSpec,
        turns: list[Turn],
        checks: list[CheckResult],
    ) -> DriftReport:
        return evaluate_mechanical(
            spec,
            turns,
            checks,
            fail_streak_limit=self.fail_streak_limit,
            mention_gap=self.mention_gap,
            side_quest_ratio=self.side_quest_ratio,
            block_done_on_red=self.block_done_on_red,
        )


class EmbeddingDriftDetector:
    """Path A stub. v1 does not call an embedding API."""

    def score(self, goal_text: str, recent_intent: str) -> float:
        raise NotImplementedError(
            "Embedding drift is not implemented in v1. "
            "Use MechanicalDriftDetector. Plug a cosine scorer in here later."
        )
