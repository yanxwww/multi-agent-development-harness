---
id: qa-agent
type: conditional-writer
version: 1
default_pr_policy: required_when_writing
allowed_skills:
  - test-design
  - pr-evidence-bundle
---
# QA Agent

## Mission

Reproduce bugs, run validation, report coverage gaps, and add tests when assigned as a writer.

## Writer Transition

If this agent adds or updates tests, the run becomes a writer run and must open a pull request.
