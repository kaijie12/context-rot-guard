"""Shared records for a guarded session."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


def _optional_limit(value: int | None, *, minimum: int) -> int | None:
    if value is None:
        return None
    return max(minimum, int(value))


@dataclass
class AcceptanceContract:
    """Machine-evaluable definition of done for one unit.

    `expected_exit` stays 0 so the done-gate and the mechanical drift sensor
    agree: any other exit is red. `not_a_check` records signals that must not
    authorize completion.
    """

    check_cmd: str
    expected_exit: int = 0
    green_rules: list[str] = field(default_factory=list)
    not_a_check: list[str] = field(default_factory=list)
    unit_id: str = "session"

    def __post_init__(self) -> None:
        self.check_cmd = str(self.check_cmd).strip()
        if not self.check_cmd:
            raise ValueError("acceptance.check_cmd is required")
        self.expected_exit = int(self.expected_exit)
        if self.expected_exit != 0:
            raise ValueError("acceptance.expected_exit must be 0")
        self.green_rules = [str(item) for item in self.green_rules]
        self.not_a_check = [str(item) for item in self.not_a_check]
        self.unit_id = str(self.unit_id).strip() or "session"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceContract:
        return cls(
            check_cmd=str(data["check_cmd"]),
            expected_exit=int(data.get("expected_exit") or 0),
            green_rules=[str(item) for item in data.get("green_rules") or []],
            not_a_check=[str(item) for item in data.get("not_a_check") or []],
            unit_id=str(data.get("unit_id") or "session"),
        )


@dataclass
class GoalSpec:
    """Original mission. `goal` is copied verbatim into pins, anchors, and digests."""

    goal: str
    constraints: list[str] = field(default_factory=list)
    done_means: str = ""
    check_cmd: str | None = None
    allow_paths: list[str] = field(default_factory=list)
    acceptance: AcceptanceContract | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalSpec:
        raw = data.get("acceptance")
        acceptance = AcceptanceContract.from_dict(raw) if raw else None
        return cls(
            goal=str(data["goal"]),
            constraints=[str(item) for item in data.get("constraints") or []],
            done_means=str(data.get("done_means") or ""),
            check_cmd=data.get("check_cmd"),
            allow_paths=[str(item) for item in data.get("allow_paths") or []],
            acceptance=acceptance,
        )


@dataclass
class GuardConfig:
    compact_every: int = 20
    anchor_every: int = 5
    fail_streak_limit: int = 3
    token_ceiling: int = 8000
    keep_recent: int = 8
    mention_gap: int = 12
    tool_char_limit: int = 1200
    side_quest_ratio: float = 0.6
    block_done_on_red: bool = True
    intent_ring_limit: int = 24
    # None keeps today's behavior: red checks block done but never stop the session.
    max_check_attempts: int | None = None
    no_progress_window: int | None = None

    def __post_init__(self) -> None:
        self.compact_every = max(2, int(self.compact_every))
        self.anchor_every = max(1, int(self.anchor_every))
        self.fail_streak_limit = max(1, int(self.fail_streak_limit))
        self.token_ceiling = max(1, int(self.token_ceiling))
        self.keep_recent = max(1, int(self.keep_recent))
        if self.keep_recent >= self.compact_every:
            self.keep_recent = self.compact_every - 1
        self.mention_gap = max(1, int(self.mention_gap))
        self.tool_char_limit = max(80, int(self.tool_char_limit))
        self.side_quest_ratio = float(self.side_quest_ratio)
        self.intent_ring_limit = max(self.mention_gap, int(self.intent_ring_limit))
        self.max_check_attempts = _optional_limit(self.max_check_attempts, minimum=1)
        self.no_progress_window = _optional_limit(self.no_progress_window, minimum=2)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuardConfig:
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass
class Turn:
    role: str
    content: str
    index: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Turn:
        return cls(role=str(data["role"]), content=str(data.get("content") or ""), index=int(data["index"]))


@dataclass
class CheckResult:
    exit_code: int
    output: str
    at_turn: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckResult:
        return cls(
            exit_code=int(data["exit_code"]),
            output=str(data.get("output") or ""),
            at_turn=int(data.get("at_turn") or 0),
        )


@dataclass
class SessionDigest:
    goal: str
    constraints: list[str]
    done_so_far: list[str]
    open_items: list[str]
    last_verify: dict[str, Any] | None
    risks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionDigest:
        return cls(
            goal=str(data["goal"]),
            constraints=[str(item) for item in data.get("constraints") or []],
            done_so_far=[str(item) for item in data.get("done_so_far") or []],
            open_items=[str(item) for item in data.get("open_items") or []],
            last_verify=data.get("last_verify"),
            risks=[str(item) for item in data.get("risks") or []],
        )


@dataclass
class DriftReport:
    drift: bool
    reasons: list[str]
    fail_streak: int
    block_done: bool
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DoneVerdict:
    """Typed result of a done-gate or session exit. `to_legacy` keeps old CLI keys."""

    status: str
    reason: str
    drift: bool = False
    reasons: list[str] = field(default_factory=list)
    fail_streak: int = 0
    exit_code: int | None = None
    failed_rule: str = ""
    evidence: str = ""
    attempt: int = 0
    next_route: str = ""
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_legacy(self) -> dict[str, Any]:
        """Shape `attempt_done()` has always returned, plus exit reasons when set."""
        if self.reason == "no_verify":
            return {"status": "blocked", "reason": "no_verify", "drift": False}
        if self.reason == "drift":
            return {
                "status": "blocked",
                "reason": "drift",
                "reasons": list(self.reasons),
                "drift": True,
                "fail_streak": self.fail_streak,
            }
        if self.reason == "verify_red":
            return {
                "status": "blocked",
                "reason": "verify_red",
                "exit_code": self.exit_code,
                "drift": False,
            }
        if self.status == "done":
            payload: dict[str, Any] = {
                "status": "done",
                "drift": False,
                "exit_code": self.exit_code,
            }
            if self.warning:
                payload["warning"] = self.warning
            return payload
        payload = {
            "status": "blocked",
            "reason": self.reason,
            "drift": self.drift,
            "failed_rule": self.failed_rule,
            "evidence": self.evidence,
            "attempt": self.attempt,
            "next_route": self.next_route,
        }
        if self.reasons:
            payload["reasons"] = list(self.reasons)
        if self.exit_code is not None:
            payload["exit_code"] = self.exit_code
        if self.fail_streak:
            payload["fail_streak"] = self.fail_streak
        return payload


@dataclass
class CorrectionPacket:
    """One failed unit handed back to the producer. This package has a single unit."""

    unit_id: str
    status: str
    failed_rule: str
    evidence: str
    allowed_scope: list[str]
    attempt: int
    next_route: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
