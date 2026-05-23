import json
import sys
import tempfile
import unittest
from pathlib import Path

from ai_harness.cli import main


class HarnessCliTests(unittest.TestCase):
    def test_init_creates_canonical_scaffold(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(main(["init", "--target", str(root)]), 0)
            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / ".ai" / "harness.yml").exists())
            self.assertTrue((root / ".ai" / "agent-catalog.yml").exists())
            self.assertTrue((root / ".ai" / "private" / "assignments.yml").exists())
            self.assertTrue((root / ".ai" / "agents" / "scheduler-agent.md").exists())
            self.assertTrue((root / ".ai" / "schemas" / "schedule_plan.schema.json").exists())
            self.assertTrue((root / ".claude" / "settings.json").exists())
            self.assertIn("CLAUDE.md", (root / ".gitignore").read_text())
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_scheduler_catalog_hides_runtime_bindings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            catalog = (root / ".ai" / "agent-catalog.yml").read_text()
            private = (root / ".ai" / "private" / "assignments.yml").read_text()
            self.assertIn("backend-implementer:", catalog)
            self.assertNotIn("codex-cli", catalog)
            self.assertNotIn("claude-code-cli", catalog)
            self.assertIn("connector: codex-cli", private)
            self.assertIn("connector: claude-code-cli", private)

    def test_validate_accepts_fresh_scaffold(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self.assertEqual(main(["validate", "--target", str(root)]), 0)

    def test_validate_rejects_nested_runtime_visible_catalog_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            catalog = root / ".ai" / "agent-catalog.yml"
            catalog.write_text(
                catalog.read_text().replace(
                    "  backend-implementer:\n    type: writer\n",
                    "  backend-implementer:\n    type: writer\n    metadata:\n      connector: codex-cli\n",
                )
            )
            self.assertEqual(main(["validate", "--target", str(root)]), 1)

    def test_create_run_writes_writer_metadata_without_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            task.write_text(json.dumps({"summary": "Add API", "acceptance": ["tests pass"]}))
            self.assertEqual(
                main(
                    [
                        "create-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--agent",
                        "backend-implementer",
                        "--task",
                        str(task),
                        "--run-id",
                        "run-20260523-001",
                        "--no-worktree",
                    ]
                ),
                0,
            )
            run_dir = root / ".ai" / "runs" / "run-20260523-001"
            run = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(run["agent_id"], "backend-implementer")
            self.assertEqual(run["connector"], "codex-cli")
            self.assertEqual(run["connector_profile"], "writer-workspace")
            self.assertEqual(run["branch"], "ai/issue-123/backend-implementer/run-20260523-001")
            self.assertEqual(run["worktree"], ".worktrees/run-20260523-001-backend-implementer")
            self.assertTrue((run_dir / "trace.jsonl").exists())
            self.assertTrue((run_dir / "evidence.json").exists())

    def test_create_run_worktree_failure_does_not_leave_stale_run_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            task.write_text(json.dumps({"summary": "Add API"}))
            self.assertEqual(
                main(
                    [
                        "create-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--agent",
                        "backend-implementer",
                        "--task",
                        str(task),
                        "--run-id",
                        "run-worktree-fails",
                    ]
                ),
                1,
            )
            self.assertFalse((root / ".ai" / "runs" / "run-worktree-fails").exists())

    def test_pr_body_renders_evidence_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            task.write_text(json.dumps({"summary": "Add API"}))
            main(
                [
                    "create-run",
                    "--target",
                    str(root),
                    "--issue",
                    "123",
                    "--agent",
                    "backend-implementer",
                    "--task",
                    str(task),
                    "--run-id",
                    "run-20260523-001",
                    "--no-worktree",
                ]
            )
            self.assertEqual(main(["pr-body", "--target", str(root), "--run", "run-20260523-001"]), 0)
            body = (root / ".ai" / "runs" / "run-20260523-001" / "pr-body.md").read_text()
            self.assertIn("Agent ID: backend-implementer", body)
            self.assertIn("Connector: codex-cli", body)
            self.assertIn("Closes #123", body)

    def test_connector_command_renders_codex_writer_command(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            task.write_text(json.dumps({"summary": "Add API"}))
            main(
                [
                    "create-run",
                    "--target",
                    str(root),
                    "--issue",
                    "123",
                    "--agent",
                    "backend-implementer",
                    "--task",
                    str(task),
                    "--run-id",
                    "run-command-001",
                    "--no-worktree",
                ]
            )
            self.assertEqual(main(["connector-command", "--target", str(root), "--run", "run-command-001"]), 0)
            command = json.loads((root / ".ai" / "runs" / "run-command-001" / "connector_command.json").read_text())
            self.assertEqual(command["connector"], "codex-cli")
            self.assertEqual(command["profile"], "writer-workspace")
            self.assertEqual(command["argv"][:2], ["codex", "exec"])
            self.assertIn("--cd", command["argv"])
            self.assertIn(".worktrees/run-command-001-backend-implementer", command["display"])
            self.assertIn(".ai/schemas/agent_result.schema.json", command["display"])

    def test_connector_command_renders_claude_readonly_command(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            task.write_text(json.dumps({"summary": "Review PR"}))
            main(
                [
                    "create-run",
                    "--target",
                    str(root),
                    "--issue",
                    "123",
                    "--agent",
                    "pr-reviewer",
                    "--task",
                    str(task),
                    "--run-id",
                    "run-command-002",
                    "--mode",
                    "read_only",
                    "--no-worktree",
                ]
            )
            self.assertEqual(main(["connector-command", "--target", str(root), "--run", "run-command-002"]), 0)
            command = json.loads((root / ".ai" / "runs" / "run-command-002" / "connector_command.json").read_text())
            self.assertEqual(command["connector"], "claude-code-cli")
            self.assertEqual(command["profile"], "reviewer-readonly")
            self.assertEqual(command["argv"][:3], ["claude", "--bare", "-p"])
            self.assertIn("--append-system-prompt-file", command["argv"])
            self.assertIn("AGENTS.md", command["argv"])

    def test_run_connector_captures_stdout_stderr_json_events_and_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-exec-001")
            command = {
                "run_id": "run-exec-001",
                "agent_id": "backend-implementer",
                "connector": "test-connector",
                "profile": "test-profile",
                "argv": [
                    sys.executable,
                    "-c",
                    "import json,sys; print(json.dumps({'event':'started','value':1})); print('plain stdout'); print('plain stderr', file=sys.stderr)",
                ],
            }
            (run_dir / "connector_command.json").write_text(json.dumps(command))
            self.assertEqual(main(["run-connector", "--target", str(root), "--run", "run-exec-001", "--timeout", "5"]), 0)

            execution = json.loads((run_dir / "connector_execution.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(execution["final_exit_code"], 0)
            self.assertEqual(len(execution["attempts"]), 1)
            self.assertIn("plain stdout", (run_dir / "stdout.log").read_text())
            self.assertIn("plain stderr", (run_dir / "stderr.log").read_text())
            events = (run_dir / "connector_events.jsonl").read_text().splitlines()
            self.assertEqual(json.loads(events[0])["event"], "started")
            trace = (run_dir / "trace.jsonl").read_text()
            self.assertIn("connector_attempt_finished", trace)
            self.assertIn("connector_run_finished", trace)

    def test_run_connector_retries_until_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-exec-002")
            counter = root / "counter.txt"
            script = (
                "from pathlib import Path\n"
                f"p = Path({str(counter)!r})\n"
                "count = int(p.read_text()) if p.exists() else 0\n"
                "p.write_text(str(count + 1))\n"
                "print('{\"event\":\"attempt\",\"count\":%d}' % (count + 1))\n"
                "raise SystemExit(1 if count == 0 else 0)\n"
            )
            command = {
                "run_id": "run-exec-002",
                "agent_id": "backend-implementer",
                "connector": "test-connector",
                "profile": "test-profile",
                "argv": [sys.executable, "-c", script],
            }
            (run_dir / "connector_command.json").write_text(json.dumps(command))
            self.assertEqual(
                main(["run-connector", "--target", str(root), "--run", "run-exec-002", "--timeout", "5", "--retries", "1"]),
                0,
            )

            execution = json.loads((run_dir / "connector_execution.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(execution["final_exit_code"], 0)
            self.assertEqual([attempt["exit_code"] for attempt in execution["attempts"]], [1, 0])
            self.assertEqual(counter.read_text(), "2")
            self.assertEqual(len((run_dir / "connector_events.jsonl").read_text().splitlines()), 2)

    def test_run_connector_timeout_records_failed_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-exec-003")
            command = {
                "run_id": "run-exec-003",
                "agent_id": "backend-implementer",
                "connector": "test-connector",
                "profile": "test-profile",
                "argv": [sys.executable, "-c", "import time; time.sleep(2)"],
            }
            (run_dir / "connector_command.json").write_text(json.dumps(command))
            self.assertEqual(main(["run-connector", "--target", str(root), "--run", "run-exec-003", "--timeout", "0.1"]), 1)

            execution = json.loads((run_dir / "connector_execution.json").read_text())
            self.assertEqual(execution["status"], "failed")
            self.assertTrue(execution["attempts"][0]["timed_out"])
            self.assertIsNone(execution["attempts"][0]["exit_code"])

    def test_run_connector_executes_from_declared_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            run_dir = self._make_manual_run(root, "run-exec-004")
            command = {
                "run_id": "run-exec-004",
                "agent_id": "backend-implementer",
                "connector": "test-connector",
                "profile": "test-profile",
                "workspace": "workspace",
                "argv": [sys.executable, "-c", "from pathlib import Path; print(Path.cwd().name)"],
            }
            (run_dir / "connector_command.json").write_text(json.dumps(command))
            self.assertEqual(main(["run-connector", "--target", str(root), "--run", "run-exec-004", "--timeout", "5"]), 0)
            self.assertEqual((run_dir / "stdout.log").read_text().strip(), "workspace")

    def test_validation_gate_runs_evidence_commands_and_updates_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-gate-001")
            evidence = {
                "agent": {"agent_id": "backend-implementer"},
                "issue": {"reference": "#123"},
                "scope": "Gate test",
                "validation": [
                    {"command": f"{sys.executable} -c \"print('validation ok')\"", "status": "not_run"}
                ],
                "risk": "low",
                "rollback": "revert",
            }
            (run_dir / "evidence.json").write_text(json.dumps(evidence))
            self.assertEqual(main(["validation-gate", "--target", str(root), "--run", "run-gate-001", "--timeout", "5"]), 0)

            gate = json.loads((run_dir / "validation_gate.json").read_text())
            updated = json.loads((run_dir / "evidence.json").read_text())
            self.assertEqual(gate["status"], "passed")
            self.assertEqual(gate["results"][0]["exit_code"], 0)
            self.assertIn("validation ok", gate["results"][0]["stdout"])
            self.assertEqual(updated["validation"][0]["status"], "passed")

    def test_validation_gate_runs_from_declared_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-gate-workspace")
            workspace = root / "workspace"
            workspace.mkdir()
            run = json.loads((run_dir / "run.json").read_text())
            run["worktree"] = "workspace"
            (run_dir / "run.json").write_text(json.dumps(run))
            evidence = {
                "agent": {"agent_id": "backend-implementer"},
                "issue": {"reference": "#123"},
                "scope": "Workspace gate test",
                "validation": [
                    {"command": f"{sys.executable} -c \"from pathlib import Path; print(Path.cwd().name)\""}
                ],
                "risk": "low",
                "rollback": "revert",
            }
            (run_dir / "evidence.json").write_text(json.dumps(evidence))

            self.assertEqual(main(["validation-gate", "--target", str(root), "--run", "run-gate-workspace", "--timeout", "5"]), 0)

            gate = json.loads((run_dir / "validation_gate.json").read_text())
            self.assertEqual(gate["results"][0]["stdout"].strip(), "workspace")

    def test_pr_gate_renders_body_and_blocks_failed_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            task.write_text(json.dumps({"summary": "Add API"}))
            main(
                [
                    "create-run",
                    "--target",
                    str(root),
                    "--issue",
                    "123",
                    "--agent",
                    "backend-implementer",
                    "--task",
                    str(task),
                    "--run-id",
                    "run-pr-gate-001",
                    "--no-worktree",
                ]
            )
            run_dir = root / ".ai" / "runs" / "run-pr-gate-001"
            (run_dir / "connector_execution.json").write_text(json.dumps({"status": "succeeded"}))
            (run_dir / "validation_gate.json").write_text(json.dumps({"status": "failed"}))
            self.assertEqual(main(["pr-gate", "--target", str(root), "--run", "run-pr-gate-001"]), 1)

            gate = json.loads((run_dir / "pr_gate.json").read_text())
            self.assertEqual(gate["status"], "blocked")
            self.assertIn("validation gate is failed", gate["reasons"])
            self.assertTrue((run_dir / "pr-body.md").exists())

    def test_dispatch_run_chains_connector_validation_and_pr_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self._install_test_connector(root)
            self._init_git_repo(root)
            plan = root / "schedule_plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T3",
                                "mode": "writer",
                                "depends_on": [],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                                "success_criteria": ["Connector succeeds"],
                            }
                        ],
                        "blocked": [],
                        "risk_notes": [],
                    }
                )
            )
            self.assertEqual(
                main(
                    [
                        "dispatch-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--plan",
                        str(plan),
                        "--run-id",
                        "run-dispatch-001",
                        "--validation-mode",
                        "skip",
                        "--timeout",
                        "5",
                    ]
                ),
                0,
            )

            schedule_dir = root / ".ai" / "runs" / "run-dispatch-001"
            child_dir = root / ".ai" / "runs" / "run-dispatch-001-T3-backend-implementer"
            summary = json.loads((schedule_dir / "dispatch_run.json").read_text())
            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(summary["children"][0]["run_id"], "run-dispatch-001-T3-backend-implementer")
            self.assertTrue((child_dir / "connector_command.json").exists())
            self.assertEqual(json.loads((child_dir / "connector_execution.json").read_text())["status"], "succeeded")
            self.assertEqual(json.loads((child_dir / "validation_gate.json").read_text())["status"], "skipped")
            self.assertEqual(json.loads((child_dir / "pr_gate.json").read_text())["status"], "passed")
            self.assertTrue((child_dir / "pr-body.md").exists())

    def test_dispatch_plan_targets_agent_identity_and_uses_private_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = root / "schedule_plan.json"
            main(["init", "--target", str(root)])
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T3",
                                "mode": "writer",
                                "depends_on": ["T1", "T2"],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                                "success_criteria": ["Backend tests pass"],
                            },
                            {
                                "agent_id": "pr-reviewer",
                                "task_id": "T4",
                                "mode": "read_only",
                                "depends_on": ["T3"],
                                "expected_output": "review_findings",
                                "requires_pr": False,
                                "risk_level": "low",
                                "success_criteria": ["Findings are structured"],
                            },
                        ],
                        "blocked": [],
                        "risk_notes": ["Auth work requires a security review."],
                    }
                )
            )
            self.assertEqual(
                main(
                    [
                        "dispatch-plan",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--plan",
                        str(plan),
                        "--run-id",
                        "run-schedule-001",
                        "--no-worktree",
                    ]
                ),
                0,
            )
            schedule_dir = root / ".ai" / "runs" / "run-schedule-001"
            log_lines = (schedule_dir / "dispatch_log.jsonl").read_text().splitlines()
            self.assertEqual(len(log_lines), 2)
            first = json.loads(log_lines[0])
            second = json.loads(log_lines[1])
            self.assertEqual(first["agent_id"], "backend-implementer")
            self.assertEqual(first["connector"], "codex-cli")
            self.assertEqual(first["connector_profile"], "writer-workspace")
            self.assertEqual(second["agent_id"], "pr-reviewer")
            self.assertEqual(second["connector"], "claude-code-cli")
            self.assertEqual(second["connector_profile"], "reviewer-readonly")
            child = root / ".ai" / "runs" / "run-schedule-001-T3-backend-implementer" / "run.json"
            self.assertEqual(json.loads(child.read_text())["agent_id"], "backend-implementer")

    def _make_manual_run(self, root: Path, run_id: str) -> Path:
        main(["init", "--target", str(root)])
        run_dir = root / ".ai" / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "agent_id": "backend-implementer",
                    "connector": "test-connector",
                    "connector_profile": "test-profile",
                    "state": "planned",
                }
            )
        )
        (run_dir / "trace.jsonl").write_text("")
        return run_dir

    def _install_test_connector(self, root: Path) -> None:
        connector = root / ".ai" / "connectors" / "test-cli.yml"
        connector.write_text(
            "\n".join(
                [
                    "id: test-cli",
                    "version: 1",
                    f"executable: {sys.executable}",
                    "profiles:",
                    "  test-profile:",
                    "    mode: test",
                    "command_templates:",
                    (
                        "  test-profile: "
                        f"{sys.executable} -c \"import json; print(json.dumps({{'event':'agent_done'}}))\""
                    ),
                    "",
                ]
            )
        )
        assignments = root / ".ai" / "private" / "assignments.yml"
        text = assignments.read_text()
        text = text.replace(
            "  backend-implementer:\n    connector: codex-cli\n    profile: writer-workspace\n",
            "  backend-implementer:\n    connector: test-cli\n    profile: test-profile\n",
        )
        assignments.write_text(text)

    def _init_git_repo(self, root: Path) -> None:
        import subprocess

        subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "add", "."], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_dispatch_plan_rejects_runtime_visible_to_scheduler(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = root / "bad_schedule_plan.json"
            main(["init", "--target", str(root)])
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "connector": "codex-cli",
                                "task_id": "T3",
                                "mode": "writer",
                                "depends_on": [],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                                "success_criteria": ["Backend tests pass"],
                            }
                        ],
                        "blocked": [],
                        "risk_notes": [],
                    }
                )
            )
            self.assertEqual(
                main(
                    [
                        "dispatch-plan",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--plan",
                        str(plan),
                        "--run-id",
                        "run-schedule-001",
                        "--no-worktree",
                    ]
                ),
                1,
            )

    def test_dispatch_plan_rejects_nested_runtime_visible_to_scheduler(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = root / "bad_nested_schedule_plan.json"
            main(["init", "--target", str(root)])
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T3",
                                "mode": "writer",
                                "depends_on": [],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                                "success_criteria": ["Backend tests pass"],
                                "metadata": {"connector": "codex-cli"},
                            }
                        ],
                        "blocked": [],
                        "risk_notes": [],
                    }
                )
            )
            self.assertEqual(
                main(
                    [
                        "dispatch-plan",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--plan",
                        str(plan),
                        "--run-id",
                        "run-schedule-001",
                        "--no-worktree",
                    ]
                ),
                1,
            )
            self.assertFalse((root / ".ai" / "runs" / "run-schedule-001").exists())

    def test_dispatch_plan_failure_removes_schedule_and_child_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = root / "schedule_plan.json"
            main(["init", "--target", str(root)])
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "pr-reviewer",
                                "task_id": "T1",
                                "mode": "read_only",
                                "depends_on": [],
                                "expected_output": "review_findings",
                                "requires_pr": False,
                                "risk_level": "low",
                                "success_criteria": ["Findings are structured"],
                            },
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T2",
                                "mode": "writer",
                                "depends_on": ["T1"],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                                "success_criteria": ["Backend tests pass"],
                            },
                        ],
                        "blocked": [],
                        "risk_notes": [],
                    }
                )
            )
            self.assertEqual(
                main(
                    [
                        "dispatch-plan",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--plan",
                        str(plan),
                        "--run-id",
                        "run-schedule-rollback",
                    ]
                ),
                1,
            )
            self.assertFalse((root / ".ai" / "runs" / "run-schedule-rollback").exists())
            self.assertFalse((root / ".ai" / "runs" / "run-schedule-rollback-T1-pr-reviewer").exists())
            self.assertFalse((root / ".ai" / "runs" / "run-schedule-rollback-T2-backend-implementer").exists())


if __name__ == "__main__":
    unittest.main()
