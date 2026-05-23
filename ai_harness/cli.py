from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .dispatch import dispatch_plan
from .runs import create_run, render_pr_body
from .scaffold import init_scaffold
from .validation import validate_scaffold


class HarnessError(Exception):
    """User-facing harness error."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="Codex / Claude Code neutral AI automation development harness.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the harness scaffold.")
    init_parser.add_argument("--target", default=".", help="Target repository root.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite managed files.")

    validate_parser = subparsers.add_parser("validate", help="Validate harness configuration.")
    validate_parser.add_argument("--target", default=".", help="Target repository root.")

    run_parser = subparsers.add_parser("create-run", help="Create an isolated agent run record.")
    run_parser.add_argument("--target", default=".", help="Target repository root.")
    run_parser.add_argument("--issue", required=True, help="Issue id, such as 123 or issue-123.")
    run_parser.add_argument("--agent", required=True, help="Agent identity id.")
    run_parser.add_argument("--task", required=True, help="Path to task JSON.")
    run_parser.add_argument("--run-id", help="Explicit run id for deterministic automation.")
    run_parser.add_argument("--base-ref", default="HEAD", help="Git base ref for worktree creation.")
    run_parser.add_argument(
        "--mode",
        choices=["read_only", "writer"],
        help="Run mode. Defaults from the agent identity type.",
    )
    run_parser.add_argument(
        "--no-worktree",
        action="store_true",
        help="Only create metadata; do not create a git worktree.",
    )

    dispatch_parser = subparsers.add_parser("dispatch-plan", help="Prepare runs from a runtime-blind SchedulePlan.")
    dispatch_parser.add_argument("--target", default=".", help="Target repository root.")
    dispatch_parser.add_argument("--issue", required=True, help="Issue id, such as 123 or issue-123.")
    dispatch_parser.add_argument("--plan", required=True, help="Path to SchedulePlan JSON.")
    dispatch_parser.add_argument("--run-id", required=True, help="Schedule run id.")
    dispatch_parser.add_argument("--base-ref", default="HEAD", help="Git base ref for worktree creation.")
    dispatch_parser.add_argument(
        "--no-worktree",
        action="store_true",
        help="Prepare dispatch metadata without creating git worktrees.",
    )

    pr_parser = subparsers.add_parser("pr-body", help="Render a PR body from a run evidence bundle.")
    pr_parser.add_argument("--target", default=".", help="Target repository root.")
    pr_parser.add_argument("--run", required=True, help="Run id.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    target = Path(getattr(args, "target", ".")).expanduser().resolve()

    try:
        if args.command == "init":
            init_scaffold(target, force=args.force)
            print(f"Initialized AI harness scaffold at {target}")
            return 0
        if args.command == "validate":
            validate_scaffold(target)
            print(f"AI harness scaffold is valid at {target}")
            return 0
        if args.command == "create-run":
            run = create_run(
                target=target,
                issue=args.issue,
                agent_id=args.agent,
                task_path=Path(args.task).expanduser().resolve(),
                run_id=args.run_id,
                base_ref=args.base_ref,
                create_worktree=not args.no_worktree,
                mode=args.mode,
            )
            print(f"Created run {run['run_id']} for agent {run['agent_id']}")
            print(f"Branch: {run['branch']}")
            print(f"Worktree: {run['worktree']}")
            return 0
        if args.command == "dispatch-plan":
            schedule_dir = dispatch_plan(
                target=target,
                issue=args.issue,
                plan_path=Path(args.plan).expanduser().resolve(),
                run_id=args.run_id,
                base_ref=args.base_ref,
                create_worktree=not args.no_worktree,
            )
            print(f"Prepared dispatch plan at {schedule_dir}")
            return 0
        if args.command == "pr-body":
            body_path = render_pr_body(target=target, run_id=args.run)
            print(f"Wrote PR body to {body_path}")
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2
