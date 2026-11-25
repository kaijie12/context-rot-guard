"""context-rot-guard: compress, re-anchor, and detect drift in long agent sessions."""

from __future__ import annotations

from context_rot_guard.drift import EmbeddingDriftDetector, MechanicalDriftDetector
from context_rot_guard.guard import ContextRotGuard
from context_rot_guard.models import (
    AcceptanceContract,
    CheckResult,
    CorrectionPacket,
    DoneVerdict,
    DriftReport,
    GoalSpec,
    GuardConfig,
    SessionDigest,
    Turn,
)

__version__ = "0.1.0"

__all__ = [
    "AcceptanceContract",
    "CheckResult",
    "ContextRotGuard",
    "CorrectionPacket",
    "DoneVerdict",
    "DriftReport",
    "EmbeddingDriftDetector",
    "GoalSpec",
    "GuardConfig",
    "MechanicalDriftDetector",
    "SessionDigest",
    "Turn",
    "__version__",
]
