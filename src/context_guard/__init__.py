"""context-guard: compress, re-anchor, and detect drift in long agent sessions."""

from __future__ import annotations

from context_guard.drift import EmbeddingDriftDetector, MechanicalDriftDetector
from context_guard.guard import ContextRotGuard
from context_guard.models import (
    CheckResult,
    DriftReport,
    GoalSpec,
    GuardConfig,
    SessionDigest,
    Turn,
)

__version__ = "0.1.0"

__all__ = [
    "CheckResult",
    "ContextRotGuard",
    "DriftReport",
    "EmbeddingDriftDetector",
    "GoalSpec",
    "GuardConfig",
    "MechanicalDriftDetector",
    "SessionDigest",
    "Turn",
    "__version__",
]
