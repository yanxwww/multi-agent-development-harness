# AI Harness MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable local CLI that scaffolds and validates a neutral Codex / Claude Code AI development harness.

**Architecture:** A Python standard-library CLI owns the scaffold templates, a small YAML-subset parser for generated config files, run metadata generation, and PR body rendering. The harness is configuration-driven: roles, assignments, runtime adapters, rules, schemas, and generated run artifacts remain plain files inside the target repository.

**Tech Stack:** Python 3.13, `argparse`, `json`, `unittest`, git CLI for optional worktree creation.

---

### Task 1: Package Skeleton and CLI Tests

**Files:**
- Create: `tests/test_cli.py`
- Create: `pyproject.toml`
- Create: `src/ai_harness/__init__.py`
- Create: `src/ai_harness/__main__.py`
- Create: `src/ai_harness/cli.py`

- [ ] **Step 1: Write failing tests for init, validate, create-run, and pr-body**

```python
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
            self.assertTrue((root / ".ai" / "assignments.yml").exists())
            self.assertTrue((root / ".claude" / "settings.json").exists())
            self.assertIn("CLAUDE.md", (root / ".gitignore").read_text())
            self.assertFalse((root / "CLAUDE.md").exists())

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
            self.assertEqual(main([
                "create-run",
                "--target", str(root),
                "--issue", "123",
                "--role", "backend-implementer",
                "--task", str(task),
                "--run-id", "run-20260523-001",
                "--no-worktree",
            ]), 0)
            run_dir = root / ".ai" / "runs" / "run-20260523-001"
            run = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(run["role_id"], "backend-implementer")
            self.assertEqual(run["runtime_id"], "codex")
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
            main([
                "create-run",
                "--target", str(root),
                "--issue", "123",
                "--role", "backend-implementer",
                "--task", str(task),
                "--run-id", "run-20260523-001",
                "--no-worktree",
            ])
            self.assertEqual(main(["pr-body", "--target", str(root), "--run", "run-20260523-001"]), 0)
            body = (root / ".ai" / "runs" / "run-20260523-001" / "pr-body.md").read_text()
            self.assertIn("Agent ID: backend-implementer", body)
            self.assertIn("Runtime: codex", body)
            self.assertIn("Closes #123", body)
```

- [ ] **Step 2: Run tests to verify they fail because `ai_harness` does not exist**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL or ERROR with `ModuleNotFoundError: No module named 'ai_harness'`.

### Task 2: Scaffold Templates

**Files:**
- Create: `src/ai_harness/scaffold.py`

- [ ] **Step 1: Implement scaffold template generation**

Generate `AGENTS.md`, `.gitignore`, `.ai/harness.yml`, `.ai/assignments.yml`, role profiles, runtime adapter profiles, rules, schemas, skill registry, `.agents/skills/.gitkeep`, `.claude/skills/.gitkeep`, `.claude/settings.json`, docs directories, and `.ai/runs/.gitkeep`.

- [ ] **Step 2: Run the init test**

Run: `python3 -m unittest tests.test_cli.HarnessCliTests.test_init_creates_canonical_scaffold -v`
Expected: PASS.

### Task 3: YAML Subset and Validation

**Files:**
- Create: `src/ai_harness/yaml_lite.py`
- Create: `src/ai_harness/validation.py`

- [ ] **Step 1: Implement the YAML subset parser**

Support the scaffold's mapping/list/scalar subset so the harness can validate its own generated files without third-party dependencies.

- [ ] **Step 2: Implement validation checks**

Check required files, role ids, assignment references, runtime references, skill allowlists, schema JSON syntax, and `CLAUDE.md` gitignore policy.

- [ ] **Step 3: Run the validate test**

Run: `python3 -m unittest tests.test_cli.HarnessCliTests.test_validate_accepts_fresh_scaffold -v`
Expected: PASS.

### Task 4: Run Creation and PR Body Rendering

**Files:**
- Create: `src/ai_harness/runs.py`

- [ ] **Step 1: Implement run metadata creation**

Resolve role and runtime assignment, normalize issue ids to `issue-<number>`, create `.ai/runs/<run-id>`, copy task metadata, create `run.json`, `assignment.json`, `trace.jsonl`, `evidence.json`, and optionally create a git worktree.

- [ ] **Step 2: Implement PR body rendering**

Render `.ai/runs/<run-id>/pr-body.md` from evidence, run metadata, role hash, issue id, validation placeholders, risk notes, rollback notes, and unresolved questions.

- [ ] **Step 3: Run create-run and pr-body tests**

Run: `python3 -m unittest tests.test_cli.HarnessCliTests.test_create_run_writes_writer_metadata_without_worktree tests.test_cli.HarnessCliTests.test_pr_body_renders_evidence_bundle -v`
Expected: PASS.

### Task 5: CLI Wiring and Full Verification

**Files:**
- Modify: `src/ai_harness/cli.py`
- Modify: `src/ai_harness/__main__.py`
- Modify: `README.md`

- [ ] **Step 1: Wire commands through argparse**

Expose `init`, `validate`, `create-run`, and `pr-body`.

- [ ] **Step 2: Add README usage**

Document the architecture, commands, generated layout, and current non-goals.

- [ ] **Step 3: Run full test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS.

- [ ] **Step 4: Run smoke commands**

Run:

```bash
tmp="$(mktemp -d)"
python3 -m ai_harness init --target "$tmp"
python3 -m ai_harness validate --target "$tmp"
printf '{"summary":"Smoke task"}' > "$tmp/task.json"
python3 -m ai_harness create-run --target "$tmp" --issue 1 --role backend-implementer --task "$tmp/task.json" --run-id run-smoke-001 --no-worktree
python3 -m ai_harness pr-body --target "$tmp" --run run-smoke-001
```

Expected: every command exits `0` and the run directory contains `run.json`, `evidence.json`, `trace.jsonl`, and `pr-body.md`.

