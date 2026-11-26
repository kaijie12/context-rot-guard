"""Thin CLI over ContextRotGuard. Session file: .context-guard/session.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from context_guard.cycle import ChatCycle, chat_path, handle_hook, prompts_from_transcript
from context_guard.guard import ContextRotGuard
from context_guard.models import GoalSpec, GuardConfig


def default_session_path() -> Path:
    return Path.cwd() / ".context-guard" / "session.json"


def _path(args: argparse.Namespace) -> Path:
    if args.session is not None:
        return Path(args.session)
    return default_session_path()


def _print_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _load(path: Path) -> ContextRotGuard:
    if not path.is_file():
        print("No session at %s. Run `context-guard init` first." % path, file=sys.stderr)
        raise SystemExit(2)
    return ContextRotGuard.load(path)


def _cmd_init(args: argparse.Namespace) -> int:
    path = _path(args)
    if path.exists() and not args.force:
        print("Session already exists at %s. Pass --force to replace it." % path, file=sys.stderr)
        return 2
    spec = GoalSpec(
        goal=args.goal,
        constraints=list(args.constraint or []),
        done_means=args.done_means,
        check_cmd=args.check_cmd,
        allow_paths=list(args.allow_path or []),
    )
    config = GuardConfig(
        compact_every=args.compact_every,
        anchor_every=args.anchor_every,
        fail_streak_limit=args.fail_streak,
        token_ceiling=args.token_ceiling,
        mention_gap=args.mention_gap,
        block_done_on_red=not args.allow_done_on_red,
        enable_compact=not args.no_compact,
    )
    guard = ContextRotGuard(spec, config=config, session_path=path)
    guard._save()
    _print_json(
        {
            "status": "initialized",
            "session": str(path),
            "goal": spec.goal,
            "enable_compact": config.enable_compact,
        }
    )
    return 0


def _cmd_turn(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    guard.add_turn(args.role, args.content)
    _print_json({"status": "ok", "turn_count": guard.turn_count, "role": args.role})
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    report = guard.record_check(args.exit_code, args.log or "")
    _print_json(report.to_dict())
    return 0


def _cmd_messages(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    messages = guard.process(before_completion=args.before_done)
    if args.json:
        _print_json(messages)
        return 0
    for message in messages:
        kind = message.get("meta", {}).get("kind", message["role"])
        sys.stdout.write("--- %s (%s) ---\n" % (kind, message["role"]))
        sys.stdout.write(message["content"])
        if not message["content"].endswith("\n"):
            sys.stdout.write("\n")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    _print_json(guard.status())
    return 0


def _cmd_quality_check(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    payload = guard.quality_check()
    _print_json(payload)
    preview = payload.get("done_preview") or {}
    return 0 if preview.get("status") == "done" else 2


def _cmd_log(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    events = list(guard.events)
    if args.tail is not None:
        events = events[-max(0, int(args.tail)) :]
    _print_json(events)
    return 0


def _session_usable(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not text:
        return False
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def _ensure_session(path: Path, args: argparse.Namespace) -> ContextRotGuard:
    # mktemp creates an empty file; treat empty/invalid JSON as "missing".
    if _session_usable(path):
        return ContextRotGuard.load(path)
    goal = (args.goal or "").strip() or "Stay on the mission recorded for this workspace"
    done_means = (args.done_means or "").strip() or "checks stay green; do not claim done while red"
    config = GuardConfig(
        enable_compact=bool(getattr(args, "compact", False)),
        pulse_every=args.pulse_every,
        fail_streak_limit=args.fail_streak,
        mention_gap=args.mention_gap,
    )
    guard = ContextRotGuard(
        GoalSpec(goal=goal, done_means=done_means, check_cmd=args.check_cmd),
        config=config,
        session_path=path,
    )
    guard._save()
    return guard


def _cmd_pulse(args: argparse.Namespace) -> int:
    path = _path(args)
    if args.ensure:
        guard = _ensure_session(path, args)
    else:
        guard = _load(path)
    if args.bootstrap_only:
        _print_json(
            {
                "status": "ready",
                "session": str(path),
                "goal": guard.spec.goal,
                "pulse_count": guard.pulse_count,
                "enable_compact": guard.config.enable_compact,
            }
        )
        return 0
    snippet = args.snippet or ""
    if args.snippet_file:
        snippet = Path(args.snippet_file).read_text(encoding="utf-8")
    payload = guard.pulse(snippet=snippet, record_only=bool(args.record_only))
    if args.plain:
        sys.stdout.write(str(payload.get("note") or "") + "\n")
    else:
        _print_json(payload)
    return 2 if payload.get("drift") else 0


def _cmd_done(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    messages = guard.process(before_completion=True)
    result = guard.attempt_done()
    result["anchor_injected"] = any(
        message.get("meta", {}).get("kind") == "anchor" for message in messages
    )
    _print_json(result)
    return 0 if result["status"] == "done" else 2


def _conversation(args: argparse.Namespace) -> str:
    return str(args.conversation or "default")


def _cycle_path(args: argparse.Namespace) -> Path:
    root = Path(args.root) if getattr(args, "root", None) else Path.cwd()
    if args.session is not None:
        return Path(args.session)
    return chat_path(root, _conversation(args))


def _load_cycle(args: argparse.Namespace) -> tuple[ChatCycle, Path]:
    path = _cycle_path(args)
    return ChatCycle.load(path, _conversation(args)), path


def _cmd_unit_start(args: argparse.Namespace) -> int:
    cycle, path = _load_cycle(args)
    if args.mission:
        cycle.observe_user(args.mission if args.mission.lower().startswith("mission:") else "Mission: %s" % args.mission)
    cycle.start_goal(
        args.goal,
        args.done_means or "",
        amended=bool(cycle.goal),
        check=args.check or "",
    )
    cycle.save(path)
    _print_json(
        {
            "status": "goal",
            "session": str(path),
            "phase": cycle.phase,
            "mission": cycle.mission,
            "goal": cycle.goal,
            "pin": cycle.pin(),
        }
    )
    return 0


def _cmd_goal_show(args: argparse.Namespace) -> int:
    cycle, _path = _load_cycle(args)
    sys.stdout.write(cycle.show())
    if not cycle.show().endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _cmd_goal_recover(args: argparse.Namespace) -> int:
    cycle, path = _load_cycle(args)
    if getattr(args, "transcript", None):
        extra = prompts_from_transcript(args.transcript)
        if extra:
            # Prefer transcript when the sidecar is empty or thin.
            if len(cycle.prompts) < len(extra):
                cycle.prompts = list(extra)
            else:
                for line in extra:
                    if line not in cycle.prompts:
                        cycle.prompts.append(line)
    cycle.recover_from_prompts()
    cycle.save(path)
    shown = cycle.show()
    sys.stdout.write(shown)
    if not shown.endswith("\n"):
        sys.stdout.write("\n")
    return 0 if cycle.goal else 1


def _cmd_hook(args: argparse.Namespace) -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    root = Path(args.root) if args.root else Path.cwd()
    _print_json(handle_hook(args.event, payload, root))
    return 0


def _cmd_revise(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    guard.revise(
        goal=args.goal,
        constraints=args.constraint if args.constraint else None,
        done_means=args.done_means,
        check_cmd=args.check_cmd,
        allow_paths=args.allow_path if args.allow_path else None,
    )
    _print_json({"status": "revised", "goal": guard.spec.goal, "drift": guard.status()["drift"]})
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--session",
        type=Path,
        default=None,
        help="Session JSON path (default: .context-guard/session.json)",
    )
    parser = argparse.ArgumentParser(
        prog="context-guard",
        description=(
            "Portable quality sensor for agent chats: re-inject the goal, "
            "flag mechanical drift, and leave an event receipt."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", parents=[common], help="Start a session")
    init.add_argument("--goal", required=True)
    init.add_argument("--done-means", required=True, dest="done_means")
    init.add_argument("--constraint", action="append", default=[])
    init.add_argument("--check-cmd", dest="check_cmd", default=None)
    init.add_argument("--allow-path", action="append", default=[])
    init.add_argument("--compact-every", type=int, default=20)
    init.add_argument("--anchor-every", type=int, default=5)
    init.add_argument("--fail-streak", type=int, default=3)
    init.add_argument("--token-ceiling", type=int, default=8000)
    init.add_argument("--mention-gap", type=int, default=12)
    init.add_argument("--allow-done-on-red", action="store_true")
    init.add_argument(
        "--no-compact",
        action="store_true",
        help="Leave compaction to the host (Cursor/Claude). Still pins, anchors, and flags drift.",
    )
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=_cmd_init)

    turn = sub.add_parser("turn", parents=[common], help="Append a user, assistant, tool, or system turn")
    turn.add_argument("role", choices=["user", "assistant", "tool", "system"])
    turn.add_argument("content")
    turn.set_defaults(func=_cmd_turn)

    check = sub.add_parser("check", parents=[common], help="Record a verify-command result")
    check.add_argument("--exit-code", type=int, required=True, dest="exit_code")
    check.add_argument("--log", default="")
    check.set_defaults(func=_cmd_check)

    messages = sub.add_parser("messages", parents=[common], help="Print the model-bound window")
    messages.add_argument("--json", action="store_true")
    messages.add_argument(
        "--before-done",
        action="store_true",
        help="Force a goal anchor, as if a completion attempt is next",
    )
    messages.set_defaults(func=_cmd_messages)

    status = sub.add_parser("status", parents=[common], help="Print drift and session counters")
    status.set_defaults(func=_cmd_status)

    quality = sub.add_parser(
        "quality-check",
        parents=[common],
        help="Score drift and preview whether done would pass (does not mark done)",
    )
    quality.set_defaults(func=_cmd_quality_check)

    log = sub.add_parser("log", parents=[common], help="Print the action event receipt")
    log.add_argument("--tail", type=int, default=None, help="Only the last N events")
    log.set_defaults(func=_cmd_log)

    pulse = sub.add_parser(
        "pulse",
        parents=[common],
        help="Lightweight background tick: short note, realign on drift",
    )
    pulse.add_argument(
        "--ensure",
        action="store_true",
        help="Create a session automatically if missing (for hooks)",
    )
    pulse.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="With --ensure: create/load session and exit without pulsing",
    )
    pulse.add_argument("--goal", default=None, help="Used with --ensure")
    pulse.add_argument("--done-means", dest="done_means", default=None, help="Used with --ensure")
    pulse.add_argument("--check-cmd", dest="check_cmd", default=None, help="Used with --ensure")
    pulse.add_argument("--fail-streak", type=int, default=3, help="Used with --ensure")
    pulse.add_argument("--mention-gap", type=int, default=12, help="Used with --ensure")
    pulse.add_argument("--pulse-every", type=int, default=3, dest="pulse_every", help="Speak every N clean pulses")
    pulse.add_argument(
        "--compact",
        action="store_true",
        help="Allow L1 compact during pulse (off by default for Cursor/Claude hosts)",
    )
    pulse.add_argument("--snippet", default="", help="Optional recent assistant text to ingest")
    pulse.add_argument("--snippet-file", type=Path, default=None)
    pulse.add_argument(
        "--record-only",
        action="store_true",
        help="Ingest/realign without advancing the speak cadence (afterAgentResponse)",
    )
    pulse.add_argument("--plain", action="store_true", help="Print only the short note")
    pulse.set_defaults(func=_cmd_pulse)

    done = sub.add_parser("done", parents=[common], help="Try to mark the session done")
    done.set_defaults(func=_cmd_done)

    revise = sub.add_parser("revise", parents=[common], help="Replace the goal and reset drift counters")
    revise.add_argument("--goal", default=None)
    revise.add_argument("--done-means", dest="done_means", default=None)
    revise.add_argument("--constraint", action="append", default=[])
    revise.add_argument("--check-cmd", dest="check_cmd", default=None)
    revise.add_argument("--allow-path", action="append", default=[])
    revise.set_defaults(func=_cmd_revise)

    def _add_goal_parser(name: str) -> None:
        parser = sub.add_parser(name, help="Name the current goal of a large task")
        parser_sub = parser.add_subparsers(dest="goal_cmd", required=True)
        start = parser_sub.add_parser("start", parents=[common], help="Open or replace the current goal")
        start.add_argument("--goal", required=True)
        start.add_argument("--done-means", dest="done_means", default="")
        start.add_argument("--check", default="")
        start.add_argument("--mission", default=None)
        start.add_argument("--conversation", default="default")
        start.add_argument("--root", type=Path, default=None)
        start.set_defaults(func=_cmd_unit_start)
        show = parser_sub.add_parser("show", parents=[common], help="Print the living goal")
        show.add_argument("--conversation", default="default")
        show.add_argument("--root", type=Path, default=None)
        show.set_defaults(func=_cmd_goal_show)
        recover = parser_sub.add_parser(
            "recover",
            parents=[common],
            help="Scan this chat's history and arm a living goal",
        )
        recover.add_argument("--conversation", default="default")
        recover.add_argument("--root", type=Path, default=None)
        recover.add_argument(
            "--transcript",
            type=Path,
            default=None,
            help="Optional Cursor JSONL transcript to merge into prompts",
        )
        recover.set_defaults(func=_cmd_goal_recover)

    _add_goal_parser("goal")
    _add_goal_parser("unit")  # deprecated alias

    hook = sub.add_parser("hook", help="Cursor hook adapter (JSON stdin, hook JSON stdout)")
    hook.add_argument(
        "--event",
        required=True,
        choices=[
            "beforeSubmitPrompt",
            "afterAgentResponse",
            "postToolUse",
            "sessionStart",
            "stop",
        ],
    )
    hook.add_argument("--root", type=Path, default=None)
    hook.set_defaults(func=_cmd_hook)
    return parser


def _pull_session(argv: list[str]) -> tuple[Path | None, list[str]]:
    """Accept `--session` before or after the subcommand."""
    session: Path | None = None
    cleaned: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--session":
            if index + 1 >= len(argv):
                print("context-guard: --session requires a path", file=sys.stderr)
                raise SystemExit(2)
            session = Path(argv[index + 1])
            index += 2
            continue
        if token.startswith("--session="):
            session = Path(token.split("=", 1)[1])
            index += 1
            continue
        cleaned.append(token)
        index += 1
    return session, cleaned


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    session, cleaned = _pull_session(raw)
    args = build_parser().parse_args(cleaned)
    if session is not None:
        args.session = session
    return int(args.func(args))
