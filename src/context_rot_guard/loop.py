"""Repeatable loop protocol for one unit: verdict, correction packet, feature pack.

The library still does not run an agent. A caller produces a change, runs the
acceptance command, and records the exit code. This module names what comes
back when that check is red, and writes the files a new feature starts from.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Sequence

from context_rot_guard.models import (
    AcceptanceContract,
    CheckResult,
    CorrectionPacket,
    DoneVerdict,
    DriftReport,
    GoalSpec,
    GuardConfig,
)

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

DEFAULT_NOT_A_CHECK = (
    "The model says done",
    "The diff looks reasonable",
    "No exception was raised",
)

UNSET_SCOPE = "(unset — edit only files named by the goal)"


def trailing_red(checks: Sequence[CheckResult]) -> list[CheckResult]:
    reds: list[CheckResult] = []
    for check in reversed(checks):
        if check.exit_code == 0:
            break
        reds.append(check)
    reds.reverse()
    return reds


def _no_progress(checks: Sequence[CheckResult], window: int | None) -> bool:
    if window is None:
        return False
    reds = trailing_red(checks)
    if len(reds) < window:
        return False
    recent = [check.output for check in reds[-window:]]
    return len(set(recent)) == 1


def _evidence(checks: Sequence[CheckResult], report: DriftReport) -> str:
    if checks:
        tail = checks[-1].output.strip()
        if tail:
            return tail
    if report.reasons:
        return ", ".join(report.reasons)
    return ""


def build_verdict(
    spec: GoalSpec,
    config: GuardConfig,
    checks: Sequence[CheckResult],
    report: DriftReport,
) -> DoneVerdict:
    """Decide pass, keep-correcting, or stop. Defaults match pre-protocol sessions."""
    last = checks[-1] if checks else None
    attempt = len(trailing_red(checks))
    evidence = _evidence(checks, report)
    base = dict(
        drift=report.drift,
        reasons=list(report.reasons),
        fail_streak=report.fail_streak,
        exit_code=None if last is None else last.exit_code,
        evidence=evidence,
        attempt=attempt,
    )

    capped = (
        config.max_check_attempts is not None
        and last is not None
        and last.exit_code != 0
        and attempt >= config.max_check_attempts
    )
    if capped:
        return DoneVerdict(
            status="blocked",
            reason="attempt_cap",
            failed_rule="attempt_cap",
            next_route="escalate",
            **base,
        )
    if last is not None and last.exit_code != 0 and _no_progress(checks, config.no_progress_window):
        return DoneVerdict(
            status="blocked",
            reason="no_progress",
            failed_rule="no_progress",
            next_route="escalate",
            **base,
        )
    if report.drift:
        return DoneVerdict(
            status="blocked",
            reason="drift",
            failed_rule=report.reasons[0] if report.reasons else "drift",
            next_route="correct",
            **base,
        )
    if last is None:
        return DoneVerdict(
            status="blocked",
            reason="no_verify",
            failed_rule="no_verify",
            next_route="check",
            drift=False,
            attempt=0,
        )
    if last.exit_code != 0 and config.block_done_on_red:
        return DoneVerdict(
            status="blocked",
            reason="verify_red",
            failed_rule="verify_red",
            next_route="correct",
            **base,
        )
    warning = ""
    if last.exit_code != 0:
        warning = "verify_red"
    return DoneVerdict(
        status="done",
        reason="pass",
        failed_rule="",
        next_route="pass",
        warning=warning,
        drift=False,
        exit_code=last.exit_code,
        attempt=0,
    )


def build_packet(spec: GoalSpec, verdict: DoneVerdict) -> CorrectionPacket | None:
    """Return the failed unit only. A passing or not-yet-checked session has no packet."""
    if verdict.status == "done" or verdict.reason == "no_verify":
        return None
    if spec.acceptance is not None:
        unit_id = spec.acceptance.unit_id
    else:
        unit_id = "session"
    scope = list(spec.allow_paths) or [UNSET_SCOPE]
    return CorrectionPacket(
        unit_id=unit_id,
        status=verdict.status,
        failed_rule=verdict.failed_rule or verdict.reason,
        evidence=verdict.evidence,
        allowed_scope=scope,
        attempt=verdict.attempt,
        next_route=verdict.next_route,
    )


def render_correction(packet: CorrectionPacket) -> str:
    scope = "\n".join("- %s" % item for item in packet.allowed_scope)
    if packet.next_route == "escalate":
        action = "Stop correcting this unit. Hand the packet back for a replan or a human."
    else:
        action = "Fix this unit only, inside the allowed scope, then re-run the check."
    return (
        "[CORRECTION — this unit only]\n"
        "unit: {unit}\n"
        "failed_rule: {rule}\n"
        "attempt: {attempt}\n"
        "next_route: {route}\n"
        "evidence: {evidence}\n"
        "allowed_scope:\n{scope}\n"
        "{action}\n"
    ).format(
        unit=packet.unit_id,
        rule=packet.failed_rule,
        attempt=packet.attempt,
        route=packet.next_route,
        evidence=packet.evidence or "(none)",
        scope=scope,
        action=action,
    )


def contract_for_check(check_cmd: str, *, unit_id: str = "session") -> AcceptanceContract:
    command = check_cmd.strip()
    return AcceptanceContract(
        check_cmd=command,
        expected_exit=0,
        green_rules=["%s exits 0" % command],
        not_a_check=list(DEFAULT_NOT_A_CHECK),
        unit_id=unit_id,
    )


def validate_slug(slug: str) -> str:
    text = slug.strip()
    if not SLUG_RE.match(text):
        raise ValueError("feature slug must be lowercase words separated by hyphens")
    return text


def write_feature_pack(
    dest: Path,
    *,
    slug: str,
    goal: str,
    done_means: str,
    check_cmd: str,
    constraints: Sequence[str] | None = None,
    allow_paths: Sequence[str] | None = None,
    max_check_attempts: int = 3,
    no_progress_window: int = 2,
    force: bool = False,
) -> Path:
    """Write the acceptance file and brief a new feature starts from.

    `dest` is the feature directory (usually `.context-rot-guard/features/<slug>`).
    """
    slug = validate_slug(slug)
    folder = Path(dest)
    if folder.exists() and any(folder.iterdir()) and not force:
        raise FileExistsError("feature pack already exists at %s" % folder)
    folder.mkdir(parents=True, exist_ok=True)
    constraint_list = [str(item) for item in (constraints or [])]
    paths = [str(item) for item in (allow_paths or [])]
    contract = contract_for_check(check_cmd, unit_id=slug)
    acceptance = {
        "slug": slug,
        "goal": goal,
        "done_means": done_means,
        "constraints": constraint_list,
        "allow_paths": paths,
        "acceptance": contract.to_dict(),
        "exits": {
            "pass": "acceptance.check_cmd exits 0",
            "attempt_cap": max_check_attempts,
            "no_progress_window": no_progress_window,
            "error_threshold": "fail_streak verify_stall inside the session",
            "human_interrupt": "revise the goal or stop the agent",
            "external_event": "objective met elsewhere — delete or archive this pack",
            "cost_budget": "enforced by the harness budget, not this file",
            "deadline": "enforced by the harness wall clock, not this file",
        },
    }
    (folder / "acceptance.json").write_text(
        json.dumps(acceptance, indent=2) + "\n",
        encoding="utf-8",
    )
    (folder / "BRIEF.md").write_text(
        _brief(
            slug=slug,
            goal=goal,
            done_means=done_means,
            check_cmd=check_cmd.strip(),
            constraints=constraint_list,
            allow_paths=paths,
            max_check_attempts=max_check_attempts,
            no_progress_window=no_progress_window,
        ),
        encoding="utf-8",
    )
    return folder


def _shell_quote(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _brief(
    *,
    slug: str,
    goal: str,
    done_means: str,
    check_cmd: str,
    constraints: list[str],
    allow_paths: list[str],
    max_check_attempts: int,
    no_progress_window: int,
) -> str:
    constraint_lines = "\n".join("- %s" % item for item in constraints) or "- (none)"
    path_lines = "\n".join("- `%s`" % item for item in allow_paths) or "- (name them before editing)"
    init = (
        "context-rot-guard init --goal %s --done-means %s --check-cmd %s "
        "--max-check-attempts %d --no-progress-window %d"
        % (
            _shell_quote(goal),
            _shell_quote(done_means),
            _shell_quote(check_cmd),
            max_check_attempts,
            no_progress_window,
        )
    )
    for path in allow_paths:
        init += " --allow-path %s" % _shell_quote(path)
    for item in constraints:
        init += " --constraint %s" % _shell_quote(item)
    return (
        "# %s\n\n"
        "One unit. Do not start a second feature until this check is green or an exit fires.\n\n"
        "## Goal\n\n%s\n\n"
        "## Done means\n\n%s\n\n"
        "Check (this is the oracle):\n\n```bash\n%s\n```\n\n"
        "Not a check: the model says done, the diff looks reasonable, no exception was raised.\n\n"
        "## Scope\n\n%s\n\n"
        "## Constraints\n\n%s\n\n"
        "## Loop\n\n"
        "1. Produce a change inside the scope.\n"
        "2. Run the check. Record the exit code if a session is open.\n"
        "3. On red, correct this unit only. Do not regenerate unrelated work.\n"
        "4. Stop after %d red checks (`attempt_cap`) or %d identical red outputs (`no_progress`).\n"
        "   Escalate — do not polish the same failure.\n\n"
        "## Session\n\n```bash\n%s\n```\n"
        % (
            slug,
            goal,
            done_means,
            check_cmd,
            path_lines,
            constraint_lines,
            max_check_attempts,
            no_progress_window,
            init,
        )
    )
