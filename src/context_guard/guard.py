"""Orchestrate compression, anchors, and mechanical drift."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from context_guard.anchor import anchor_due, render_anchor, render_pin
from context_guard.compress import build_digest, estimate_tokens, render_digest, truncate_text
from context_guard.drift import evaluate_mechanical, render_drift_note
from context_guard.models import (
    CheckResult,
    DriftReport,
    GoalSpec,
    GuardConfig,
    SessionDigest,
    Turn,
)

ROLES = {"user", "assistant", "tool", "system"}
Summarizer = Callable[[SessionDigest], SessionDigest]
EVENT_LIMIT = 200


class ContextRotGuard:
    """Message middleware. `process()` returns the list to send to the model.

    Persistence is optional. Pass `session_path` (the CLI does) to write
    `.context-guard/session.json`. Omit it in tests and library calls
    that should stay in memory.
    """

    def __init__(
        self,
        spec: GoalSpec,
        *,
        compact_every: int = 20,
        anchor_every: int = 5,
        fail_streak: int = 3,
        token_ceiling: int = 8000,
        keep_recent: int = 8,
        mention_gap: int = 12,
        session_path: Path | None = None,
        config: GuardConfig | None = None,
        summarizer: Summarizer | None = None,
    ) -> None:
        self.spec = spec
        if config is None:
            config = GuardConfig(
                compact_every=compact_every,
                anchor_every=anchor_every,
                fail_streak_limit=fail_streak,
                token_ceiling=token_ceiling,
                keep_recent=keep_recent,
                mention_gap=mention_gap,
            )
        self.config = config
        self.session_path = Path(session_path) if session_path is not None else None
        self.summarizer = summarizer
        self.turns: list[Turn] = []
        self.intent_ring: list[Turn] = []
        self.checks: list[CheckResult] = []
        self.digest: SessionDigest | None = None
        self.turn_count = 0
        self.events: list[dict[str, Any]] = []
        self.pulse_count = 0
        self._last_drift_key: tuple[bool, tuple[str, ...]] = (False, ())

    def add_turn(self, role: str, content: str) -> None:
        if role not in ROLES:
            raise ValueError("role must be one of %s" % ", ".join(sorted(ROLES)))
        text = content if isinstance(content, str) else str(content)
        if role == "tool":
            text = truncate_text(text, self.config.tool_char_limit)
        self.turn_count += 1
        turn = Turn(role=role, content=text, index=self.turn_count)
        self.turns.append(turn)
        snippet = text if len(text) <= 500 else text[:500]
        self.intent_ring.append(Turn(role=role, content=snippet, index=self.turn_count))
        overflow = len(self.intent_ring) - self.config.intent_ring_limit
        if overflow > 0:
            self.intent_ring = self.intent_ring[overflow:]
        self._save()

    def record_check(self, exit_code: int, output: str = "") -> DriftReport:
        text = output if isinstance(output, str) else str(output)
        if len(text) > 500:
            text = text[-500:]
        self.checks.append(
            CheckResult(exit_code=int(exit_code), output=text, at_turn=self.turn_count)
        )
        report = self.evaluate()
        self._note_drift(report)
        self._save()
        return report

    def revise(
        self,
        *,
        goal: str | None = None,
        constraints: list[str] | None = None,
        done_means: str | None = None,
        check_cmd: str | None = None,
        allow_paths: list[str] | None = None,
    ) -> None:
        """Replace the mission and reset drift counters. Raw turns stay."""
        if goal is not None:
            self.spec.goal = goal
        if constraints is not None:
            self.spec.constraints = list(constraints)
        if done_means is not None:
            self.spec.done_means = done_means
        if check_cmd is not None:
            self.spec.check_cmd = check_cmd
        if allow_paths is not None:
            self.spec.allow_paths = list(allow_paths)
        self.digest = None
        self.checks.clear()
        self.intent_ring.clear()
        self._last_drift_key = (False, ())
        self._save()

    def evaluate(self) -> DriftReport:
        return evaluate_mechanical(
            self.spec,
            self.intent_ring,
            self.checks,
            fail_streak_limit=self.config.fail_streak_limit,
            mention_gap=self.config.mention_gap,
            side_quest_ratio=self.config.side_quest_ratio,
            block_done_on_red=self.config.block_done_on_red,
        )

    def maybe_compact(self, *, force: bool = False, drift_reasons: list[str] | None = None) -> bool:
        if not self.config.enable_compact:
            return False
        if len(self.turns) <= self.config.keep_recent:
            return False
        window = "\n".join(turn.content for turn in self.turns)
        over_budget = (
            len(self.turns) >= self.config.compact_every
            or estimate_tokens(window) > self.config.token_ceiling
        )
        if not force and not over_budget:
            return False
        drop_count = len(self.turns) - self.config.keep_recent
        dropped = self.turns[:drop_count]
        self.turns = self.turns[drop_count:]
        risks: list[str] = []
        if self.digest is not None:
            risks.extend(
                note for note in self.digest.risks if not note.startswith("Compacted ")
            )
        risks.append("Compacted %d earlier turns into this digest." % drop_count)
        for reason in drift_reasons or []:
            note = "drift:%s" % reason
            if note not in risks:
                risks.append(note)
        self.digest = build_digest(
            self.spec,
            dropped,
            self.checks,
            risks,
            prior=self.digest,
        )
        if self.summarizer is not None:
            updated = self.summarizer(self.digest)
            updated.goal = self.spec.goal
            updated.constraints = list(self.spec.constraints)
            self.digest = updated
        self._emit(
            "compact",
            reasons=list(drift_reasons or []),
            detail={"dropped": drop_count, "kept": len(self.turns)},
        )
        return True

    def process(self, *, before_completion: bool = False) -> list[dict[str, Any]]:
        """Apply L1 + L2 and attach an L3 note when drift or a red check blocks done."""
        pre = self.evaluate()
        self.maybe_compact(
            force=pre.drift,
            drift_reasons=pre.reasons if pre.drift else None,
        )
        report = self.evaluate()
        self._note_drift(report)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._pin_text(), "meta": {"kind": "pin"}}
        ]
        for turn in self.turns:
            messages.append(
                {
                    "role": turn.role,
                    "content": turn.content,
                    "meta": {"kind": "turn", "index": turn.index},
                }
            )
        if anchor_due(
            self.turn_count,
            self.config.anchor_every,
            drift=report.drift,
            before_completion=before_completion,
        ):
            messages.append(
                {
                    "role": "system",
                    "content": render_anchor(self.spec),
                    "meta": {"kind": "anchor"},
                }
            )
            self._emit(
                "anchor",
                reasons=list(report.reasons),
                detail={"before_completion": before_completion, "drift": report.drift},
            )
        if report.drift or report.block_done:
            messages.append(
                {
                    "role": "system",
                    "content": render_drift_note(report),
                    "meta": {"kind": "drift"},
                }
            )
        self._save()
        return messages

    def attempt_done(self) -> dict[str, Any]:
        """Refuse `status=done` on drift, on a red check, or with no check at all."""
        report = self.evaluate()
        last = self.checks[-1] if self.checks else None
        if report.drift:
            payload: dict[str, Any] = {
                "status": "blocked",
                "reason": "drift",
                "reasons": list(report.reasons),
                "drift": True,
                "fail_streak": report.fail_streak,
            }
            self._emit("blocked_done", reasons=list(report.reasons), detail={"reason": "drift"})
            self._save()
            return payload
        if last is None:
            payload = {"status": "blocked", "reason": "no_verify", "drift": False}
            self._emit("blocked_done", reasons=[], detail={"reason": "no_verify"})
            self._save()
            return payload
        if last.exit_code != 0 and self.config.block_done_on_red:
            payload = {
                "status": "blocked",
                "reason": "verify_red",
                "exit_code": last.exit_code,
                "drift": False,
            }
            self._emit(
                "blocked_done",
                reasons=[],
                detail={"reason": "verify_red", "exit_code": last.exit_code},
            )
            self._save()
            return payload
        payload = {
            "status": "done",
            "drift": False,
            "exit_code": last.exit_code,
        }
        if last.exit_code != 0:
            payload["warning"] = "verify_red"
        self._emit("done", reasons=[], detail={"exit_code": last.exit_code})
        self._save()
        return payload

    def quality_check(self) -> dict[str, Any]:
        """Score drift, refresh the model window, and preview whether done would pass.

        Does not mark the session done. Agents should run this before claiming done.
        """
        report = self.evaluate()
        messages = self.process()
        preview = self._done_preview()
        payload = {
            "drift": report.drift,
            "reasons": list(report.reasons),
            "fail_streak": report.fail_streak,
            "block_done": report.block_done,
            "done_preview": preview,
            "events_tail": list(self.events[-10:]),
            "message_count": len(messages),
            "enable_compact": self.config.enable_compact,
        }
        self._emit(
            "quality_check",
            reasons=list(report.reasons),
            detail={"done_preview": preview.get("status"), "drift": report.drift},
        )
        self._save()
        # Re-read tail after emit so callers see the quality_check event.
        payload["events_tail"] = list(self.events[-10:])
        return payload

    def pulse(self, *, snippet: str = "", record_only: bool = False) -> dict[str, Any]:
        """Lightweight background tick for hooks: score drift, realign if needed, short note.

        Normal pulse: increments `pulse_count`, speaks every `pulse_every` ticks and on drift.
        `record_only`: ingest a message into the sidecar (e.g. afterAgentResponse) without
        advancing the speak cadence; still realigns when drift is true.
        """
        text = (snippet or "").strip()
        if text:
            # Keep pulse ingest tiny so hooks stay cheap.
            if len(text) > 400:
                text = text[:400]
            self.add_turn("assistant", text)
        if not record_only:
            self.pulse_count += 1
        report = self.evaluate()
        actions: list[str] = []
        if report.drift:
            before = len(self.events)
            self.process()
            for event in self.events[before:]:
                action = str(event.get("action") or "")
                if action and action not in actions:
                    actions.append(action)
            note = self._drift_note(report, actions)
            should_speak = True
        else:
            note = "no drift detected"
            if record_only:
                should_speak = False
            else:
                should_speak = self.pulse_count % self.config.pulse_every == 0
        self._emit(
            "pulse",
            reasons=list(report.reasons),
            detail={
                "note": note,
                "should_speak": should_speak,
                "pulse_count": self.pulse_count,
                "record_only": record_only,
            },
        )
        self._save()
        return {
            "note": note,
            "drift": report.drift,
            "reasons": list(report.reasons),
            "should_speak": should_speak,
            "pulse_count": self.pulse_count,
            "actions": actions,
            "enable_compact": self.config.enable_compact,
            "record_only": record_only,
        }

    @staticmethod
    def _drift_note(report: DriftReport, actions: list[str]) -> str:
        reasons = ", ".join(report.reasons) or "unknown"
        helped: list[str] = []
        if "anchor" in actions:
            helped.append("re-anchored the goal")
        if "compact" in actions:
            helped.append("compacted noise")
        if "drift" in actions or report.drift:
            helped.append("flagged drift")
        if not helped:
            helped.append("flagged drift")
        return "drift detected (%s) — I %s" % (reasons, "; ".join(helped))

    def status(self) -> dict[str, Any]:
        report = self.evaluate()
        last = self.checks[-1].to_dict() if self.checks else None
        return {
            "goal": self.spec.goal,
            "turns_retained": len(self.turns),
            "turn_count": self.turn_count,
            "compacted": self.digest is not None,
            "enable_compact": self.config.enable_compact,
            "drift": report.drift,
            "reasons": list(report.reasons),
            "fail_streak": report.fail_streak,
            "block_done": report.block_done,
            "last_check": last,
            "signals": report.signals,
            "event_count": len(self.events),
            "pulse_count": self.pulse_count,
        }

    def _done_preview(self) -> dict[str, Any]:
        """Same decision as `attempt_done()` without emitting done/blocked events."""
        report = self.evaluate()
        last = self.checks[-1] if self.checks else None
        if report.drift:
            return {
                "status": "blocked",
                "reason": "drift",
                "reasons": list(report.reasons),
                "drift": True,
                "fail_streak": report.fail_streak,
            }
        if last is None:
            return {"status": "blocked", "reason": "no_verify", "drift": False}
        if last.exit_code != 0 and self.config.block_done_on_red:
            return {
                "status": "blocked",
                "reason": "verify_red",
                "exit_code": last.exit_code,
                "drift": False,
            }
        payload: dict[str, Any] = {
            "status": "done",
            "drift": False,
            "exit_code": last.exit_code,
        }
        if last.exit_code != 0:
            payload["warning"] = "verify_red"
        return payload

    def _note_drift(self, report: DriftReport) -> None:
        key = (bool(report.drift), tuple(report.reasons))
        if key == self._last_drift_key:
            return
        previous_drift, _ = self._last_drift_key
        self._last_drift_key = key
        if report.drift or (previous_drift and not report.drift):
            self._emit(
                "drift",
                reasons=list(report.reasons),
                detail={"drift": report.drift, "fail_streak": report.fail_streak},
            )

    def _emit(
        self,
        action: str,
        *,
        reasons: list[str] | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": action,
            "turn": self.turn_count,
            "reasons": list(reasons or []),
            "detail": detail or {},
        }
        self.events.append(event)
        overflow = len(self.events) - EVENT_LIMIT
        if overflow > 0:
            self.events = self.events[overflow:]

    def _pin_text(self) -> str:
        if self.digest is not None:
            return render_digest(self.digest)
        return render_pin(self.spec)

    def _save(self) -> None:
        if self.session_path is None:
            return
        payload = {
            "version": 1,
            "spec": self.spec.to_dict(),
            "config": self.config.to_dict(),
            "turns": [turn.to_dict() for turn in self.turns],
            "intent_ring": [turn.to_dict() for turn in self.intent_ring],
            "turn_count": self.turn_count,
            "digest": self.digest.to_dict() if self.digest is not None else None,
            "checks": [check.to_dict() for check in self.checks],
            "events": list(self.events),
            "pulse_count": self.pulse_count,
            "last_drift_key": [self._last_drift_key[0], list(self._last_drift_key[1])],
        }
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.session_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.session_path)

    @classmethod
    def load(cls, path: Path, *, summarizer: Summarizer | None = None) -> ContextRotGuard:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        guard = cls(
            GoalSpec.from_dict(data["spec"]),
            config=GuardConfig.from_dict(data["config"]),
            session_path=Path(path),
            summarizer=summarizer,
        )
        guard.turns = [Turn.from_dict(item) for item in data.get("turns") or []]
        guard.intent_ring = [Turn.from_dict(item) for item in data.get("intent_ring") or []]
        guard.turn_count = int(data.get("turn_count") or 0)
        digest = data.get("digest")
        guard.digest = SessionDigest.from_dict(digest) if digest else None
        guard.checks = [CheckResult.from_dict(item) for item in data.get("checks") or []]
        guard.events = [dict(item) for item in data.get("events") or []]
        guard.pulse_count = int(data.get("pulse_count") or 0)
        raw_key = data.get("last_drift_key")
        if isinstance(raw_key, list) and len(raw_key) == 2:
            guard._last_drift_key = (
                bool(raw_key[0]),
                tuple(str(item) for item in (raw_key[1] or [])),
            )
        return guard
