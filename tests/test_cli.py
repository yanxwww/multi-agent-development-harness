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
            self.assertTrue((root / ".ai" / "locks" / "branches").exists())
            self.assertTrue((root / ".ai" / "agents" / "scheduler-agent.md").exists())
            self.assertTrue((root / ".ai" / "agents" / "risk-approval-agent.md").exists())
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
            self.assertIn("risk-approval-agent:", catalog)
            self.assertNotIn("codex-cli", catalog)
            self.assertNotIn("claude-code-cli", catalog)
            self.assertIn("connector: codex-cli", private)
            self.assertIn("connector: claude-code-cli", private)
            self.assertIn("profile: risk-approval-readonly", private)

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

    def test_create_run_rejects_unsafe_run_id(self):
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
                        "../escape",
                        "--no-worktree",
                    ]
                ),
                1,
            )
            self.assertFalse((root / ".ai" / "escape").exists())

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

    def test_skill_sync_exposes_only_allowed_skills_for_bound_codex_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            task.write_text(json.dumps({"summary": "Add API"}))
            source_skill = root / ".ai" / "skills" / "backend-implementation" / "SKILL.md"
            source_skill.parent.mkdir(parents=True)
            source_skill.write_text(
                "---\nname: backend-implementation\ndescription: Custom backend implementation skill.\n---\n# Backend\n"
            )
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
                    "run-skill-sync-001",
                    "--no-worktree",
                ]
            )

            self.assertEqual(main(["skill-sync", "--target", str(root), "--run", "run-skill-sync-001"]), 0)

            run_dir = root / ".ai" / "runs" / "run-skill-sync-001"
            manifest = json.loads((run_dir / "skill_sync.json").read_text())
            self.assertEqual(manifest["connector"], "codex-cli")
            self.assertEqual(manifest["destination"], ".agents/skills")
            self.assertEqual(
                [item["id"] for item in manifest["skills"]],
                ["backend-implementation", "ci-failure-repair", "pr-evidence-bundle"],
            )
            self.assertEqual(
                (root / ".agents" / "skills" / "backend-implementation" / "SKILL.md").read_text(),
                source_skill.read_text(),
            )
            generated = (root / ".agents" / "skills" / "ci-failure-repair" / "SKILL.md").read_text()
            self.assertIn("Repair validation and CI failures.", generated)
            self.assertFalse((root / ".agents" / "skills" / "frontend-implementation").exists())
            self.assertFalse((root / ".claude" / "skills" / "backend-implementation").exists())

    def test_skill_sync_installs_writer_skills_inside_run_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            self._init_git_repo(root)
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
                        "run-skill-sync-worktree-001",
                    ]
                ),
                0,
            )

            self.assertEqual(main(["skill-sync", "--target", str(root), "--run", "run-skill-sync-worktree-001"]), 0)

            worktree = root / ".worktrees" / "run-skill-sync-worktree-001-backend-implementer"
            manifest = json.loads((root / ".ai" / "runs" / "run-skill-sync-worktree-001" / "skill_sync.json").read_text())
            self.assertEqual(manifest["destination_root"], ".worktrees/run-skill-sync-worktree-001-backend-implementer")
            self.assertTrue((worktree / ".agents" / "skills" / "backend-implementation" / "SKILL.md").exists())
            self.assertFalse((root / ".agents" / "skills" / "backend-implementation").exists())

    def test_skill_sync_routes_claude_bound_agent_to_claude_skill_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            task.write_text(json.dumps({"summary": "Add UI"}))
            main(
                [
                    "create-run",
                    "--target",
                    str(root),
                    "--issue",
                    "123",
                    "--agent",
                    "frontend-implementer",
                    "--task",
                    str(task),
                    "--run-id",
                    "run-skill-sync-claude-001",
                    "--no-worktree",
                ]
            )

            self.assertEqual(main(["skill-sync", "--target", str(root), "--run", "run-skill-sync-claude-001"]), 0)

            manifest = json.loads((root / ".ai" / "runs" / "run-skill-sync-claude-001" / "skill_sync.json").read_text())
            self.assertEqual(manifest["connector"], "claude-code-cli")
            self.assertEqual(manifest["destination"], ".claude/skills")
            self.assertTrue((root / ".claude" / "skills" / "frontend-implementation" / "SKILL.md").exists())
            self.assertFalse((root / ".agents" / "skills" / "frontend-implementation").exists())

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

    def test_run_connector_rejects_mutated_known_connector_command(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            self._install_test_connector(root)
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
                    "run-command-policy-001",
                    "--no-worktree",
                ]
            )
            self.assertEqual(main(["connector-command", "--target", str(root), "--run", "run-command-policy-001"]), 0)
            run_dir = root / ".ai" / "runs" / "run-command-policy-001"
            command = json.loads((run_dir / "connector_command.json").read_text())
            command["argv"] = [sys.executable, "-c", "print('mutated')"]
            (run_dir / "connector_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-connector", "--target", str(root), "--run", "run-command-policy-001", "--timeout", "5"]), 1)
            self.assertFalse((run_dir / "connector_execution.json").exists())

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

    def test_validation_gate_prefers_policy_commands_over_evidence_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-gate-policy")
            run = json.loads((run_dir / "run.json").read_text())
            run["validation_commands"] = [f"{sys.executable} -c \"print('policy command')\""]
            (run_dir / "run.json").write_text(json.dumps(run))
            evidence = {
                "agent": {"agent_id": "backend-implementer"},
                "issue": {"reference": "#123"},
                "scope": "Gate policy test",
                "validation": [
                    {"command": f"{sys.executable} -c \"print('tampered evidence')\"", "status": "not_run"}
                ],
                "risk": "low",
                "rollback": "revert",
            }
            (run_dir / "evidence.json").write_text(json.dumps(evidence))

            self.assertEqual(main(["validation-gate", "--target", str(root), "--run", "run-gate-policy", "--timeout", "5"]), 0)

            gate = json.loads((run_dir / "validation_gate.json").read_text())
            self.assertIn("policy command", gate["results"][0]["stdout"])
            self.assertNotIn("tampered evidence", gate["results"][0]["stdout"])

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

    def test_pr_command_requires_passed_pr_gate_and_renders_gh_create(self):
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
                    "run-pr-command-001",
                    "--no-worktree",
                ]
            )
            run_dir = root / ".ai" / "runs" / "run-pr-command-001"
            self.assertEqual(main(["pr-command", "--target", str(root), "--run", "run-pr-command-001"]), 1)

            (run_dir / "connector_execution.json").write_text(json.dumps({"status": "succeeded"}))
            (run_dir / "validation_gate.json").write_text(json.dumps({"status": "skipped"}))
            self.assertEqual(main(["pr-gate", "--target", str(root), "--run", "run-pr-command-001"]), 0)
            (run_dir / "push_execution.json").write_text(json.dumps({"status": "succeeded"}))
            self.assertEqual(main(["pr-command", "--target", str(root), "--run", "run-pr-command-001", "--base", "main", "--draft"]), 0)

            command = json.loads((run_dir / "pr_command.json").read_text())
            self.assertEqual(command["argv"][:3], ["gh", "pr", "create"])
            self.assertIn("--base", command["argv"])
            self.assertIn("main", command["argv"])
            self.assertIn("--head", command["argv"])
            self.assertIn("ai/issue-123/backend-implementer/run-pr-command-001", command["argv"])
            self.assertIn("--draft", command["argv"])
            self.assertEqual(command["title"], "[AI:backend-implementer] Add API")
            self.assertEqual(command["body_file"], ".ai/runs/run-pr-command-001/pr-body.md")

    def test_pr_command_requires_successful_push_and_rejects_mutated_argv(self):
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
                    "run-pr-command-policy-001",
                    "--no-worktree",
                ]
            )
            run_dir = root / ".ai" / "runs" / "run-pr-command-policy-001"
            (run_dir / "connector_execution.json").write_text(json.dumps({"status": "succeeded"}))
            (run_dir / "validation_gate.json").write_text(json.dumps({"status": "skipped"}))
            self.assertEqual(main(["pr-gate", "--target", str(root), "--run", "run-pr-command-policy-001"]), 0)
            self.assertEqual(main(["pr-command", "--target", str(root), "--run", "run-pr-command-policy-001"]), 1)

            (run_dir / "push_execution.json").write_text(json.dumps({"status": "succeeded"}))
            self.assertEqual(main(["pr-command", "--target", str(root), "--run", "run-pr-command-policy-001"]), 0)
            command = json.loads((run_dir / "pr_command.json").read_text())
            command["argv"] = [sys.executable, "-c", "print('mutated pr')"]
            (run_dir / "pr_command.json").write_text(json.dumps(command))
            self.assertEqual(main(["run-pr-command", "--target", str(root), "--run", "run-pr-command-policy-001", "--timeout", "5"]), 1)
            self.assertFalse((run_dir / "pr_execution.json").exists())

    def test_run_pr_command_captures_output_and_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-pr-exec-001")
            command = {
                "run_id": "run-pr-exec-001",
                "argv": [
                    sys.executable,
                    "-c",
                    "import sys; print('https://example.test/pull/1'); print('created', file=sys.stderr)",
                ],
            }
            (run_dir / "pr_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-pr-command", "--target", str(root), "--run", "run-pr-exec-001", "--timeout", "5"]), 0)

            execution = json.loads((run_dir / "pr_execution.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(execution["exit_code"], 0)
            self.assertIn("https://example.test/pull/1", (run_dir / "pr_stdout.log").read_text())
            self.assertIn("created", (run_dir / "pr_stderr.log").read_text())
            trace = (run_dir / "trace.jsonl").read_text()
            self.assertIn("pr_command_started", trace)
            self.assertIn("pr_command_finished", trace)

    def test_merge_command_requires_passed_merge_gate_and_executes_rendered_command(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-merge-command-001")
            fake_gh = root / "fake-gh"
            fake_gh.write_text("#!/bin/sh\necho merged \"$@\"\n")
            fake_gh.chmod(0o755)

            self.assertEqual(main(["merge-command", "--target", str(root), "--run", "run-merge-command-001"]), 1)

            (run_dir / "merge_gate.json").write_text(json.dumps({"status": "passed", "merge_ready": True}))
            self.assertEqual(main(["merge-command", "--target", str(root), "--run", "run-merge-command-001"]), 1)

            (run_dir / "pr_execution.json").write_text(json.dumps({"status": "succeeded", "url": "https://example.test/pull/1"}))
            self.assertEqual(
                main(
                    [
                        "merge-command",
                        "--target",
                        str(root),
                        "--run",
                        "run-merge-command-001",
                        "--method",
                        "squash",
                        "--delete-branch",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )
            command = json.loads((run_dir / "merge_command.json").read_text())
            self.assertEqual(command["argv"][:3], [str(fake_gh), "pr", "merge"])
            self.assertIn("ai/issue-123/backend-implementer/run-merge-command-001", command["argv"])
            self.assertIn("--squash", command["argv"])
            self.assertIn("--delete-branch", command["argv"])

            self.assertEqual(main(["run-merge-command", "--target", str(root), "--run", "run-merge-command-001", "--timeout", "5"]), 0)
            execution = json.loads((run_dir / "merge_execution.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(execution["exit_code"], 0)
            self.assertIn("merged pr merge", (run_dir / "merge_stdout.log").read_text())
            trace = (run_dir / "trace.jsonl").read_text()
            self.assertIn("merge_command_started", trace)
            self.assertIn("merge_command_finished", trace)

    def test_run_merge_command_rejects_mutated_argv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-merge-command-policy-001")
            fake_gh = root / "fake-gh"
            fake_gh.write_text("#!/bin/sh\necho merged \"$@\"\n")
            fake_gh.chmod(0o755)
            (run_dir / "merge_gate.json").write_text(json.dumps({"status": "passed", "merge_ready": True}))
            (run_dir / "pr_execution.json").write_text(json.dumps({"status": "succeeded", "url": "https://example.test/pull/2"}))
            self.assertEqual(
                main(
                    [
                        "merge-command",
                        "--target",
                        str(root),
                        "--run",
                        "run-merge-command-policy-001",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )
            command = json.loads((run_dir / "merge_command.json").read_text())
            command["argv"] = [sys.executable, "-c", "print('mutated merge')"]
            (run_dir / "merge_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-merge-command", "--target", str(root), "--run", "run-merge-command-policy-001", "--timeout", "5"]), 1)
            self.assertFalse((run_dir / "merge_execution.json").exists())

    def test_github_doctor_records_auth_repo_and_remote_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self._init_git_repo(root)
            remote = root / "remote.git"
            self._init_bare_remote(root, remote)
            fake_gh = root / "fake-gh"
            fake_gh.write_text(
                "#!/bin/sh\n"
                "if [ \"$1 $2\" = \"auth status\" ]; then echo authenticated; exit 0; fi\n"
                "if [ \"$1 $2\" = \"repo view\" ]; then echo '{\"nameWithOwner\":\"acme/repo\",\"url\":\"https://github.com/acme/repo\"}'; exit 0; fi\n"
                "exit 1\n"
            )
            fake_gh.chmod(0o755)

            self.assertEqual(main(["github-doctor", "--target", str(root), "--executable", str(fake_gh)]), 0)
            doctor = json.loads((root / ".ai" / "github_doctor.json").read_text())
            self.assertEqual(doctor["status"], "passed")
            self.assertEqual(doctor["repo"]["nameWithOwner"], "acme/repo")
            self.assertEqual(doctor["checks"]["auth"]["status"], "passed")
            self.assertEqual(doctor["checks"]["remote"]["status"], "passed")

    def test_github_checks_command_captures_checks_and_writes_ci_eval_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-github-checks-001")
            fake_gh = root / "fake-gh"
            fake_gh.write_text(
                "#!/bin/sh\n"
                "printf '[{\"name\":\"unit\",\"bucket\":\"pass\",\"state\":\"SUCCESS\",\"workflow\":\"ci\"},"
                "{\"name\":\"lint\",\"bucket\":\"skipping\",\"state\":\"SKIPPED\",\"workflow\":\"ci\"}]'\n"
            )
            fake_gh.chmod(0o755)
            (run_dir / "pr_execution.json").write_text(
                json.dumps({"status": "succeeded", "url": "https://github.com/acme/repo/pull/7", "number": 7})
            )

            self.assertEqual(
                main(
                    [
                        "github-checks-command",
                        "--target",
                        str(root),
                        "--run",
                        "run-github-checks-001",
                        "--watch",
                        "--interval",
                        "1",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )
            command = json.loads((run_dir / "github_checks_command.json").read_text())
            self.assertEqual(command["argv"][:3], [str(fake_gh), "pr", "checks"])
            self.assertIn("7", command["argv"])
            self.assertIn("--watch", command["argv"])

            self.assertEqual(main(["run-github-checks-command", "--target", str(root), "--run", "run-github-checks-001", "--timeout", "5"]), 0)
            execution = json.loads((run_dir / "github_checks_execution.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            ci = json.loads((run_dir / "ci_results.json").read_text())
            eval_results = json.loads((run_dir / "eval_results.json").read_text())
            self.assertEqual(ci["status"], "passed")
            self.assertEqual([check["status"] for check in ci["checks"]], ["passed", "skipped"])
            self.assertEqual(eval_results["status"], "passed")
            self.assertEqual(eval_results["checks"][0]["status"], "skipped")

    def test_run_github_checks_command_marks_empty_failed_cli_output_as_failed_ci(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-github-checks-empty-failed-001")
            fake_gh = root / "fake-gh"
            fake_gh.write_text("#!/bin/sh\nexit 1\n")
            fake_gh.chmod(0o755)
            (run_dir / "pr_execution.json").write_text(json.dumps({"status": "succeeded", "number": 11}))
            self.assertEqual(
                main(
                    [
                        "github-checks-command",
                        "--target",
                        str(root),
                        "--run",
                        "run-github-checks-empty-failed-001",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )

            self.assertEqual(
                main(["run-github-checks-command", "--target", str(root), "--run", "run-github-checks-empty-failed-001", "--timeout", "5"]),
                1,
            )

            execution = json.loads((run_dir / "github_checks_execution.json").read_text())
            ci = json.loads((run_dir / "ci_results.json").read_text())
            self.assertEqual(execution["status"], "failed")
            self.assertEqual(ci["status"], "failed")
            self.assertEqual(ci["checks"][0]["status"], "failed")

    def test_run_github_checks_command_rejects_mutated_argv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-github-checks-policy-001")
            fake_gh = root / "fake-gh"
            fake_gh.write_text("#!/bin/sh\necho '[]'\n")
            fake_gh.chmod(0o755)
            (run_dir / "pr_execution.json").write_text(json.dumps({"status": "succeeded", "number": 9}))
            self.assertEqual(
                main(["github-checks-command", "--target", str(root), "--run", "run-github-checks-policy-001", "--executable", str(fake_gh)]),
                0,
            )
            command = json.loads((run_dir / "github_checks_command.json").read_text())
            command["argv"] = [sys.executable, "-c", "print('mutated checks')"]
            (run_dir / "github_checks_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-github-checks-command", "--target", str(root), "--run", "run-github-checks-policy-001", "--timeout", "5"]), 1)
            self.assertFalse((run_dir / "github_checks_execution.json").exists())

    def test_ci_eval_gate_blocks_missing_or_failed_results_and_passes_green_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-ci-eval-001")

            self.assertEqual(main(["ci-eval-gate", "--target", str(root), "--run", "run-ci-eval-001"]), 1)
            gate = json.loads((run_dir / "ci_eval_gate.json").read_text())
            self.assertEqual(gate["status"], "blocked")
            self.assertIn("CI results are missing", gate["reasons"])
            self.assertIn("Eval results are missing", gate["reasons"])

            (run_dir / "ci_results.json").write_text(json.dumps({"status": "passed", "checks": [{"name": "unit", "status": "passed"}]}))
            (run_dir / "eval_results.json").write_text(json.dumps({"status": "failed", "checks": [{"name": "quality", "status": "failed"}]}))
            self.assertEqual(main(["ci-eval-gate", "--target", str(root), "--run", "run-ci-eval-001"]), 1)
            gate = json.loads((run_dir / "ci_eval_gate.json").read_text())
            self.assertIn("Eval results status is failed", gate["reasons"])

            (run_dir / "eval_results.json").write_text(json.dumps({"status": "passed", "checks": [{"name": "quality", "status": "passed"}]}))
            self.assertEqual(main(["ci-eval-gate", "--target", str(root), "--run", "run-ci-eval-001"]), 0)
            gate = json.loads((run_dir / "ci_eval_gate.json").read_text())
            self.assertEqual(gate["status"], "passed")

    def test_review_gate_blocks_unresolved_blocking_or_major_findings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-review-gate-001")
            findings = {
                "findings": [
                    {"id": "F1", "severity": "blocking", "status": "open", "body": "Fix auth bypass"},
                    {"id": "F2", "severity": "minor", "status": "open", "body": "Rename local"},
                ]
            }
            (run_dir / "review_findings.json").write_text(json.dumps(findings))

            self.assertEqual(main(["review-gate", "--target", str(root), "--run", "run-review-gate-001"]), 1)
            gate = json.loads((run_dir / "review_gate.json").read_text())
            self.assertEqual(gate["status"], "blocked")
            self.assertEqual(gate["unresolved_blocking_findings"], ["F1"])

            findings["findings"][0]["status"] = "resolved"
            (run_dir / "review_findings.json").write_text(json.dumps(findings))
            self.assertEqual(main(["review-gate", "--target", str(root), "--run", "run-review-gate-001"]), 0)
            gate = json.loads((run_dir / "review_gate.json").read_text())
            self.assertEqual(gate["status"], "passed")
            self.assertEqual(gate["open_nonblocking_findings"], ["F2"])

    def test_writer_lock_and_owner_transfer_enforce_single_current_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            branch = "ai/issue-123/backend-implementer/run-owner-001"
            owner_dir = self._make_manual_writer_run(root, "run-owner-001", branch=branch)
            repair_dir = self._make_manual_writer_run(root, "run-repair-001", branch=branch, agent_id="ci-repair-agent")

            self.assertEqual(main(["writer-lock", "--target", str(root), "--run", "run-owner-001"]), 0)
            owner_lock = json.loads((owner_dir / "writer_lock.json").read_text())
            self.assertEqual(owner_lock["owner_run_id"], "run-owner-001")
            self.assertEqual(main(["writer-lock", "--target", str(root), "--run", "run-repair-001"]), 1)

            self.assertEqual(
                main(
                    [
                        "writer-transfer",
                        "--target",
                        str(root),
                        "--from-run",
                        "run-owner-001",
                        "--to-run",
                        "run-repair-001",
                        "--reason",
                        "CI repair owner transfer",
                    ]
                ),
                0,
            )
            lock = json.loads((repair_dir / "writer_lock.json").read_text())
            self.assertEqual(lock["owner_run_id"], "run-repair-001")
            self.assertEqual(len(lock["history"]), 2)
            self.assertEqual(main(["writer-lock", "--target", str(root), "--run", "run-owner-001"]), 1)
            self.assertEqual(main(["writer-lock", "--target", str(root), "--run", "run-repair-001"]), 0)

    def test_risk_approval_gate_requires_autonomous_approval_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-risk-approval-001", risk_level="high")

            self.assertEqual(main(["risk-approval-gate", "--target", str(root), "--run", "run-risk-approval-001"]), 1)
            gate = json.loads((run_dir / "risk_approval_gate.json").read_text())
            self.assertEqual(gate["status"], "blocked")
            self.assertIn("risk approval is missing", gate["reasons"])

            (run_dir / "risk_approval.json").write_text(
                json.dumps(
                    {
                        "status": "rejected",
                        "approver_agent_id": "risk-approval-agent",
                        "source_run_id": "run-risk-approval-001",
                        "risk_level": "high",
                        "rationale": "Policy risk remains unresolved.",
                    }
                )
            )
            self.assertEqual(main(["risk-approval-gate", "--target", str(root), "--run", "run-risk-approval-001"]), 1)
            gate = json.loads((run_dir / "risk_approval_gate.json").read_text())
            self.assertIn("risk approval status is rejected", gate["reasons"])

            (run_dir / "risk_approval.json").write_text(
                json.dumps(
                    {
                        "status": "approved",
                        "approver_agent_id": "risk-approval-agent",
                        "source_run_id": "run-risk-approval-001",
                        "risk_level": "high",
                        "rationale": "Autonomous policy review passed.",
                    }
                )
            )
            self.assertEqual(main(["risk-approval-gate", "--target", str(root), "--run", "run-risk-approval-001"]), 0)
            gate = json.loads((run_dir / "risk_approval_gate.json").read_text())
            self.assertEqual(gate["status"], "passed")
            self.assertEqual(gate["approver_agent_id"], "risk-approval-agent")

    def test_merge_gate_requires_lifecycle_gates_lock_and_agent_risk_approval_for_high_risk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-merge-001", risk_level="high")
            (run_dir / "pr_gate.json").write_text(json.dumps({"status": "passed"}))
            (run_dir / "push_execution.json").write_text(json.dumps({"status": "succeeded"}))
            (run_dir / "ci_eval_gate.json").write_text(json.dumps({"status": "passed"}))
            (run_dir / "review_gate.json").write_text(json.dumps({"status": "passed"}))

            self.assertEqual(main(["merge-gate", "--target", str(root), "--run", "run-merge-001"]), 1)
            gate = json.loads((run_dir / "merge_gate.json").read_text())
            self.assertIn("writer lock is missing", gate["reasons"])

            self.assertEqual(main(["writer-lock", "--target", str(root), "--run", "run-merge-001"]), 0)
            self.assertEqual(main(["merge-gate", "--target", str(root), "--run", "run-merge-001"]), 1)
            gate = json.loads((run_dir / "merge_gate.json").read_text())
            self.assertIn("risk approval gate is missing", gate["reasons"])

            (run_dir / "risk_approval.json").write_text(
                json.dumps(
                    {
                        "status": "approved",
                        "approver_agent_id": "risk-approval-agent",
                        "source_run_id": "run-merge-001",
                        "risk_level": "high",
                        "rationale": "Autonomous policy review passed.",
                    }
                )
            )
            self.assertEqual(main(["risk-approval-gate", "--target", str(root), "--run", "run-merge-001"]), 0)
            self.assertEqual(main(["merge-gate", "--target", str(root), "--run", "run-merge-001"]), 0)
            gate = json.loads((run_dir / "merge_gate.json").read_text())
            self.assertEqual(gate["status"], "passed")
            self.assertTrue(gate["merge_ready"])

    def test_skill_evolution_plan_recommends_skill_curator_pr_for_repeated_patterns(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-skill-source-001")
            findings = {
                "findings": [
                    {"id": "F1", "severity": "major", "status": "resolved", "pattern": "missing-validation", "body": "No validation evidence"},
                    {"id": "F2", "severity": "major", "status": "resolved", "pattern": "missing-validation", "body": "Validation evidence stale"},
                ]
            }
            (run_dir / "review_findings.json").write_text(json.dumps(findings))

            self.assertEqual(
                main(
                    [
                        "skill-evolution-plan",
                        "--target",
                        str(root),
                        "--source-run",
                        "run-skill-source-001",
                        "--run-id",
                        "run-skill-evolution-001",
                    ]
                ),
                0,
            )
            plan = json.loads((run_dir / "skill_evolution_plan.json").read_text())
            self.assertEqual(plan["status"], "recommended")
            self.assertEqual(plan["patterns"][0]["pattern"], "missing-validation")
            schedule_plan = json.loads((run_dir / "skill_evolution_schedule_plan.json").read_text())
            self.assertEqual(schedule_plan["run_plan"][0]["agent_id"], "skill-curator")
            self.assertEqual(schedule_plan["run_plan"][0]["expected_output"], "skill_update_pr")

    def test_lifecycle_run_chains_post_publication_gates_to_merge_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-lifecycle-001", risk_level="high")
            (run_dir / "pr_gate.json").write_text(json.dumps({"status": "passed"}))
            (run_dir / "push_execution.json").write_text(json.dumps({"status": "succeeded"}))
            (run_dir / "ci_results.json").write_text(json.dumps({"status": "passed", "checks": [{"name": "ci", "status": "passed"}]}))
            (run_dir / "eval_results.json").write_text(json.dumps({"status": "passed", "checks": [{"name": "eval", "status": "passed"}]}))
            (run_dir / "review_findings.json").write_text(json.dumps({"findings": []}))
            (run_dir / "risk_approval.json").write_text(
                json.dumps(
                    {
                        "status": "approved",
                        "approver_agent_id": "risk-approval-agent",
                        "source_run_id": "run-lifecycle-001",
                        "risk_level": "high",
                        "rationale": "Autonomous policy review passed.",
                    }
                )
            )

            self.assertEqual(
                main(
                    [
                        "lifecycle-run",
                        "--target",
                        str(root),
                        "--run",
                        "run-lifecycle-001",
                        "--skill-run-id",
                        "run-lifecycle-skill-001",
                    ]
                ),
                0,
            )

            lifecycle = json.loads((run_dir / "lifecycle_run.json").read_text())
            self.assertEqual(lifecycle["status"], "merge_ready")
            self.assertTrue(lifecycle["merge_ready"])
            self.assertEqual(
                [stage["name"] for stage in lifecycle["stages"]],
                [
                    "writer_lock",
                    "ci_eval_gate",
                    "review_gate",
                    "risk_approval_gate",
                    "merge_gate",
                    "skill_evolution_plan",
                ],
            )
            self.assertEqual(json.loads((run_dir / "merge_gate.json").read_text())["status"], "passed")
            self.assertEqual(json.loads((run_dir / "skill_evolution_plan.json").read_text())["status"], "not_recommended")
            self.assertIn("lifecycle_run_finished", (run_dir / "trace.jsonl").read_text())

    def test_lifecycle_run_blocks_merge_but_still_recommends_skill_evolution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-lifecycle-blocked-001", risk_level="medium")
            (run_dir / "pr_gate.json").write_text(json.dumps({"status": "passed"}))
            (run_dir / "push_execution.json").write_text(json.dumps({"status": "succeeded"}))
            (run_dir / "ci_results.json").write_text(json.dumps({"status": "passed", "checks": [{"name": "ci", "status": "passed"}]}))
            (run_dir / "eval_results.json").write_text(json.dumps({"status": "passed", "checks": [{"name": "eval", "status": "passed"}]}))
            (run_dir / "review_findings.json").write_text(
                json.dumps(
                    {
                        "findings": [
                            {
                                "id": "F1",
                                "severity": "blocking",
                                "status": "open",
                                "pattern": "missing-validation",
                                "body": "Validation evidence missing.",
                            },
                            {
                                "id": "F2",
                                "severity": "major",
                                "status": "open",
                                "pattern": "missing-validation",
                                "body": "Validation evidence is stale.",
                            },
                        ]
                    }
                )
            )

            self.assertEqual(
                main(["lifecycle-run", "--target", str(root), "--run", "run-lifecycle-blocked-001"]),
                1,
            )

            lifecycle = json.loads((run_dir / "lifecycle_run.json").read_text())
            self.assertEqual(lifecycle["status"], "blocked")
            self.assertFalse(lifecycle["merge_ready"])
            self.assertEqual(json.loads((run_dir / "review_gate.json").read_text())["status"], "blocked")
            self.assertEqual(json.loads((run_dir / "risk_approval_gate.json").read_text())["status"], "not_required")
            self.assertEqual(json.loads((run_dir / "merge_gate.json").read_text())["status"], "blocked")
            self.assertEqual(json.loads((run_dir / "skill_evolution_plan.json").read_text())["status"], "recommended")
            schedule_plan = json.loads((run_dir / "skill_evolution_schedule_plan.json").read_text())
            self.assertEqual(schedule_plan["run_plan"][0]["agent_id"], "skill-curator")

    def test_diff_gate_records_worktree_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            self._init_git_repo(root)
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
                        "run-diff-gate-001",
                    ]
                ),
                0,
            )
            run_dir = root / ".ai" / "runs" / "run-diff-gate-001"
            worktree = root / ".worktrees" / "run-diff-gate-001-backend-implementer"
            (worktree / "AGENTS.md").write_text((worktree / "AGENTS.md").read_text() + "\nDiff gate change.\n")

            self.assertEqual(main(["diff-gate", "--target", str(root), "--run", "run-diff-gate-001"]), 0)

            gate = json.loads((run_dir / "diff_gate.json").read_text())
            self.assertEqual(gate["status"], "passed")
            self.assertIn("AGENTS.md", gate["changed_files"])
            self.assertTrue((run_dir / "diff.patch").exists())

    def test_diff_gate_includes_untracked_file_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            self._init_git_repo(root)
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
                    "run-diff-untracked-001",
                ]
            )
            run_dir = root / ".ai" / "runs" / "run-diff-untracked-001"
            worktree = root / ".worktrees" / "run-diff-untracked-001-backend-implementer"
            (worktree / "new-file.txt").write_text("new evidence\n")

            self.assertEqual(main(["diff-gate", "--target", str(root), "--run", "run-diff-untracked-001"]), 0)

            gate = json.loads((run_dir / "diff_gate.json").read_text())
            patch = (run_dir / "diff.patch").read_text()
            self.assertIn("new-file.txt", gate["changed_files"])
            self.assertIn("new-file.txt", patch)
            self.assertIn("new evidence", patch)

    def test_commit_command_requires_passed_diff_gate_and_commits_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            self._init_git_repo(root)
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
                    "run-commit-001",
                ]
            )
            run_dir = root / ".ai" / "runs" / "run-commit-001"
            worktree = root / ".worktrees" / "run-commit-001-backend-implementer"
            (worktree / "AGENTS.md").write_text((worktree / "AGENTS.md").read_text() + "\nCommit gate change.\n")
            self.assertEqual(main(["commit-command", "--target", str(root), "--run", "run-commit-001"]), 1)

            self.assertEqual(main(["diff-gate", "--target", str(root), "--run", "run-commit-001"]), 0)
            self.assertEqual(main(["commit-command", "--target", str(root), "--run", "run-commit-001"]), 0)
            command = json.loads((run_dir / "commit_command.json").read_text())
            self.assertEqual(command["message"], "[AI:backend-implementer] Add API")
            self.assertEqual(command["steps"][0]["argv"][:2], ["git", "add"])
            self.assertEqual(command["steps"][1]["argv"][0], "git")

            self.assertEqual(main(["run-commit-command", "--target", str(root), "--run", "run-commit-001", "--timeout", "5"]), 0)
            execution = json.loads((run_dir / "commit_execution.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            self.assertTrue(execution["commit_sha"])
            self.assertEqual(json.loads((run_dir / "post_commit_diff_gate.json").read_text())["status"], "clean")

    def test_run_commit_command_rejects_mutated_steps(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            self._init_git_repo(root)
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
                    "run-commit-policy-001",
                ]
            )
            run_dir = root / ".ai" / "runs" / "run-commit-policy-001"
            worktree = root / ".worktrees" / "run-commit-policy-001-backend-implementer"
            (worktree / "AGENTS.md").write_text((worktree / "AGENTS.md").read_text() + "\nCommit policy change.\n")
            self.assertEqual(main(["diff-gate", "--target", str(root), "--run", "run-commit-policy-001"]), 0)
            self.assertEqual(main(["commit-command", "--target", str(root), "--run", "run-commit-policy-001"]), 0)
            command = json.loads((run_dir / "commit_command.json").read_text())
            command["steps"][1]["argv"] = ["git", "status"]
            (run_dir / "commit_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-commit-command", "--target", str(root), "--run", "run-commit-policy-001", "--timeout", "5"]), 1)
            self.assertFalse((run_dir / "commit_execution.json").exists())

    def test_push_command_requires_successful_commit_and_captures_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-push-001")
            run = json.loads((run_dir / "run.json").read_text())
            run.update(
                {
                    "mode": "writer",
                    "branch": "ai/issue-123/backend-implementer/run-push-001",
                    "worktree": "workspace",
                    "task_summary": "Add API",
                }
            )
            (run_dir / "run.json").write_text(json.dumps(run))
            (root / "workspace").mkdir()
            (run_dir / "commit_execution.json").write_text(
                json.dumps({"status": "succeeded", "commit_sha": "abc123"})
            )

            self.assertEqual(main(["push-command", "--target", str(root), "--run", "run-push-001", "--remote", "origin"]), 0)
            command = json.loads((run_dir / "push_command.json").read_text())
            self.assertEqual(command["argv"], ["git", "push", "origin", "ai/issue-123/backend-implementer/run-push-001"])
            self.assertEqual(main(["run-push-command", "--target", str(root), "--run", "run-push-001", "--timeout", "5"]), 1)
            execution = json.loads((run_dir / "push_execution.json").read_text())
            self.assertEqual(execution["status"], "failed")
            self.assertNotEqual(execution["exit_code"], 0)

    def test_run_push_command_rejects_mutated_argv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-push-policy-001")
            run = json.loads((run_dir / "run.json").read_text())
            run.update(
                {
                    "mode": "writer",
                    "branch": "ai/issue-123/backend-implementer/run-push-policy-001",
                    "worktree": "workspace",
                    "task_summary": "Add API",
                }
            )
            (run_dir / "run.json").write_text(json.dumps(run))
            (root / "workspace").mkdir()
            (run_dir / "commit_execution.json").write_text(json.dumps({"status": "succeeded", "commit_sha": "abc123"}))
            self.assertEqual(main(["push-command", "--target", str(root), "--run", "run-push-policy-001"]), 0)
            command = json.loads((run_dir / "push_command.json").read_text())
            command["argv"] = [sys.executable, "-c", "print('mutated push')"]
            (run_dir / "push_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-push-command", "--target", str(root), "--run", "run-push-policy-001", "--timeout", "5"]), 1)
            self.assertFalse((run_dir / "push_execution.json").exists())

    def test_integration_command_merges_child_writer_branches_and_enables_push_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._prepare_integration_fixture(root)

            self.assertEqual(main(["run-integration-command", "--target", str(root), "--run", "run-integration-001", "--timeout", "10"]), 0)

            execution = json.loads((run_dir / "integration_execution.json").read_text())
            commit_execution = json.loads((run_dir / "commit_execution.json").read_text())
            worktree = root / ".worktrees" / "run-integration-001-integration-agent"
            self.assertEqual(execution["status"], "succeeded")
            self.assertTrue(commit_execution["commit_sha"])
            self.assertTrue((worktree / "backend.txt").exists())
            self.assertTrue((worktree / "frontend.txt").exists())
            self.assertEqual(main(["validation-gate", "--target", str(root), "--run", "run-integration-001", "--mode", "skip"]), 0)
            self.assertEqual(main(["pr-gate", "--target", str(root), "--run", "run-integration-001"]), 0)
            self.assertEqual(main(["push-command", "--target", str(root), "--run", "run-integration-001"]), 0)

    def test_run_integration_command_rejects_mutated_steps(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._prepare_integration_fixture(
                root,
                schedule_run_id="run-schedule-integration-policy",
                integration_run_id="run-integration-policy-001",
            )
            command = json.loads((run_dir / "integration_command.json").read_text())
            command["steps"][0]["argv"] = ["git", "status"]
            (run_dir / "integration_command.json").write_text(json.dumps(command))

            self.assertEqual(
                main(["run-integration-command", "--target", str(root), "--run", "run-integration-policy-001", "--timeout", "10"]),
                1,
            )
            self.assertFalse((run_dir / "integration_execution.json").exists())

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

    def test_dispatch_run_requires_push_before_preparing_pr_command(self):
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
                        "run-dispatch-pr-001",
                        "--validation-mode",
                        "skip",
                        "--timeout",
                        "5",
                        "--prepare-pr-command",
                        "--pr-base",
                        "main",
                        "--draft-pr",
                    ]
                ),
                1,
            )

            schedule_dir = root / ".ai" / "runs" / "run-dispatch-pr-001"
            child_dir = root / ".ai" / "runs" / "run-dispatch-pr-001-T3-backend-implementer"
            summary = json.loads((schedule_dir / "dispatch_run.json").read_text())
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["children"][0]["status"], "failed")
            self.assertIn("push execution is missing", summary["children"][0]["error"])
            self.assertFalse((child_dir / "pr_command.json").exists())

    def test_dispatch_run_blocks_dependents_when_dependency_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self._install_failing_test_connector(root)
            self._init_git_repo(root)
            plan = root / "schedule_plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T1",
                                "mode": "writer",
                                "depends_on": [],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                                "success_criteria": ["Fails intentionally"],
                            },
                            {
                                "agent_id": "frontend-implementer",
                                "task_id": "T2",
                                "mode": "writer",
                                "depends_on": ["T1"],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                                "success_criteria": ["Must not run"],
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
                        "dispatch-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--plan",
                        str(plan),
                        "--run-id",
                        "run-dispatch-deps-001",
                        "--validation-mode",
                        "skip",
                        "--timeout",
                        "5",
                    ]
                ),
                1,
            )

            schedule_dir = root / ".ai" / "runs" / "run-dispatch-deps-001"
            summary = json.loads((schedule_dir / "dispatch_run.json").read_text())
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["children"][0]["status"], "failed")
            self.assertEqual(summary["children"][1]["status"], "blocked")
            blocked_dir = root / ".ai" / "runs" / "run-dispatch-deps-001-T2-frontend-implementer"
            self.assertFalse((blocked_dir / "connector_command.json").exists())

    def test_dispatch_run_can_commit_push_then_prepare_pr_command(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = root / "origin.git"
            main(["init", "--target", str(root)])
            self._install_writing_test_connector(root)
            self._init_git_repo(root)
            self._init_bare_remote(root, remote)
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
                                "success_criteria": ["Connector writes a change"],
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
                        "run-dispatch-publish-001",
                        "--validation-mode",
                        "skip",
                        "--timeout",
                        "5",
                        "--commit-and-push",
                        "--push-remote",
                        "origin",
                        "--prepare-pr-command",
                        "--pr-base",
                        "main",
                        "--draft-pr",
                    ]
                ),
                0,
            )

            schedule_dir = root / ".ai" / "runs" / "run-dispatch-publish-001"
            child_run_id = "run-dispatch-publish-001-T3-backend-implementer"
            child_dir = root / ".ai" / "runs" / child_run_id
            summary = json.loads((schedule_dir / "dispatch_run.json").read_text())
            child = summary["children"][0]
            self.assertEqual(child["diff_gate_status"], "passed")
            self.assertEqual(child["commit_status"], "succeeded")
            self.assertEqual(child["push_status"], "succeeded")
            self.assertEqual(child["pr_command"], f".ai/runs/{child_run_id}/pr_command.json")
            self.assertEqual(json.loads((child_dir / "push_execution.json").read_text())["status"], "succeeded")
            self.assertTrue((child_dir / "pr_command.json").exists())
            self.assertEqual(self._remote_branch_sha(remote, "ai/issue-123/backend-implementer/" + child_run_id), child["commit_sha"])

    def test_automation_run_writes_top_level_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self._install_test_connector(root)
            self._init_git_repo(root)
            plan = root / "automation_schedule_plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T-auto",
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
                        "automation-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--plan",
                        str(plan),
                        "--run-id",
                        "run-automation-001",
                        "--validation-mode",
                        "skip",
                    ]
                ),
                0,
            )

            schedule_dir = root / ".ai" / "runs" / "run-automation-001"
            child_dir = root / ".ai" / "runs" / "run-automation-001-T-auto-backend-implementer"
            summary = json.loads((schedule_dir / "automation_run.json").read_text())
            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(summary["dispatch_status"], "succeeded")
            self.assertTrue((child_dir / "skill_sync.json").exists())
            self.assertTrue((child_dir / "connector_execution.json").exists())
            self.assertTrue((child_dir / "pr_gate.json").exists())

    def test_automation_run_skips_publication_phases_for_read_only_children(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self._install_test_connector(root)
            self._bind_agent_to_test_connector(root, "pr-reviewer")
            plan = root / "automation_readonly_schedule_plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "pr-reviewer",
                                "task_id": "T-review",
                                "mode": "read_only",
                                "depends_on": [],
                                "expected_output": "review_findings",
                                "requires_pr": False,
                                "risk_level": "low",
                                "success_criteria": ["Review completes"],
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
                        "automation-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--plan",
                        str(plan),
                        "--run-id",
                        "run-automation-readonly-001",
                        "--no-worktree",
                        "--validation-mode",
                        "skip",
                        "--github-checks",
                        "--lifecycle",
                    ]
                ),
                0,
            )

            schedule_dir = root / ".ai" / "runs" / "run-automation-readonly-001"
            child_dir = root / ".ai" / "runs" / "run-automation-readonly-001-T-review-pr-reviewer"
            summary = json.loads((schedule_dir / "automation_run.json").read_text())
            child = summary["children"][0]
            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(child["status"], "succeeded")
            self.assertEqual(child["publication_status"], "skipped")
            self.assertFalse((child_dir / "github_checks_command.json").exists())
            self.assertFalse((child_dir / "lifecycle_run.json").exists())

    def test_dispatch_plan_rejects_unknown_dependency_and_cycles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            unknown = root / "unknown_dep.json"
            unknown.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T2",
                                "mode": "writer",
                                "depends_on": ["T1"],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                            }
                        ],
                        "blocked": [],
                        "risk_notes": [],
                    }
                )
            )
            self.assertEqual(
                main(["dispatch-plan", "--target", str(root), "--issue", "123", "--plan", str(unknown), "--run-id", "run-schedule-unknown", "--no-worktree"]),
                1,
            )

            cycle = root / "cycle_dep.json"
            cycle.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T1",
                                "mode": "writer",
                                "depends_on": ["T2"],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                            },
                            {
                                "agent_id": "frontend-implementer",
                                "task_id": "T2",
                                "mode": "writer",
                                "depends_on": ["T1"],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                            },
                        ],
                        "blocked": [],
                        "risk_notes": [],
                    }
                )
            )
            self.assertEqual(
                main(["dispatch-plan", "--target", str(root), "--issue", "123", "--plan", str(cycle), "--run-id", "run-schedule-cycle", "--no-worktree"]),
                1,
            )

    def test_dispatch_plan_rejects_unsafe_schedule_run_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = root / "schedule_plan.json"
            main(["init", "--target", str(root)])
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [],
                        "blocked": [],
                        "risk_notes": [],
                    }
                )
            )
            self.assertEqual(
                main(["dispatch-plan", "--target", str(root), "--issue", "123", "--plan", str(plan), "--run-id", "../escape", "--no-worktree"]),
                1,
            )
            self.assertFalse((root / ".ai" / "escape").exists())

    def test_dispatch_plan_failure_removes_created_worktrees_and_branches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = root / "schedule_plan.json"
            main(["init", "--target", str(root)])
            self._init_git_repo(root)
            second_branch = "ai/issue-123/backend-implementer/run-schedule-leak-T2-backend-implementer"
            self._create_branch(root, second_branch)
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T1",
                                "mode": "writer",
                                "depends_on": [],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                            },
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T2",
                                "mode": "writer",
                                "depends_on": [],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "medium",
                            },
                        ],
                        "blocked": [],
                        "risk_notes": [],
                    }
                )
            )

            self.assertEqual(
                main(["dispatch-plan", "--target", str(root), "--issue", "123", "--plan", str(plan), "--run-id", "run-schedule-leak"]),
                1,
            )

            first_branch = "ai/issue-123/backend-implementer/run-schedule-leak-T1-backend-implementer"
            self.assertFalse((root / ".worktrees" / "run-schedule-leak-T1-backend-implementer-backend-implementer").exists())
            self.assertFalse(self._branch_exists(root, first_branch))
            self.assertTrue(self._branch_exists(root, second_branch))

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
                                "depends_on": [],
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

    def test_dispatch_plan_can_target_risk_approval_agent_without_runtime_visibility(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = root / "risk_approval_schedule_plan.json"
            main(["init", "--target", str(root)])
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "risk-approval-agent",
                                "task_id": "T-risk",
                                "mode": "read_only",
                                "depends_on": [],
                                "expected_output": "risk_approval",
                                "requires_pr": False,
                                "risk_level": "high",
                                "success_criteria": ["High-risk approval decision is structured"],
                            }
                        ],
                        "blocked": [],
                        "risk_notes": ["High-risk merge must be approved by risk-approval-agent."],
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
                        "run-risk-schedule-001",
                        "--no-worktree",
                    ]
                ),
                0,
            )
            schedule_dir = root / ".ai" / "runs" / "run-risk-schedule-001"
            entry = json.loads((schedule_dir / "dispatch_log.jsonl").read_text().splitlines()[0])
            self.assertEqual(entry["agent_id"], "risk-approval-agent")
            self.assertEqual(entry["connector"], "claude-code-cli")
            self.assertEqual(entry["connector_profile"], "risk-approval-readonly")

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

    def _make_manual_writer_run(
        self,
        root: Path,
        run_id: str,
        branch: str | None = None,
        agent_id: str = "backend-implementer",
        risk_level: str = "medium",
    ) -> Path:
        run_dir = self._make_manual_run(root, run_id)
        run = json.loads((run_dir / "run.json").read_text())
        run.update(
            {
                "agent_id": agent_id,
                "mode": "writer",
                "branch": branch or f"ai/issue-123/{agent_id}/{run_id}",
                "risk_level": risk_level,
                "task_summary": "Lifecycle gate test",
                "issue_id": "issue-123",
            }
        )
        (run_dir / "run.json").write_text(json.dumps(run))
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

    def _bind_agent_to_test_connector(self, root: Path, agent_id: str) -> None:
        assignments = root / ".ai" / "private" / "assignments.yml"
        lines = assignments.read_text().splitlines()
        for index, line in enumerate(lines):
            if line == f"  {agent_id}:":
                lines[index + 1] = "    connector: test-cli"
                lines[index + 2] = "    profile: test-profile"
                break
        assignments.write_text("\n".join(lines) + "\n")

    def _install_writing_test_connector(self, root: Path) -> None:
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
                        f"{sys.executable} -c \"from pathlib import Path; "
                        "p=Path('AGENTS.md'); "
                        "p.write_text(p.read_text() + '\\nConnector change.\\n'); "
                        "print('{\\\"event\\\":\\\"agent_done\\\"}')\""
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

    def _install_failing_test_connector(self, root: Path) -> None:
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
                    f"  test-profile: {sys.executable} -c \"raise SystemExit(7)\"",
                    "",
                ]
            )
        )
        assignments = root / ".ai" / "private" / "assignments.yml"
        text = assignments.read_text()
        text = text.replace("connector: codex-cli", "connector: test-cli")
        text = text.replace("connector: claude-code-cli", "connector: test-cli")
        text = text.replace("profile: writer-workspace", "profile: test-profile")
        text = text.replace("profile: reviewer-readonly", "profile: test-profile")
        text = text.replace("profile: scheduler-readonly", "profile: test-profile")
        text = text.replace("profile: readonly-json", "profile: test-profile")
        text = text.replace("profile: planner", "profile: test-profile")
        text = text.replace("profile: qa-workspace", "profile: test-profile")
        text = text.replace("profile: skill-writer", "profile: test-profile")
        text = text.replace("profile: release-readonly", "profile: test-profile")
        text = text.replace("profile: risk-approval-readonly", "profile: test-profile")
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

    def _init_bare_remote(self, root: Path, remote: Path) -> None:
        import subprocess

        subprocess.run(["git", "init", "--bare", str(remote)], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _create_branch(self, root: Path, branch: str) -> None:
        import subprocess

        subprocess.run(["git", "branch", branch], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _branch_exists(self, root: Path, branch: str) -> bool:
        import subprocess

        result = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=root)
        return result.returncode == 0

    def _remote_branch_sha(self, remote: Path, branch: str) -> str:
        import subprocess

        result = subprocess.run(
            ["git", "--git-dir", str(remote), "rev-parse", branch],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def _prepare_integration_fixture(
        self,
        root: Path,
        schedule_run_id: str = "run-schedule-integration",
        integration_run_id: str = "run-integration-001",
    ) -> Path:
        plan = root / f"{schedule_run_id}.json"
        main(["init", "--target", str(root)])
        plan.write_text(
            json.dumps(
                {
                    "run_plan": [
                        {
                            "agent_id": "backend-implementer",
                            "task_id": "T-backend",
                            "mode": "writer",
                            "depends_on": [],
                            "expected_output": "branch_pr",
                            "requires_pr": True,
                            "risk_level": "medium",
                            "success_criteria": ["Backend branch is mergeable"],
                        },
                        {
                            "agent_id": "frontend-implementer",
                            "task_id": "T-frontend",
                            "mode": "writer",
                            "depends_on": [],
                            "expected_output": "branch_pr",
                            "requires_pr": True,
                            "risk_level": "medium",
                            "success_criteria": ["Frontend branch is mergeable"],
                        },
                    ],
                    "blocked": [],
                    "risk_notes": [],
                }
            )
        )
        self._init_git_repo(root)
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
                    schedule_run_id,
                    "--no-worktree",
                ]
            ),
            0,
        )
        schedule_dir = root / ".ai" / "runs" / schedule_run_id
        for index, line in enumerate((schedule_dir / "dispatch_log.jsonl").read_text().splitlines(), start=1):
            entry = json.loads(line)
            child_dir = root / ".ai" / "runs" / entry["run_id"]
            child_run = json.loads((child_dir / "run.json").read_text())
            filename = "backend.txt" if entry["agent_id"] == "backend-implementer" else "frontend.txt"
            self._create_branch(root, child_run["branch"])
            self._commit_file_on_branch(root, child_run["branch"], filename, f"{entry['agent_id']} integration content\n")
            (child_dir / "pr_execution.json").write_text(
                json.dumps(
                    {
                        "status": "succeeded",
                        "number": index,
                        "url": f"https://github.com/acme/repo/pull/{index}",
                    }
                )
            )

        self.assertEqual(
            main(
                [
                    "integration-plan",
                    "--target",
                    str(root),
                    "--issue",
                    "123",
                    "--schedule-run",
                    schedule_run_id,
                    "--run-id",
                    integration_run_id,
                ]
            ),
            0,
        )
        self.assertEqual(main(["integration-command", "--target", str(root), "--run", integration_run_id]), 0)
        return root / ".ai" / "runs" / integration_run_id

    def _commit_file_on_branch(self, root: Path, branch: str, relpath: str, content: str) -> None:
        import subprocess

        current = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
        subprocess.run(["git", "checkout", branch], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (root / relpath).write_text(content)
        subprocess.run(["git", "add", relpath], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", f"Add {relpath}"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(["git", "checkout", current], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

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
