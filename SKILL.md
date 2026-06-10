---
name: github-gitflow-hotfix-skill
description: Manage GitHub hotfix workflows for repositories that use Gitflow. Use when Codex needs to verify Gitflow, create or validate hotfix branches, enforce production-branch lineage, commit and push a hotfix, or create hotfix pull requests back to production, development, and release branches.
---

# Gitflow Hotfix

Use this workflow for Gitflow repositories when a production hotfix must be made from a `hotfix/<branchname>` branch and then proposed back to production, development, and any active release branches.

## Hard Gates

- First prove the repository uses Gitflow. If Gitflow cannot be determined, stop and ask the user.
- Do not assume Gitflow from a lone `develop` branch.
- Require a known production branch, usually `main` or `master`.
- Require a known development branch that differs from production, usually `develop`.
- Require hotfix branches to use `hotfix/<branchname>`.
- Existing hotfix branches must have production lineage. If lineage is ambiguous or development-based, stop and ask the user.
- Commit, push, and create PRs only while the current branch is the hotfix branch.
- Never force push unless the user explicitly approves it first.
- If repo-local instructions conflict with the mandatory hotfix branch pattern, stop and ask the user.

## Audit Helper

Run the read-only helper before creating, switching to, committing on, or creating PRs from a hotfix branch:

```bash
scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname>
```

Useful options:

```bash
scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname> --remote origin --json
scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname> --main main --develop develop
```

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Gitflow was proven and the hotfix branch is either absent or has valid lineage. |
| 2 | Gitflow, production branch, or development branch could not be determined. |
| 3 | The hotfix branch name is invalid. |
| 4 | Required git repository data could not be read. |
| 5 | The hotfix branch exists but does not satisfy production lineage. |

The helper does not fetch, create branches, check out branches, or edit files.

## Workflow

1. Prepare repository context.
   - Confirm the worktree is clean before switching or creating branches:
     ```bash
     git status --short
     ```
   - Refresh remote refs when network access is available:
     ```bash
     git fetch --prune origin
     ```
   - Read repo-local rules first: `AGENTS.md`, `CONTRIBUTING.md`, and root README files.

2. Establish Gitflow.
   - Identify production as exactly one of `main` or `master`, unless the user supplies a repo-specific production branch.
   - Identify development from `origin/HEAD` when it differs from production, or from root README Gitflow wording plus a real development branch.
   - Treat README wording such as `gitflow`, `git flow`, `hotfix/`, or Gitflow-style release/hotfix process descriptions as Gitflow evidence.
   - If signals are missing or mixed, stop and ask the user to confirm production and development branches.

3. Resolve the hotfix branch.
   - If the user gives only a suffix, use `hotfix/<suffix>`.
   - Run the audit helper for the final branch name.
   - If the branch exists locally, switch to it only from a clean worktree:
     ```bash
     git switch hotfix/<branchname>
     ```
   - If the branch exists only on the remote, create a local tracking branch only after the audit confirms lineage:
     ```bash
     git switch --track origin/hotfix/<branchname>
     ```
   - If the branch does not exist, create it from the production branch:
     ```bash
     git switch -c hotfix/<branchname> origin/main
     ```
     Replace `origin/main` with the proven production ref.

4. Apply and validate the fix.
   - Make the minimum hotfix changes on the hotfix branch.
   - Follow repository language conventions and doc/comment standards.
   - Detect and run applicable validation before committing. Prefer Makefile targets over direct tool commands when present.
   - If validation tooling is absent, report that explicitly.

5. Commit and push.
   - Reconfirm the current branch:
     ```bash
     git branch --show-current
     ```
   - If it is not the expected `hotfix/<branchname>`, stop.
   - Stage only intended files, commit with the repository's commit convention, and push:
     ```bash
     git add <intended-files>
     git status --short
     git commit -m "<message>"
     git push -u origin hotfix/<branchname>
     ```

6. Create pull requests.
   - Ask the user to list release branches, or confirm that there are none.
   - Create PRs from the hotfix branch to:
     - production, such as `main` or `master`
     - development, such as `develop`
     - each user-specified release branch
   - Use `.github/pull_request_template.md` exactly when it exists.
   - Use explicit bases and heads:
     ```bash
     gh pr create --base main --head hotfix/<branchname> --title "<title>" --body-file <body-file>
     gh pr create --base develop --head hotfix/<branchname> --title "<title>" --body-file <body-file>
     gh pr create --base release/<name> --head hotfix/<branchname> --title "<title>" --body-file <body-file>
     ```
   - Return every PR URL and note which target branch each PR uses.

## Stop And Ask

Stop and ask the user when:

- Gitflow cannot be proven.
- Production or development branch detection is ambiguous.
- The requested hotfix branch exists but is not based on production.
- Release branch targets are unknown.
- Local branch naming policy conflicts with `hotfix/<branchname>`.
- Any push would require history rewriting.
