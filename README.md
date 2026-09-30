# Gitflow Hotfix Skill

Reusable instructions and a read-only audit helper for AI agents handling GitHub hotfixes in repositories that use Gitflow.

The core workflow lives in [`SKILL.md`](SKILL.md). Any agent that supports `SKILL.md` skills can load it; others can read it directly as repository guidance. Shared rules come from the `agent-policy` skill; commits and PRs are delegated to `git-commit` and `pr-create`.

## What This Covers

- Proving that a target repository uses Gitflow before starting hotfix work.
- Requiring hotfix branches to use `hotfix/<branchname>`, or `hotfix/<KEY>-<number>_<description>` for Jira-tracked (`github.com/cisco-sbg`) repositories.
- Ensuring existing hotfix branches are based on the production branch, usually `main` or `master`.
- Creating missing hotfix branches from production.
- Pushing one hotfix branch and creating PRs back to production, development, and any active release branches.

## Repository Contents

- `SKILL.md`: Agent-neutral workflow and hard gates.
- `scripts/gitflow_hotfix_audit.py`: Read-only Git audit helper for Gitflow and hotfix lineage checks.
- `agents/openai.yaml`: Optional agent UI metadata.

## Audit Helper

Run the helper from inside the target repository:

```bash
/path/to/github-gitflow-hotfix-skill/scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname>
```

Useful options:

```bash
/path/to/github-gitflow-hotfix-skill/scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname> --remote origin --json
/path/to/github-gitflow-hotfix-skill/scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname> --main main --develop develop
/path/to/github-gitflow-hotfix-skill/scripts/gitflow_hotfix_audit.py --hotfix hotfix/DISC-123_fix_timeout --require-jira
```

The Jira-keyed name is enforced automatically for `github.com/cisco-sbg` remotes and with `--require-jira` elsewhere.

The helper does not fetch, create branches, check out branches, or edit files.

## Agent Notes

Load `SKILL.md` as a skill, or include it in the agent's context, and run the audit helper before branch actions. All agents should stop and ask the user when Gitflow cannot be proven, hotfix lineage is ambiguous, release branches are unknown, or a push would require history rewriting.

## Validation

Validate the skill metadata with your agent environment's skill validator, for example:

```bash
python3 <skill-creator>/scripts/quick_validate.py .
```

Skip this check if no validator is available.

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

## Dependencies

- MCP dependencies: None detected.
