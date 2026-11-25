"""Thin CLI over ContextRotGuard. Session file: .context-rot-guard/session.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from context_rot_guard.guard import ContextRotGuard
from context_rot_guard.loop import contract_for_check, write_feature_pack
from context_rot_guard.models import GoalSpec, GuardConfig


def default_session_path() -> Path:
    return Path.cwd() / ".context-rot-guard" / "session.json"


def _path(args: argparse.Namespace) -> Path:
    if args.session is not None:
        return Path(args.session)
    return default_session_path()


def _print_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _load(path: Path) -> ContextRotGuard:
    if not path.is_file():
        print("No session at %s. Run `context-rot-guard init` first." % path, file=sys.stderr)
        raise SystemExit(2)
    return ContextRotGuard.load(path)


def _cmd_init(args: argparse.Namespace) -> int:
    path = _path(args)
    if path.exists() and not args.force:
        print("Session already exists at %s. Pass --force to replace it." % path, file=sys.stderr)
        return 2
    acceptance = contract_for_check(args.check_cmd) if args.check_cmd else None
    spec = GoalSpec(
        goal=args.goal,
        constraints=list(args.constraint or []),
        done_means=args.done_means,
        check_cmd=args.check_cmd,
        allow_paths=list(args.allow_path or []),
        acceptance=acceptance,
    )
    config = GuardConfig(
        compact_every=args.compact_every,
        anchor_every=args.anchor_every,
        fail_streak_limit=args.fail_streak,
        token_ceiling=args.token_ceiling,
        mention_gap=args.mention_gap,
        block_done_on_red=not args.allow_done_on_red,
        max_check_attempts=args.max_check_attempts,
        no_progress_window=args.no_progress_window,
    )
    guard = ContextRotGuard(spec, config=config, session_path=path)
    guard._save()
    _print_json({"status": "initialized", "session": str(path), "goal": spec.goal})
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


def _cmd_done(args: argparse.Namespace) -> int:
    guard = _load(_path(args))
    messages = guard.process(before_completion=True)
    result = guard.attempt_done()
    result["anchor_injected"] = any(
        message.get("meta", {}).get("kind") == "anchor" for message in messages
    )
    _print_json(result)
    return 0 if result["status"] == "done" else 2


def _cmd_feature_start(args: argparse.Namespace) -> int:
    slug = str(args.slug)
    folder = Path(args.dest) if args.dest is not None else Path.cwd() / ".context-rot-guard" / "features" / slug
    try:
        written = write_feature_pack(
            folder,
            slug=slug,
            goal=args.goal,
            done_means=args.done_means,
            check_cmd=args.check_cmd,
            constraints=list(args.constraint or []),
            allow_paths=list(args.allow_path or []),
            max_check_attempts=args.max_check_attempts,
            no_progress_window=args.no_progress_window,
            force=args.force,
        )
    except (ValueError, FileExistsError) as exc:
        print("context-rot-guard: %s" % exc, file=sys.stderr)
        return 2
    _print_json(
        {
            "status": "scaffolded",
            "path": str(written),
            "acceptance": str(written / "acceptance.json"),
            "brief": str(written / "BRIEF.md"),
        }
    )
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
        help="Session JSON path (default: .context-rot-guard/session.json)",
    )
    parser = argparse.ArgumentParser(
        prog="context-rot-guard",
        description="Compress a long agent session, re-inject the goal, and flag mechanical drift.",
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
        "--max-check-attempts",
        type=int,
        default=None,
        help="Escalate after this many trailing red checks (default: unlimited)",
    )
    init.add_argument(
        "--no-progress-window",
        type=int,
        default=None,
        help="Escalate when this many trailing red outputs are identical",
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

    done = sub.add_parser("done", parents=[common], help="Try to mark the session done")
    done.set_defaults(func=_cmd_done)

    revise = sub.add_parser("revise", parents=[common], help="Replace the goal and reset drift counters")
    revise.add_argument("--goal", default=None)
    revise.add_argument("--done-means", dest="done_means", default=None)
    revise.add_argument("--constraint", action="append", default=[])
    revise.add_argument("--check-cmd", dest="check_cmd", default=None)
    revise.add_argument("--allow-path", action="append", default=[])
    revise.set_defaults(func=_cmd_revise)

    feature = sub.add_parser("feature", help="Scaffold one feature so the loop can be reused")
    feature_sub = feature.add_subparsers(dest="feature_cmd", required=True)
    start = feature_sub.add_parser("start", help="Write acceptance.json and BRIEF.md before coding")
    start.add_argument("--slug", required=True)
    start.add_argument("--goal", required=True)
    start.add_argument("--done-means", required=True, dest="done_means")
    start.add_argument("--check-cmd", required=True, dest="check_cmd")
    start.add_argument("--constraint", action="append", default=[])
    start.add_argument("--allow-path", action="append", default=[])
    start.add_argument("--max-check-attempts", type=int, default=3)
    start.add_argument("--no-progress-window", type=int, default=2)
    start.add_argument("--dest", type=Path, default=None)
    start.add_argument("--force", action="store_true")
    start.set_defaults(func=_cmd_feature_start)
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
                print("context-rot-guard: --session requires a path", file=sys.stderr)
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
