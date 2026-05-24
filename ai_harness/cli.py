from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .connectors import render_connector_command
from .dispatch import dispatch_plan
from .executor import run_connector_command
from .gates import run_pr_gate, run_validation_gate
from .git_publish import (
    render_commit_command,
    render_push_command,
    run_commit_command,
    run_diff_gate,
    run_push_command,
)
from .lifecycle import (
    acquire_writer_lock,
    render_skill_evolution_plan,
    run_ci_eval_gate,
    run_merge_gate,
    run_review_gate,
    transfer_writer_lock,
)
from .orchestrator import dispatch_run
from .pull_requests import render_pr_command, run_pr_command
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

    connector_parser = subparsers.add_parser("connector-command", help="Render the CLI connector command for a run.")
    connector_parser.add_argument("--target", default=".", help="Target repository root.")
    connector_parser.add_argument("--run", required=True, help="Run id.")
    connector_parser.add_argument(
        "--output-schema",
        default=".ai/schemas/agent_result.schema.json",
        help="Schema path passed to the connector template.",
    )

    run_connector_parser = subparsers.add_parser("run-connector", help="Execute a rendered connector command.")
    run_connector_parser.add_argument("--target", default=".", help="Target repository root.")
    run_connector_parser.add_argument("--run", required=True, help="Run id.")
    run_connector_parser.add_argument("--timeout", type=float, default=900.0, help="Timeout seconds per attempt.")
    run_connector_parser.add_argument("--retries", type=int, default=0, help="Retry count after failed attempts.")

    validation_parser = subparsers.add_parser("validation-gate", help="Run or record validation gate results.")
    validation_parser.add_argument("--target", default=".", help="Target repository root.")
    validation_parser.add_argument("--run", required=True, help="Run id.")
    validation_parser.add_argument("--timeout", type=float, default=900.0, help="Timeout seconds per validation command.")
    validation_parser.add_argument("--mode", choices=["run", "skip"], default="run", help="Validation mode.")

    pr_gate_parser = subparsers.add_parser("pr-gate", help="Evaluate PR readiness gate for a run.")
    pr_gate_parser.add_argument("--target", default=".", help="Target repository root.")
    pr_gate_parser.add_argument("--run", required=True, help="Run id.")

    pr_command_parser = subparsers.add_parser("pr-command", help="Render a gh pr create command for a gated writer run.")
    pr_command_parser.add_argument("--target", default=".", help="Target repository root.")
    pr_command_parser.add_argument("--run", required=True, help="Run id.")
    pr_command_parser.add_argument("--base", default="main", help="Base branch for the pull request.")
    pr_command_parser.add_argument("--draft", action="store_true", help="Render the pull request as a draft.")
    pr_command_parser.add_argument("--executable", default="gh", help="GitHub CLI executable.")

    run_pr_command_parser = subparsers.add_parser("run-pr-command", help="Execute a rendered PR command.")
    run_pr_command_parser.add_argument("--target", default=".", help="Target repository root.")
    run_pr_command_parser.add_argument("--run", required=True, help="Run id.")
    run_pr_command_parser.add_argument("--timeout", type=float, default=900.0, help="Timeout seconds for the PR command.")

    diff_gate_parser = subparsers.add_parser("diff-gate", help="Evaluate writer worktree diff before commit.")
    diff_gate_parser.add_argument("--target", default=".", help="Target repository root.")
    diff_gate_parser.add_argument("--run", required=True, help="Run id.")

    commit_command_parser = subparsers.add_parser("commit-command", help="Render deterministic git add/commit steps.")
    commit_command_parser.add_argument("--target", default=".", help="Target repository root.")
    commit_command_parser.add_argument("--run", required=True, help="Run id.")
    commit_command_parser.add_argument("--message", help="Commit message. Defaults to the AI run title.")

    run_commit_command_parser = subparsers.add_parser("run-commit-command", help="Execute rendered commit steps.")
    run_commit_command_parser.add_argument("--target", default=".", help="Target repository root.")
    run_commit_command_parser.add_argument("--run", required=True, help="Run id.")
    run_commit_command_parser.add_argument("--timeout", type=float, default=900.0, help="Timeout seconds per commit step.")

    push_command_parser = subparsers.add_parser("push-command", help="Render deterministic git push command.")
    push_command_parser.add_argument("--target", default=".", help="Target repository root.")
    push_command_parser.add_argument("--run", required=True, help="Run id.")
    push_command_parser.add_argument("--remote", default="origin", help="Git remote to push to.")

    run_push_command_parser = subparsers.add_parser("run-push-command", help="Execute rendered push command.")
    run_push_command_parser.add_argument("--target", default=".", help="Target repository root.")
    run_push_command_parser.add_argument("--run", required=True, help="Run id.")
    run_push_command_parser.add_argument("--timeout", type=float, default=900.0, help="Timeout seconds for git push.")

    ci_eval_gate_parser = subparsers.add_parser("ci-eval-gate", help="Evaluate CI and eval readiness for a run.")
    ci_eval_gate_parser.add_argument("--target", default=".", help="Target repository root.")
    ci_eval_gate_parser.add_argument("--run", required=True, help="Run id.")

    review_gate_parser = subparsers.add_parser("review-gate", help="Evaluate structured review findings for a run.")
    review_gate_parser.add_argument("--target", default=".", help="Target repository root.")
    review_gate_parser.add_argument("--run", required=True, help="Run id.")

    writer_lock_parser = subparsers.add_parser("writer-lock", help="Acquire the branch writer lock for a writer run.")
    writer_lock_parser.add_argument("--target", default=".", help="Target repository root.")
    writer_lock_parser.add_argument("--run", required=True, help="Run id.")

    writer_transfer_parser = subparsers.add_parser("writer-transfer", help="Transfer a branch writer lock to another run.")
    writer_transfer_parser.add_argument("--target", default=".", help="Target repository root.")
    writer_transfer_parser.add_argument("--from-run", required=True, help="Current owner run id.")
    writer_transfer_parser.add_argument("--to-run", required=True, help="New owner run id.")
    writer_transfer_parser.add_argument("--reason", required=True, help="Auditable transfer reason.")

    merge_gate_parser = subparsers.add_parser("merge-gate", help="Evaluate merge readiness without merging.")
    merge_gate_parser.add_argument("--target", default=".", help="Target repository root.")
    merge_gate_parser.add_argument("--run", required=True, help="Run id.")
    merge_gate_parser.add_argument("--human-approved", action="store_true", help="Record human approval for high-risk runs.")

    skill_evolution_parser = subparsers.add_parser("skill-evolution-plan", help="Recommend skill-curator work from repeated findings.")
    skill_evolution_parser.add_argument("--target", default=".", help="Target repository root.")
    skill_evolution_parser.add_argument("--source-run", required=True, help="Source run id containing findings or trace.")
    skill_evolution_parser.add_argument("--run-id", required=True, help="Suggested skill evolution schedule run id.")

    dispatch_run_parser = subparsers.add_parser("dispatch-run", help="Dispatch, execute, validate, and gate a SchedulePlan.")
    dispatch_run_parser.add_argument("--target", default=".", help="Target repository root.")
    dispatch_run_parser.add_argument("--issue", required=True, help="Issue id, such as 123 or issue-123.")
    dispatch_run_parser.add_argument("--plan", required=True, help="Path to SchedulePlan JSON.")
    dispatch_run_parser.add_argument("--run-id", required=True, help="Schedule run id.")
    dispatch_run_parser.add_argument("--base-ref", default="HEAD", help="Git base ref for worktree creation.")
    dispatch_run_parser.add_argument("--timeout", type=float, default=900.0, help="Timeout seconds per connector/validation attempt.")
    dispatch_run_parser.add_argument("--retries", type=int, default=0, help="Retry count after failed connector attempts.")
    dispatch_run_parser.add_argument(
        "--prepare-pr-command",
        action="store_true",
        help="Render gh pr create commands for gated writer child runs.",
    )
    dispatch_run_parser.add_argument("--pr-base", default="main", help="Base branch for prepared PR commands.")
    dispatch_run_parser.add_argument("--draft-pr", action="store_true", help="Render prepared PR commands as draft PRs.")
    dispatch_run_parser.add_argument(
        "--commit-and-push",
        action="store_true",
        help="After PR gate, commit worktree changes and push the run branch before PR command preparation.",
    )
    dispatch_run_parser.add_argument("--push-remote", default="origin", help="Git remote used by --commit-and-push.")
    dispatch_run_parser.add_argument(
        "--validation-mode",
        choices=["run", "skip"],
        default="run",
        help="Whether to run validation commands or mark them skipped.",
    )
    dispatch_run_parser.add_argument(
        "--no-worktree",
        action="store_true",
        help="Prepare dispatch metadata without creating git worktrees.",
    )

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
        if args.command == "connector-command":
            command_path = render_connector_command(
                target=target,
                run_id=args.run,
                output_schema=args.output_schema,
            )
            print(f"Wrote connector command to {command_path}")
            return 0
        if args.command == "run-connector":
            execution = run_connector_command(
                target=target,
                run_id=args.run,
                timeout_seconds=args.timeout,
                retries=args.retries,
            )
            print(f"Connector run {execution['status']} for {args.run}")
            return 0 if execution["status"] == "succeeded" else 1
        if args.command == "validation-gate":
            gate = run_validation_gate(
                target=target,
                run_id=args.run,
                timeout_seconds=args.timeout,
                mode=args.mode,
            )
            print(f"Validation gate {gate['status']} for {args.run}")
            return 0 if gate["status"] in {"passed", "skipped"} else 1
        if args.command == "pr-gate":
            gate = run_pr_gate(target=target, run_id=args.run)
            print(f"PR gate {gate['status']} for {args.run}")
            return 0 if gate["status"] in {"passed", "not_required"} else 1
        if args.command == "pr-command":
            command_path = render_pr_command(
                target=target,
                run_id=args.run,
                base=args.base,
                draft=args.draft,
                executable=args.executable,
            )
            print(f"Wrote PR command to {command_path}")
            return 0
        if args.command == "run-pr-command":
            execution = run_pr_command(target=target, run_id=args.run, timeout_seconds=args.timeout)
            print(f"PR command {execution['status']} for {args.run}")
            return 0 if execution["status"] == "succeeded" else 1
        if args.command == "diff-gate":
            gate = run_diff_gate(target=target, run_id=args.run)
            print(f"Diff gate {gate['status']} for {args.run}")
            return 0 if gate["status"] == "passed" else 1
        if args.command == "commit-command":
            command_path = render_commit_command(target=target, run_id=args.run, message=args.message)
            print(f"Wrote commit command to {command_path}")
            return 0
        if args.command == "run-commit-command":
            execution = run_commit_command(target=target, run_id=args.run, timeout_seconds=args.timeout)
            print(f"Commit command {execution['status']} for {args.run}")
            return 0 if execution["status"] == "succeeded" else 1
        if args.command == "push-command":
            command_path = render_push_command(target=target, run_id=args.run, remote=args.remote)
            print(f"Wrote push command to {command_path}")
            return 0
        if args.command == "run-push-command":
            execution = run_push_command(target=target, run_id=args.run, timeout_seconds=args.timeout)
            print(f"Push command {execution['status']} for {args.run}")
            return 0 if execution["status"] == "succeeded" else 1
        if args.command == "ci-eval-gate":
            gate = run_ci_eval_gate(target=target, run_id=args.run)
            print(f"CI/Eval gate {gate['status']} for {args.run}")
            return 0 if gate["status"] == "passed" else 1
        if args.command == "review-gate":
            gate = run_review_gate(target=target, run_id=args.run)
            print(f"Review gate {gate['status']} for {args.run}")
            return 0 if gate["status"] == "passed" else 1
        if args.command == "writer-lock":
            lock = acquire_writer_lock(target=target, run_id=args.run)
            print(f"Writer lock owned by {lock['owner_run_id']} for {args.run}")
            return 0
        if args.command == "writer-transfer":
            lock = transfer_writer_lock(
                target=target,
                from_run_id=args.from_run,
                to_run_id=args.to_run,
                reason=args.reason,
            )
            print(f"Writer lock transferred to {lock['owner_run_id']}")
            return 0
        if args.command == "merge-gate":
            gate = run_merge_gate(target=target, run_id=args.run, human_approved=args.human_approved)
            print(f"Merge gate {gate['status']} for {args.run}")
            return 0 if gate["status"] == "passed" else 1
        if args.command == "skill-evolution-plan":
            plan = render_skill_evolution_plan(target=target, source_run_id=args.source_run, run_id=args.run_id)
            print(f"Skill evolution plan {plan['status']} for {args.source_run}")
            return 0
        if args.command == "dispatch-run":
            summary = dispatch_run(
                target=target,
                issue=args.issue,
                plan_path=Path(args.plan).expanduser().resolve(),
                run_id=args.run_id,
                timeout_seconds=args.timeout,
                retries=args.retries,
                validation_mode=args.validation_mode,
                create_worktree=not args.no_worktree,
                base_ref=args.base_ref,
                prepare_pr_command=args.prepare_pr_command,
                pr_base=args.pr_base,
                draft_pr=args.draft_pr,
                commit_and_push=args.commit_and_push,
                push_remote=args.push_remote,
            )
            print(f"Dispatch run {summary['status']} for {args.run_id}")
            return 0 if summary["status"] == "succeeded" else 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2
