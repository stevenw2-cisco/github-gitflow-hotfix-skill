# Gitflow Hotfix Skill

Reusable instructions and a read-only audit helper for AI agents handling GitHub hotfixes in repositories that use Gitflow.

The core workflow lives in [`SKILL.md`](SKILL.md). Codex can load that file as a skill, while GitHub Copilot, Claude Code, Gemini CLI, and other AI coding agents can read it directly as repository guidance.

## What This Covers

- Proving that a target repository uses Gitflow before starting hotfix work.
- Requiring hotfix branches to use `hotfix/<branchname>`.
- Ensuring existing hotfix branches are based on the production branch, usually `main` or `master`.
- Creating missing hotfix branches from production.
- Pushing one hotfix branch and creating PRs back to production, development, and any active release branches.

## Repository Contents

- `SKILL.md`: Agent-neutral workflow and hard gates.
- `scripts/gitflow_hotfix_audit.py`: Read-only Git audit helper for Gitflow and hotfix lineage checks.
- `agents/openai.yaml`: Optional OpenAI/Codex UI metadata.

## Audit Helper

Run the helper from inside the target repository:

```bash
/path/to/github-gitflow-hotfix-skill/scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname>
```

Useful options:

```bash
/path/to/github-gitflow-hotfix-skill/scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname> --remote origin --json
/path/to/github-gitflow-hotfix-skill/scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname> --main main --develop develop
```

The helper does not fetch, create branches, check out branches, or edit files.

## Agent Notes

- Codex: install or reference this directory as a skill.
- GitHub Copilot: point the coding agent or chat context at `SKILL.md` before asking for hotfix work.
- Claude Code: include `SKILL.md` in the working context and require the audit helper before branch actions.
- Gemini CLI: include `SKILL.md` as repo guidance and run the audit helper before branch actions.

All agents should stop and ask the user when Gitflow cannot be proven, hotfix lineage is ambiguous, release branches are unknown, or a push would require history rewriting.

## Validation

Validate the skill metadata with the skill validator available in your agent environment. In this author's local Codex setup that command is:

```bash
python3.11 /Users/stevenw2/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

If that path does not exist, replace it with your local Codex skill validator path or skip this check for non-Codex usage.

Compile-check the helper without writing bytecode into the repo:

```bash
python3.11 - <<'PY'
import py_compile
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
    py_compile.compile("scripts/gitflow_hotfix_audit.py", cfile=str(Path(tmp) / "gitflow_hotfix_audit.pyc"), doraise=True)
print("py_compile ok")
PY
```

Run the audit helper tests:

```bash
python3.11 -B -m unittest tests/test_gitflow_hotfix_audit.py
```
