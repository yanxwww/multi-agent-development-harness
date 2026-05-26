import hashlib
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
            self.assertTrue((root / ".ai" / "schemas" / "review_findings.schema.json").exists())
            self.assertTrue((root / ".ai" / "rules" / "validation-policy.yml").exists())
            self.assertTrue((root / ".ai" / "rules" / "artifact-retention.yml").exists())
            self.assertTrue((root / ".ai" / "rules" / "local-daemon.yml").exists())
            self.assertTrue((root / ".ai" / "local-daemon" / "events" / ".gitkeep").exists())
            self.assertTrue((root / ".ai" / "local-daemon" / "leases" / ".gitkeep").exists())
            self.assertTrue((root / ".ai" / "local-daemon" / "polls" / ".gitkeep").exists())
            self.assertTrue((root / ".ai" / "local-daemon" / "dead-letter" / ".gitkeep").exists())
            launchd = root / ".ai" / "local-daemon" / "launchd" / "com.ai-harness.local-daemon.plist"
            self.assertTrue(launchd.exists())
            launchd_text = launchd.read_text()
            self.assertIn("--execute", launchd_text)
            self.assertIn("--status-sync", launchd_text)
            self.assertTrue((root / ".github" / "workflows" / "ai-harness-automation.yml").exists())
            workflow = (root / ".github" / "workflows" / "ai-harness-automation.yml").read_text()
            self.assertNotIn("github.event.inputs.execute", workflow)
            self.assertNotIn("$EXTRA_ARGS", workflow)
            self.assertNotIn("--execute", workflow)
            agent_result_schema = json.loads((root / ".ai" / "schemas" / "agent_result.schema.json").read_text())
            self.assertFalse(agent_result_schema["additionalProperties"])
            self.assertFalse(agent_result_schema["properties"]["evidence"]["additionalProperties"])
            claude_connector = (root / ".ai" / "connectors" / "claude-code-cli.yml").read_text()
            self.assertIn("{output_schema_json}", claude_connector)
            self.assertTrue((root / ".claude" / "settings.json").exists())
            gitignore = (root / ".gitignore").read_text()
            self.assertIn("CLAUDE.md", gitignore)
            self.assertIn(".agents/skills/*", gitignore)
            self.assertIn("!.agents/skills/.gitkeep", gitignore)
            self.assertIn(".claude/skills/*", gitignore)
            self.assertIn("!.claude/skills/.gitkeep", gitignore)
            self.assertIn(".ai/scheduler-workspaces/*", gitignore)
            self.assertIn(".ai/events/*", gitignore)
            self.assertIn(".ai/local-daemon/events/*", gitignore)
            self.assertIn(".ai/local-daemon/dead-letter/*", gitignore)
            self.assertIn(".ai/local-daemon/state.json", gitignore)
            self.assertIn(".ai/github_doctor.json", gitignore)
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

    def test_validate_rejects_read_only_connector_profile_with_write_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            connector = root / ".ai" / "connectors" / "claude-code-cli.yml"
            connector.write_text(connector.read_text().replace("tools: Read,Grep,Glob", "tools: Read,Edit,Grep,Glob", 1))

            self.assertEqual(main(["validate", "--target", str(root)]), 1)

    def test_validate_rejects_invalid_local_daemon_trigger_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            (root / ".ai" / "rules" / "local-daemon.yml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "label_actions:",
                        "  ai:auto: deploy",
                        "comment_actions:",
                        "  /ai run: run",
                        "",
                    ]
                )
            )

            self.assertEqual(main(["validate", "--target", str(root)]), 1)

    def test_validate_rejects_invalid_local_daemon_retry_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            (root / ".ai" / "rules" / "local-daemon.yml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "label_actions:",
                        "  ai:auto: run",
                        "comment_actions:",
                        "  /ai run: run",
                        "retry:",
                        "  max_attempts: 0",
                        "  backoff_seconds: 300",
                        "",
                    ]
                )
            )

            self.assertEqual(main(["validate", "--target", str(root)]), 1)

    def test_connector_contracts_command_writes_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])

            self.assertEqual(main(["connector-contracts", "--target", str(root)]), 0)

            report = json.loads((root / ".ai" / "connector_contracts.json").read_text())
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["connectors_checked"], ["claude-code-cli", "codex-cli"])

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
            prompt = (run_dir / "prompt.md").read_text()
            self.assertIn("Run ID: run-20260523-001", prompt)
            self.assertIn("Agent ID: backend-implementer", prompt)
            self.assertIn("Add API", prompt)
            self.assertIn('"acceptance": [', prompt)

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

    def test_create_run_uses_validation_policy_and_records_risk_level(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            (root / ".ai" / "rules" / "validation-policy.yml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "defaults:",
                        "  writer:",
                        "    - default writer validation",
                        "agents:",
                        "  backend-implementer:",
                        "    - backend policy validation",
                        "",
                    ]
                )
            )
            task.write_text(json.dumps({"summary": "High risk backend change", "risk_level": "high"}))

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
                        "run-policy-001",
                        "--no-worktree",
                    ]
                ),
                0,
            )

            run = json.loads((root / ".ai" / "runs" / "run-policy-001" / "run.json").read_text())
            self.assertEqual(run["risk_level"], "high")
            self.assertEqual(run["validation_commands"], ["backend policy validation"])

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
            self.assertEqual(command["prompt_file"], ".ai/runs/run-command-001/prompt.md")
            prompt = root / command["prompt_file"]
            self.assertEqual(command["prompt_sha256"], hashlib.sha256(prompt.read_bytes()).hexdigest())

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
            schema_arg = command["argv"][command["argv"].index("--json-schema") + 1]
            self.assertNotIn(".ai/schemas/", schema_arg)
            self.assertEqual(json.loads(schema_arg)["type"], "object")
            self.assertEqual(command["prompt_file"], ".ai/runs/run-command-002/prompt.md")
            prompt = root / command["prompt_file"]
            self.assertEqual(command["prompt_sha256"], hashlib.sha256(prompt.read_bytes()).hexdigest())

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

    def test_run_connector_extracts_runtime_session_for_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-exec-session-001")
            command = {
                "run_id": "run-exec-session-001",
                "agent_id": "backend-implementer",
                "connector": "codex-cli",
                "profile": "writer-workspace",
                "argv": [
                    sys.executable,
                    "-c",
                    (
                        "import json\n"
                        "print(json.dumps({'type':'thread.started','thread_id':'thread-resume-123'}))\n"
                        "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Need continuation'}}))\n"
                    ),
                ],
            }
            (run_dir / "connector_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-connector", "--target", str(root), "--run", "run-exec-session-001", "--timeout", "5"]), 0)

            execution = json.loads((run_dir / "connector_execution.json").read_text())
            self.assertEqual(execution["runtime_session"]["id"], "thread-resume-123")
            self.assertEqual(execution["runtime_session"]["kind"], "codex_thread")
            self.assertEqual(execution["runtime_session"]["resume_mode"], "cli_resume")
            self.assertEqual(execution["last_agent_message"], "Need continuation")

            claude_run_dir = self._make_manual_run(root, "run-exec-session-002")
            claude_command = {
                "run_id": "run-exec-session-002",
                "agent_id": "frontend-implementer",
                "connector": "claude-code-cli",
                "profile": "writer-workspace",
                "argv": [
                    sys.executable,
                    "-c",
                    (
                        "import json\n"
                        "print(json.dumps({'session_id':'claude-session-456','result':'Claude continuation needed'}))\n"
                    ),
                ],
            }
            (claude_run_dir / "connector_command.json").write_text(json.dumps(claude_command))

            self.assertEqual(main(["run-connector", "--target", str(root), "--run", "run-exec-session-002", "--timeout", "5"]), 0)

            claude_execution = json.loads((claude_run_dir / "connector_execution.json").read_text())
            self.assertEqual(claude_execution["runtime_session"]["id"], "claude-session-456")
            self.assertEqual(claude_execution["runtime_session"]["kind"], "claude_session")
            self.assertEqual(claude_execution["runtime_session"]["resume_mode"], "cli_resume")
            self.assertEqual(claude_execution["last_agent_message"], "Claude continuation needed")

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

    def test_run_connector_passes_prompt_file_to_stdin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-exec-005")
            prompt = run_dir / "prompt.md"
            prompt.write_text("PROMPT_SENTINEL\n")
            script = (
                "import json, sys\n"
                "data = sys.stdin.read()\n"
                "print(json.dumps({'event':'prompt_seen','has_sentinel':'PROMPT_SENTINEL' in data}))\n"
                "raise SystemExit(0 if 'PROMPT_SENTINEL' in data else 2)\n"
            )
            command = {
                "run_id": "run-exec-005",
                "agent_id": "backend-implementer",
                "connector": "test-connector",
                "profile": "test-profile",
                "prompt_file": ".ai/runs/run-exec-005/prompt.md",
                "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                "argv": [sys.executable, "-c", script],
            }
            (run_dir / "connector_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-connector", "--target", str(root), "--run", "run-exec-005", "--timeout", "5"]), 0)

            execution = json.loads((run_dir / "connector_execution.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(execution["stdin_file"], ".ai/runs/run-exec-005/prompt.md")
            events = (run_dir / "connector_events.jsonl").read_text().splitlines()
            self.assertTrue(json.loads(events[0])["has_sentinel"])

    def test_run_connector_rejects_prompt_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_run(root, "run-exec-006")
            prompt = run_dir / "prompt.md"
            prompt.write_text("original prompt\n")
            command = {
                "run_id": "run-exec-006",
                "agent_id": "backend-implementer",
                "connector": "test-connector",
                "profile": "test-profile",
                "prompt_file": ".ai/runs/run-exec-006/prompt.md",
                "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                "argv": [sys.executable, "-c", "print('should not run')"],
            }
            prompt.write_text("mutated prompt\n")
            (run_dir / "connector_command.json").write_text(json.dumps(command))

            self.assertEqual(main(["run-connector", "--target", str(root), "--run", "run-exec-006", "--timeout", "5"]), 1)
            self.assertFalse((run_dir / "connector_execution.json").exists())

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

    def test_run_merge_command_removes_worktree_before_delete_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task.json"
            main(["init", "--target", str(root)])
            self._init_git_repo(root)
            task.write_text(json.dumps({"summary": "Merge cleanup test"}))
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
                        "run-merge-delete-worktree-001",
                    ]
                ),
                0,
            )
            run_dir = root / ".ai" / "runs" / "run-merge-delete-worktree-001"
            run = json.loads((run_dir / "run.json").read_text())
            worktree = root / run["worktree"]
            fake_gh = root / "fake-gh"
            fake_gh.write_text("#!/bin/sh\ngit branch -D \"$3\"\necho merged \"$@\"\n")
            fake_gh.chmod(0o755)
            (run_dir / "merge_gate.json").write_text(json.dumps({"status": "passed", "merge_ready": True}))
            (run_dir / "pr_execution.json").write_text(json.dumps({"status": "succeeded", "url": "https://example.test/pull/1"}))

            self.assertEqual(
                main(
                    [
                        "merge-command",
                        "--target",
                        str(root),
                        "--run",
                        "run-merge-delete-worktree-001",
                        "--method",
                        "squash",
                        "--delete-branch",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(["run-merge-command", "--target", str(root), "--run", "run-merge-delete-worktree-001", "--timeout", "5"]),
                0,
            )

            execution = json.loads((run_dir / "merge_execution.json").read_text())
            cleanup = json.loads((run_dir / "merge_worktree_cleanup.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(cleanup["status"], "removed")
            self.assertFalse(worktree.exists())

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
            self.assertNotIn("--watch", command["argv"])
            self.assertIn("--watch", command["watch_argv"])

            self.assertEqual(main(["run-github-checks-command", "--target", str(root), "--run", "run-github-checks-001", "--timeout", "5"]), 0)
            execution = json.loads((run_dir / "github_checks_execution.json").read_text())
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(execution["watch_exit_code"], 0)
            self.assertTrue((run_dir / "github_checks_watch_stdout.log").exists())
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

    def test_run_github_checks_command_preserves_existing_eval_results_without_eval_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-github-checks-preserve-eval-001")
            fake_gh = root / "fake-gh"
            fake_gh.write_text(
                "#!/bin/sh\n"
                "printf '[{\"name\":\"unit\",\"bucket\":\"pass\",\"state\":\"SUCCESS\",\"workflow\":\"ci\"}]'\n"
            )
            fake_gh.chmod(0o755)
            existing_eval = {"status": "failed", "checks": [{"name": "quality", "status": "failed"}]}
            (run_dir / "eval_results.json").write_text(json.dumps(existing_eval))
            (run_dir / "pr_execution.json").write_text(json.dumps({"status": "succeeded", "number": 12}))
            self.assertEqual(
                main(
                    [
                        "github-checks-command",
                        "--target",
                        str(root),
                        "--run",
                        "run-github-checks-preserve-eval-001",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )

            self.assertEqual(
                main(["run-github-checks-command", "--target", str(root), "--run", "run-github-checks-preserve-eval-001", "--timeout", "5"]),
                0,
            )

            execution = json.loads((run_dir / "github_checks_execution.json").read_text())
            eval_results = json.loads((run_dir / "eval_results.json").read_text())
            self.assertEqual(execution["eval_status"], "failed")
            self.assertEqual(eval_results, existing_eval)

    def test_run_github_checks_command_marks_empty_successful_checks_as_pending_ci(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = self._make_manual_writer_run(root, "run-github-checks-empty-success-001")
            fake_gh = root / "fake-gh"
            fake_gh.write_text("#!/bin/sh\nprintf '[]'\n")
            fake_gh.chmod(0o755)
            (run_dir / "pr_execution.json").write_text(json.dumps({"status": "succeeded", "number": 13}))
            self.assertEqual(
                main(
                    [
                        "github-checks-command",
                        "--target",
                        str(root),
                        "--run",
                        "run-github-checks-empty-success-001",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )

            self.assertEqual(
                main(["run-github-checks-command", "--target", str(root), "--run", "run-github-checks-empty-success-001", "--timeout", "5"]),
                0,
            )

            execution = json.loads((run_dir / "github_checks_execution.json").read_text())
            ci = json.loads((run_dir / "ci_results.json").read_text())
            self.assertEqual(execution["ci_status"], "pending")
            self.assertEqual(ci["status"], "pending")
            self.assertEqual(ci["checks"][0]["status"], "pending")

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

    def test_dispatch_run_does_not_commit_runtime_skill_sync_artifacts(self):
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
                                "task_id": "T-skills",
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
                        "run-dispatch-skill-ignore-001",
                        "--validation-mode",
                        "skip",
                        "--timeout",
                        "5",
                        "--commit-and-push",
                        "--push-remote",
                        "origin",
                    ]
                ),
                0,
            )

            schedule_dir = root / ".ai" / "runs" / "run-dispatch-skill-ignore-001"
            child = json.loads((schedule_dir / "dispatch_run.json").read_text())["children"][0]
            child_run_id = "run-dispatch-skill-ignore-001-T-skills-backend-implementer"
            worktree = root / ".worktrees" / f"{child_run_id}-backend-implementer"
            self.assertTrue((worktree / ".agents" / "skills" / "backend-implementation" / "SKILL.md").exists())

            import subprocess

            result = subprocess.run(
                ["git", "show", "--name-only", "--pretty=format:", child["commit_sha"]],
                cwd=worktree,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            committed_paths = {line for line in result.stdout.splitlines() if line.strip()}
            self.assertIn("AGENTS.md", committed_paths)
            self.assertFalse(any(path.startswith(".agents/skills/") for path in committed_paths))
            self.assertFalse(any(path.startswith(".claude/skills/") for path in committed_paths))

    def test_scheduler_run_executes_scheduler_agent_and_writes_schedule_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "scheduler_task.json"
            main(["init", "--target", str(root)])
            self._install_multi_output_test_connector(root)
            self._bind_agent_to_test_connector(root, "scheduler-agent")
            task.write_text(json.dumps({"summary": "Plan a small backend task"}))

            self.assertEqual(
                main(
                    [
                        "scheduler-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--task",
                        str(task),
                        "--run-id",
                        "run-scheduler-001",
                        "--timeout",
                        "5",
                    ]
                ),
                0,
            )

            run_dir = root / ".ai" / "runs" / "run-scheduler-001"
            plan = json.loads((run_dir / "schedule_plan.json").read_text())
            run = json.loads((run_dir / "run.json").read_text())
            command = json.loads((run_dir / "connector_command.json").read_text())
            self.assertEqual(run["agent_id"], "scheduler-agent")
            self.assertEqual(run["mode"], "read_only")
            self.assertEqual(command["output_schema"], ".ai/schemas/schedule_plan.schema.json")
            self.assertEqual(plan["run_plan"][0]["agent_id"], "backend-implementer")
            self.assertNotIn("connector", json.dumps(plan))

    def test_scheduler_run_uses_sanitized_workspace_without_private_bindings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "scheduler_task.json"
            main(["init", "--target", str(root)])
            self._install_multi_output_test_connector(root)
            self._bind_agent_to_test_connector(root, "scheduler-agent")
            task.write_text(json.dumps({"summary": "Plan from sanitized context"}))

            self.assertEqual(
                main(
                    [
                        "scheduler-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--task",
                        str(task),
                        "--run-id",
                        "run-scheduler-sanitized-001",
                        "--timeout",
                        "5",
                    ]
                ),
                0,
            )

            run_dir = root / ".ai" / "runs" / "run-scheduler-sanitized-001"
            run = json.loads((run_dir / "run.json").read_text())
            command = json.loads((run_dir / "connector_command.json").read_text())
            workspace = root / command["workspace"]
            self.assertEqual(run["worktree"], ".ai/scheduler-workspaces/run-scheduler-sanitized-001")
            self.assertTrue((workspace / "AGENTS.md").exists())
            self.assertTrue((workspace / ".ai" / "agent-catalog.yml").exists())
            self.assertTrue((workspace / ".ai" / "agents" / "scheduler-agent.md").exists())
            self.assertFalse((workspace / ".ai" / "private").exists())
            self.assertFalse((workspace / ".ai" / "private" / "assignments.yml").exists())

    def test_automation_run_can_start_from_scheduler_task(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "scheduler_task.json"
            main(["init", "--target", str(root)])
            self._install_multi_output_test_connector(root)
            self._bind_agent_to_test_connector(root, "scheduler-agent")
            self._bind_agent_to_test_connector(root, "backend-implementer")
            self._init_git_repo(root)
            task.write_text(json.dumps({"summary": "Plan and implement a small backend task"}))

            self.assertEqual(
                main(
                    [
                        "automation-run",
                        "--target",
                        str(root),
                        "--issue",
                        "123",
                        "--scheduler-task",
                        str(task),
                        "--run-id",
                        "run-automation-scheduled-001",
                        "--validation-mode",
                        "skip",
                        "--timeout",
                        "5",
                    ]
                ),
                0,
            )

            scheduler_dir = root / ".ai" / "runs" / "run-automation-scheduled-001-scheduler"
            schedule_dir = root / ".ai" / "runs" / "run-automation-scheduled-001"
            child_dir = root / ".ai" / "runs" / "run-automation-scheduled-001-T-auto-backend-implementer"
            summary = json.loads((schedule_dir / "automation_run.json").read_text())
            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(summary["scheduler_run"]["run_id"], "run-automation-scheduled-001-scheduler")
            self.assertTrue((scheduler_dir / "schedule_plan.json").exists())
            self.assertTrue((child_dir / "connector_execution.json").exists())

    def test_automation_run_can_execute_review_risk_and_repair_followups(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self._install_multi_output_test_connector(root)
            self._bind_agent_to_test_connector(root, "backend-implementer")
            self._bind_agent_to_test_connector(root, "pr-reviewer")
            self._bind_agent_to_test_connector(root, "risk-approval-agent")
            self._init_git_repo(root)
            plan = root / "automation_followup_plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T-followup",
                                "mode": "writer",
                                "depends_on": [],
                                "expected_output": "branch_pr",
                                "requires_pr": True,
                                "risk_level": "high",
                                "success_criteria": ["Connector succeeds"],
                            }
                        ],
                        "blocked": [],
                        "risk_notes": ["High risk must be approved by the risk approval agent."],
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
                        "run-automation-followup-001",
                        "--validation-mode",
                        "skip",
                        "--timeout",
                        "5",
                        "--lifecycle",
                        "--auto-review",
                        "--auto-risk-approval",
                        "--auto-repair",
                    ]
                ),
                1,
            )

            schedule_dir = root / ".ai" / "runs" / "run-automation-followup-001"
            child_run_id = "run-automation-followup-001-T-followup-backend-implementer"
            child_dir = root / ".ai" / "runs" / child_run_id
            summary = json.loads((schedule_dir / "automation_run.json").read_text())
            child = summary["children"][0]
            self.assertEqual(child["review_agent_status"], "succeeded")
            self.assertEqual(child["risk_approval_agent_status"], "succeeded")
            self.assertEqual(json.loads((child_dir / "review_findings.json").read_text())["findings"], [])
            self.assertEqual(json.loads((child_dir / "risk_approval.json").read_text())["source_run_id"], child_run_id)
            self.assertEqual(json.loads((child_dir / "risk_approval_gate.json").read_text())["status"], "passed")
            repair_plan = json.loads((child_dir / "repair_schedule_plan.json").read_text())
            self.assertEqual(repair_plan["run_plan"][0]["agent_id"], "ci-repair-agent")
            self.assertEqual(summary["status"], "failed")

    def test_automation_run_can_dispatch_auto_repair_run_when_lifecycle_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self._install_multi_output_test_connector(root)
            self._bind_agent_to_test_connector(root, "backend-implementer")
            self._bind_agent_to_test_connector(root, "ci-repair-agent")
            self._init_git_repo(root)
            plan = root / "automation_auto_repair_plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "run_plan": [
                            {
                                "agent_id": "backend-implementer",
                                "task_id": "T-repair-source",
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
                        "run-automation-auto-repair-001",
                        "--validation-mode",
                        "skip",
                        "--timeout",
                        "5",
                        "--lifecycle",
                        "--auto-repair",
                        "--run-auto-repair",
                    ]
                ),
                1,
            )

            schedule_dir = root / ".ai" / "runs" / "run-automation-auto-repair-001"
            source_run_id = "run-automation-auto-repair-001-T-repair-source-backend-implementer"
            source_dir = root / ".ai" / "runs" / source_run_id
            summary = json.loads((schedule_dir / "automation_run.json").read_text())
            child = summary["children"][0]
            repair_dispatch_id = f"{source_run_id}-repair-dispatch"
            repair_child_id = f"{repair_dispatch_id}-T-repair-ci-repair-agent"
            self.assertEqual(child["repair_schedule_status"], "recommended")
            self.assertEqual(child["auto_repair_run_status"], "succeeded")
            self.assertTrue((source_dir / "auto_repair_run.json").exists())
            self.assertTrue((root / ".ai" / "runs" / repair_dispatch_id / "dispatch_run.json").exists())
            self.assertTrue((root / ".ai" / "runs" / repair_child_id / "connector_execution.json").exists())

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

    def test_automation_daemon_dry_run_writes_event_scheduler_task(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            event = root / "event.json"
            main(["init", "--target", str(root)])
            event.write_text(
                json.dumps(
                    {
                        "action": "opened",
                        "issue": {"number": 42, "title": "Add daemon task", "body": "Build the event bridge."},
                        "repository": {"full_name": "example/repo"},
                    }
                )
            )

            self.assertEqual(
                main(
                    [
                        "automation-daemon",
                        "--target",
                        str(root),
                        "--event-file",
                        str(event),
                        "--run-id",
                        "run-daemon-001",
                    ]
                ),
                0,
            )

            event_dir = root / ".ai" / "events" / "run-daemon-001"
            summary = json.loads((event_dir / "automation_daemon.json").read_text())
            task = json.loads((event_dir / "scheduler_task.json").read_text())
            self.assertEqual(summary["status"], "planned")
            self.assertFalse(summary["executed"])
            self.assertEqual(summary["issue"], "42")
            self.assertIn("Add daemon task", task["summary"])
            self.assertFalse((root / ".ai" / "runs" / "run-daemon-001").exists())

    def test_github_sync_poll_creates_local_events_for_label_and_comment_triggers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            fake_gh = root / "fake-gh"
            issues = [
                {
                    "number": 42,
                    "title": "Build local daemon",
                    "body": "Run this locally.",
                    "url": "https://github.com/example/repo/issues/42",
                    "updatedAt": "2026-05-26T01:02:03Z",
                    "labels": [{"name": "ai:auto"}],
                    "comments": [{"body": "/ai run", "author": {"login": "yanxwww"}, "createdAt": "2026-05-26T01:03:03Z"}],
                }
            ]
            script = (
                "import json,sys; "
                f"issues={issues!r}; "
                "args=sys.argv[1:]; "
                "print(json.dumps(issues if args[:2]==['issue','list'] else []));"
            )
            fake_gh.write_text(f"#!{sys.executable}\n{script}\n")
            fake_gh.chmod(0o755)

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-poll-001",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )

            poll = json.loads((root / ".ai" / "local-daemon" / "polls" / "run-local-poll-001.json").read_text())
            self.assertEqual(poll["status"], "planned")
            self.assertEqual(poll["created_event_count"], 2)
            event_ids = {event["event_id"] for event in poll["created_events"]}
            self.assertEqual(event_ids, {"issue-42-ai-auto", "issue-42-ai-run"})
            task = json.loads((root / ".ai" / "local-daemon" / "events" / "issue-42-ai-run" / "scheduler_task.json").read_text())
            self.assertIn("Build local daemon", task["summary"])
            self.assertIn("/ai run", task["trigger"])
            state = json.loads((root / ".ai" / "local-daemon" / "state.json").read_text())
            self.assertEqual(set(state["processed_event_ids"]), event_ids)

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-poll-002",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )
            poll2 = json.loads((root / ".ai" / "local-daemon" / "polls" / "run-local-poll-002.json").read_text())
            self.assertEqual(poll2["created_event_count"], 0)

    def test_github_sync_poll_uses_configurable_trigger_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            (root / ".ai" / "rules" / "local-daemon.yml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "label_actions:",
                        "  ai:custom: review",
                        "comment_actions:",
                        "  /ai custom: repair",
                        "",
                    ]
                )
            )
            fake_gh = root / "fake-gh"
            issues = [
                {
                    "number": 21,
                    "title": "Custom trigger policy",
                    "body": "Run this locally.",
                    "url": "https://github.com/example/repo/issues/21",
                    "updatedAt": "2026-05-26T01:02:03Z",
                    "labels": [{"name": "ai:custom"}, {"name": "ai:auto"}],
                    "comments": [{"body": "/ai run"}],
                },
                {
                    "number": 22,
                    "title": "Custom comment trigger policy",
                    "body": "Run this locally.",
                    "url": "https://github.com/example/repo/issues/22",
                    "updatedAt": "2026-05-26T01:02:03Z",
                    "labels": [],
                    "comments": [{"body": "/ai custom"}],
                },
            ]
            script = (
                "import json,sys; "
                f"issues={issues!r}; "
                "args=sys.argv[1:]; "
                "print(json.dumps(issues if args[:2]==['issue','list'] else []));"
            )
            fake_gh.write_text(f"#!{sys.executable}\n{script}\n")
            fake_gh.chmod(0o755)

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-policy-001",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )

            poll = json.loads((root / ".ai" / "local-daemon" / "polls" / "run-local-policy-001.json").read_text())
            created = {event["event_id"]: event for event in poll["created_events"]}
            self.assertEqual(set(created), {"issue-21-ai-custom", "issue-22-ai-custom"})
            self.assertEqual(created["issue-21-ai-custom"]["action"], "review")
            self.assertEqual(created["issue-22-ai-custom"]["action"], "repair")
            task = json.loads((root / ".ai" / "local-daemon" / "events" / "issue-21-ai-custom" / "scheduler_task.json").read_text())
            self.assertEqual(task["action"], "review")

    def test_local_daemon_once_runs_github_sync_poll(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            fake_gh = root / "fake-gh"
            issues = [
                {
                    "number": 7,
                    "title": "Plan from daemon",
                    "body": "Plan only.",
                    "url": "https://github.com/example/repo/issues/7",
                    "updatedAt": "2026-05-26T01:02:03Z",
                    "labels": [{"name": "ai:plan"}],
                    "comments": [],
                }
            ]
            script = (
                "import json,sys; "
                f"issues={issues!r}; "
                "args=sys.argv[1:]; "
                "print(json.dumps(issues if args[:2]==['issue','list'] else []));"
            )
            fake_gh.write_text(f"#!{sys.executable}\n{script}\n")
            fake_gh.chmod(0o755)

            self.assertEqual(
                main(
                    [
                        "local-daemon",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-daemon-001",
                        "--once",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )

            summary = json.loads((root / ".ai" / "local-daemon" / "polls" / "run-local-daemon-001.json").read_text())
            self.assertEqual(summary["mode"], "once")
            self.assertEqual(summary["created_event_count"], 1)
            self.assertTrue((root / ".ai" / "local-daemon" / "events" / "issue-7-ai-plan" / "scheduler_task.json").exists())

    def test_github_sync_poll_requires_exclusive_local_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            lease = root / ".ai" / "local-daemon" / "leases" / "poll.lock"
            lease.write_text(json.dumps({"run_id": "run-other"}))

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-poll-locked",
                    ]
                ),
                1,
            )
            self.assertFalse((root / ".ai" / "local-daemon" / "polls" / "run-local-poll-locked.json").exists())

    def test_github_sync_poll_execute_requires_passing_github_doctor_before_events(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            calls_log = root / "gh-calls.jsonl"
            fake_gh = root / "fake-gh"
            issues = [
                {
                    "number": 42,
                    "title": "Should not run",
                    "body": "Run this locally.",
                    "url": "https://github.com/example/repo/issues/42",
                    "updatedAt": "2026-05-26T01:02:03Z",
                    "labels": [{"name": "ai:auto"}],
                    "comments": [],
                }
            ]
            script = (
                "import json,sys\n"
                f"issues={issues!r}\n"
                f"log={str(calls_log)!r}\n"
                "args=sys.argv[1:]\n"
                "open(log, 'a').write(json.dumps(args) + '\\n')\n"
                "if args[:2] == ['auth', 'status']:\n"
                "    print('not authenticated')\n"
                "    sys.exit(1)\n"
                "if args[:2] == ['repo', 'view']:\n"
                "    print('{\"nameWithOwner\":\"example/repo\"}')\n"
                "elif args[:2] == ['issue', 'list']:\n"
                "    print(json.dumps(issues))\n"
                "elif args[:2] == ['pr', 'list']:\n"
                "    print('[]')\n"
                "else:\n"
                "    print('[]')\n"
            )
            fake_gh.write_text(f"#!{sys.executable}\n{script}")
            fake_gh.chmod(0o755)

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-preflight-001",
                        "--executable",
                        str(fake_gh),
                        "--execute",
                    ]
                ),
                1,
            )

            poll = json.loads((root / ".ai" / "local-daemon" / "polls" / "run-local-preflight-001.json").read_text())
            self.assertEqual(poll["status"], "failed")
            self.assertEqual(poll["execute_preflight"]["status"], "failed")
            self.assertEqual(poll["created_event_count"], 0)
            self.assertFalse((root / ".ai" / "local-daemon" / "events" / "issue-42-ai-auto").exists())
            doctor = json.loads((root / ".ai" / "github_doctor.json").read_text())
            self.assertEqual(doctor["status"], "failed")
            calls = [json.loads(line) for line in calls_log.read_text().splitlines()]
            self.assertIn(["auth", "status"], calls)
            self.assertNotIn(["issue", "list", "--state", "open", "--json", "number,title,body,labels,comments,updatedAt,url"], calls)

    def test_github_sync_poll_retries_failed_execute_events_and_dead_letters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            self._install_failing_test_connector(root)
            self._init_git_repo(root)
            remote = root / "remote.git"
            self._init_bare_remote(root, remote)
            (root / ".ai" / "rules" / "local-daemon.yml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "label_actions:",
                        "  ai:auto: run",
                        "comment_actions:",
                        "  /ai run: run",
                        "retry:",
                        "  max_attempts: 2",
                        "  backoff_seconds: 3600",
                        "  retry_label: ai:retry",
                        "  retry_comment: /ai retry",
                        "",
                    ]
                )
            )
            retry_flag = root / "retry.flag"
            fake_gh = root / "fake-gh"
            script = (
                "import json,sys\n"
                f"retry_flag={str(retry_flag)!r}\n"
                "args=sys.argv[1:]\n"
                "comments=[{'body':'/ai retry'}] if __import__('pathlib').Path(retry_flag).exists() else []\n"
                "issues=[{'number':42,'title':'Retry failed automation','body':'Run this locally.',"
                "'url':'https://github.com/example/repo/issues/42','updatedAt':'2026-05-26T01:02:03Z',"
                "'labels':[{'name':'ai:auto'}],'comments':comments}]\n"
                "if args[:2] == ['auth', 'status']:\n"
                "    print('authenticated')\n"
                "elif args[:2] == ['repo', 'view']:\n"
                "    print('{\"nameWithOwner\":\"example/repo\",\"url\":\"https://github.com/example/repo\"}')\n"
                "elif args[:2] == ['issue', 'list']:\n"
                "    print(json.dumps(issues))\n"
                "elif args[:2] == ['pr', 'list']:\n"
                "    print('[]')\n"
                "else:\n"
                "    print('[]')\n"
            )
            fake_gh.write_text(f"#!{sys.executable}\n{script}")
            fake_gh.chmod(0o755)
            event_dir = root / ".ai" / "local-daemon" / "events" / "issue-42-ai-auto"
            event_dir.mkdir(parents=True)
            (event_dir / "event.json").write_text("{}\n")

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-retry-001",
                        "--executable",
                        str(fake_gh),
                        "--execute",
                        "--timeout",
                        "5",
                    ]
                ),
                1,
            )
            first = json.loads((event_dir / "event_result.json").read_text())
            self.assertEqual(first["status"], "failed")
            self.assertEqual(first["completion_status"], "incomplete")
            self.assertEqual(first["retry"]["attempts"], 1)
            self.assertTrue(first["automation_run_id"].endswith("-attempt-1"))
            first_task = json.loads((event_dir / "scheduler_task.json").read_text())
            self.assertTrue(first_task["retry_context"]["resume"])
            self.assertEqual(first_task["retry_context"]["attempt"], 1)
            state = json.loads((root / ".ai" / "local-daemon" / "state.json").read_text())
            self.assertNotIn("issue-42-ai-auto", state["processed_event_ids"])
            self.assertEqual(state["retry_events"]["issue-42-ai-auto"]["attempts"], 1)
            previous_run_dir = root / ".ai" / "runs" / first["automation_run_id"]
            previous_run_dir.mkdir(parents=True, exist_ok=True)
            previous_child_dir = root / ".ai" / "runs" / "run-local-child-001"
            previous_child_dir.mkdir(parents=True, exist_ok=True)
            (previous_run_dir / "automation_run.json").write_text(
                json.dumps(
                    {
                        "children": [
                            {
                                "run_id": "run-local-child-001",
                                "agent_id": "backend-implementer",
                                "status": "failed",
                                "connector_status": "failed",
                            }
                        ]
                    }
                )
            )
            (previous_child_dir / "connector_execution.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "runtime_session": {
                            "kind": "codex_thread",
                            "id": "thread-private-001",
                            "resume_mode": "cli_resume",
                        },
                        "last_agent_message": "I only produced next-step advice.",
                    }
                )
            )

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-retry-002",
                        "--executable",
                        str(fake_gh),
                        "--execute",
                        "--timeout",
                        "5",
                    ]
                ),
                0,
            )
            second = json.loads((root / ".ai" / "local-daemon" / "polls" / "run-local-retry-002.json").read_text())
            self.assertEqual(second["created_event_count"], 0)
            self.assertEqual(second["skipped_events"][0]["reason"], "waiting_for_retry_backoff")

            retry_flag.write_text("retry\n")
            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-retry-003",
                        "--executable",
                        str(fake_gh),
                        "--execute",
                        "--timeout",
                        "5",
                    ]
                ),
                1,
            )
            third = json.loads((event_dir / "event_result.json").read_text())
            self.assertTrue(third["dead_lettered"])
            self.assertEqual(third["retry"]["attempts"], 2)
            self.assertTrue(third["automation_run_id"].endswith("-attempt-2"))
            third_task = json.loads((event_dir / "scheduler_task.json").read_text())
            self.assertEqual(third_task["retry_context"]["previous_result"]["status"], "failed")
            self.assertEqual(third_task["retry_context"]["previous_retry"]["attempts"], 1)
            self.assertEqual(
                third_task["runtime_state_request_artifact"],
                ".ai/local-daemon/events/issue-42-ai-auto/runtime_state_request.json",
            )
            self.assertEqual(third_task["runtime_state_request"]["assessor_agent_id"], "scheduler-agent")
            runtime_state_request = json.loads((event_dir / "runtime_state_request.json").read_text())
            self.assertEqual(runtime_state_request["assessor_agent_id"], "scheduler-agent")
            self.assertEqual(third_task["runtime_state_request"], runtime_state_request)
            self.assertEqual(runtime_state_request["observed"]["completion_status"], "incomplete")
            self.assertIn("resume_runtime_session", runtime_state_request["decision_contract"]["allowed_decisions"])
            self.assertIn("repair_new_run", runtime_state_request["decision_contract"]["allowed_decisions"])
            self.assertEqual(runtime_state_request["runtime_observations"][0]["agent_id"], "backend-implementer")
            self.assertTrue(runtime_state_request["runtime_observations"][0]["resume_available"])
            self.assertEqual(
                runtime_state_request["runtime_observations"][0]["last_agent_message"],
                "I only produced next-step advice.",
            )
            self.assertNotIn("thread-private-001", json.dumps(runtime_state_request))
            dead_letter = root / ".ai" / "local-daemon" / "dead-letter" / "issue-42-ai-auto" / "dead_letter.json"
            self.assertTrue(dead_letter.exists())
            state = json.loads((root / ".ai" / "local-daemon" / "state.json").read_text())
            self.assertIn("issue-42-ai-auto", state["dead_letter_event_ids"])

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-retry-004",
                        "--executable",
                        str(fake_gh),
                        "--execute",
                        "--timeout",
                        "5",
                    ]
                ),
                1,
            )
            fourth = json.loads((event_dir / "event_result.json").read_text())
            self.assertFalse(fourth.get("dead_lettered", False))
            self.assertEqual(fourth["retry"]["attempts"], 1)
            state = json.loads((root / ".ai" / "local-daemon" / "state.json").read_text())
            self.assertNotIn("issue-42-ai-auto", state["dead_letter_event_ids"])
            self.assertEqual(state["retry_events"]["issue-42-ai-auto"]["attempts"], 1)

    def test_github_sync_poll_status_sync_posts_planned_comment_and_event_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            calls_log = root / "gh-calls.jsonl"
            fake_gh = root / "fake-gh"
            issues = [
                {
                    "number": 42,
                    "title": "Build local status sync",
                    "body": "Run this locally.",
                    "url": "https://github.com/example/repo/issues/42",
                    "updatedAt": "2026-05-26T01:02:03Z",
                    "labels": [{"name": "ai:plan"}],
                    "comments": [],
                }
            ]
            script = (
                "import json,sys\n"
                f"issues={issues!r}\n"
                f"log={str(calls_log)!r}\n"
                "args=sys.argv[1:]\n"
                "open(log, 'a').write(json.dumps(args) + '\\n')\n"
                "if args[:2] == ['issue', 'list']:\n"
                "    print(json.dumps(issues))\n"
                "elif args[:2] == ['pr', 'list']:\n"
                "    print('[]')\n"
                "elif args[:2] == ['issue', 'comment']:\n"
                "    print('https://github.com/example/repo/issues/42#issuecomment-1')\n"
                "else:\n"
                "    print('[]')\n"
            )
            fake_gh.write_text(f"#!{sys.executable}\n{script}")
            fake_gh.chmod(0o755)

            self.assertEqual(
                main(
                    [
                        "github-sync-poll",
                        "--target",
                        str(root),
                        "--run-id",
                        "run-local-poll-status-001",
                        "--executable",
                        str(fake_gh),
                        "--status-sync",
                    ]
                ),
                0,
            )

            event_dir = root / ".ai" / "local-daemon" / "events" / "issue-42-ai-plan"
            result = json.loads((event_dir / "event_result.json").read_text())
            self.assertEqual(result["status"], "planned")
            self.assertEqual(result["status_sync"]["status"], "succeeded")
            self.assertEqual(result["status_sync"]["source"]["number"], 42)
            body = (event_dir / "status_comment.md").read_text()
            self.assertIn("Status: planned", body)
            self.assertIn("scheduler task", body)
            self.assertNotIn("trace.jsonl", body)
            self.assertNotIn("stdout.log", body)
            calls = [json.loads(line) for line in calls_log.read_text().splitlines()]
            self.assertIn(["issue", "comment", "42", "--body-file", str((event_dir / "status_comment.md").resolve())], calls)
            poll = json.loads((root / ".ai" / "local-daemon" / "polls" / "run-local-poll-status-001.json").read_text())
            self.assertEqual(poll["created_events"][0]["status_sync"]["status"], "succeeded")

    def test_github_status_sync_comments_without_raw_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            event_dir = root / ".ai" / "local-daemon" / "events" / "issue-42-ai-run"
            event_dir.mkdir(parents=True)
            (event_dir / "event.json").write_text(
                json.dumps(
                    {
                        "event_id": "issue-42-ai-run",
                        "source": {"kind": "issue", "number": 42, "url": "https://github.com/example/repo/issues/42"},
                        "trigger": "/ai run",
                        "action": "run",
                    }
                )
            )
            argv_log = root / "gh-argv.json"
            fake_gh = root / "fake-gh"
            script = (
                "import json,sys; "
                f"open({str(argv_log)!r}, 'w').write(json.dumps(sys.argv[1:])); "
                "print('https://github.com/example/repo/issues/42#issuecomment-1')"
            )
            fake_gh.write_text(f"#!{sys.executable}\n{script}\n")
            fake_gh.chmod(0o755)

            self.assertEqual(
                main(
                    [
                        "github-status-sync",
                        "--target",
                        str(root),
                        "--event-id",
                        "issue-42-ai-run",
                        "--status",
                        "planned",
                        "--message",
                        "scheduler task ready",
                        "--executable",
                        str(fake_gh),
                    ]
                ),
                0,
            )

            body = (event_dir / "status_comment.md").read_text()
            self.assertIn("Status: planned", body)
            self.assertIn("scheduler task ready", body)
            self.assertNotIn("trace.jsonl", body)
            argv = json.loads(argv_log.read_text())
            self.assertEqual(argv[:3], ["issue", "comment", "42"])
            self.assertIn("--body-file", argv)
            sync = json.loads((event_dir / "status_sync.json").read_text())
            self.assertEqual(sync["status"], "succeeded")

    def test_artifact_retention_report_detects_secret_like_run_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            main(["init", "--target", str(root)])
            run_dir = root / ".ai" / "runs" / "run-secret-001"
            run_dir.mkdir(parents=True)
            (run_dir / "stdout.log").write_text("OPENAI_API_KEY=sk-test-secret\n")

            self.assertEqual(main(["artifact-retention-report", "--target", str(root)]), 0)

            report = json.loads((root / ".ai" / "artifact_retention_report.json").read_text())
            self.assertEqual(report["status"], "findings")
            self.assertTrue(any(finding["kind"] == "redaction" for finding in report["findings"]))

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

    def _install_multi_output_test_connector(self, root: Path) -> None:
        plan = {
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
        code = (
            "import json,re,sys; "
            "schema=sys.argv[1] if len(sys.argv)>1 else ''; "
            "prompt=sys.stdin.read(); "
            "match=re.search(r'\"source_run_id\"\\s*:\\s*\"([^\"]+)\"', prompt); "
            "source=match.group(1) if match else 'unknown'; "
            f"plan={plan!r}; "
            "review={'findings':[]}; "
            "risk={'status':'approved','approver_agent_id':'risk-approval-agent','source_run_id':source,'risk_level':'high','rationale':'Automated test approval.'}; "
            "agent={'status':'succeeded','summary':'ok','evidence':{}}; "
            "value=({'result':'```json\\n'+json.dumps(plan)+'\\n```'} if schema.endswith('schedule_plan.schema.json') "
            "else review if schema.endswith('review_findings.schema.json') "
            "else risk if schema.endswith('risk_approval.schema.json') "
            "else agent); "
            "print(json.dumps(value))"
        )
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
                    f"  test-profile: {sys.executable} -c {json.dumps(code)} {{output_schema}}",
                    "",
                ]
            )
        )

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
