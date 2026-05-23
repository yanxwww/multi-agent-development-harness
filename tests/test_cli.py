import json
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


if __name__ == "__main__":
    unittest.main()
