"""Shared records for a guarded session."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


@dataclass
class GoalSpec:
    """Original mission. `goal` is copied verbatim into pins, anchors, and digests."""

    goal: str
    constraints: list[str] = field(default_factory=list)
    done_means: str = ""
    check_cmd: str | None = None
    allow_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalSpec:
        return cls(
            goal=str(data["goal"]),
            constraints=[str(item) for item in data.get("constraints") or []],
            done_means=str(data.get("done_means") or ""),
            check_cmd=data.get("check_cmd"),
            allow_paths=[str(item) for item in data.get("allow_paths") or []],
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
    enable_compact: bool = True
    # Speak a short pulse note every N pulses (hooks), and always on drift.
    pulse_every: int = 3

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
        self.enable_compact = bool(self.enable_compact)
        self.pulse_every = max(1, int(self.pulse_every))

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
