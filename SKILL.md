---
name: github-gitflow-hotfix-skill
description: Manage GitHub hotfix workflows for repositories that use Gitflow — prove Gitflow, create or validate a production-based hotfix branch (hotfix/KEY-n_desc with a Jira key in Jira-tracked repos), then commit, push, and open hotfix PRs back to production, development, and release branches. Use when the user asks for a Gitflow hotfix or hotfix PRs. Not for ordinary feature PRs (use pr-create) or repos that do not use Gitflow.
---

# Gitflow Hotfix

Use this workflow for Gitflow repositories when a production hotfix must be made from a hotfix branch and then proposed back to production, development, and any active release branches.

Git, attribution, and validation rules come from the `agent-policy` skill (`references/git.md`, `references/attribution.md`, `references/validation.md`). This skill adds the Gitflow-specific steps. Commits go through `git-commit`; PRs go through `pr-create`.

## Hard Gates

- First prove the repository uses Gitflow. If Gitflow cannot be determined, stop and ask the user.
- Do not assume Gitflow from a lone `develop` branch.
- Require a known production branch, usually `main` or `master`.
- Require a known development branch that differs from production, usually `develop`.
- Require hotfix branches to use `hotfix/<branchname>`. In Jira-tracked repositories (`github.com/cisco-sbg`), the name must be `hotfix/<KEY>-<number>_<description>` and match the branch regex in `agent-policy` → `references/git.md`, for example `hotfix/DISC-123_fix_timeout`. Ask for the Jira key; never invent one.
- Existing hotfix branches must be production-reachable and must not contain development-only history. If lineage is ambiguous or development-based, stop and ask the user.
- Commit, push, and create PRs only while the current branch is the hotfix branch.
- Worktrees and alternate checkouts follow `git-worktree-safety`.
- Never force push, and never push directly to `main`, `master`, `develop`, or `release/*`, without explicit approval (`agent-policy` → `references/git.md`). A non-force push of the hotfix branch itself is a safe operation.
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
scripts/gitflow_hotfix_audit.py --hotfix hotfix/DISC-123_fix_timeout --require-jira
```

The helper enforces the Jira-keyed name automatically when the remote URL is under `github.com/cisco-sbg`. Pass `--require-jira` to enforce it for any other remote.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Gitflow was proven and the hotfix branch is either absent or has valid lineage. |
| 2 | Gitflow, production branch, or development branch could not be determined. |
| 3 | The hotfix branch name is invalid (including a missing Jira key when one is required). |
| 4 | Required git repository data could not be read. |
| 5 | The hotfix branch exists but does not satisfy production lineage. |

The helper does not fetch, create branches, check out branches, or edit files. If it warns that `FETCH_HEAD` is missing or stale, run `git fetch --prune origin` and rerun the audit before creating or tracking any hotfix branch.

## Workflow

1. Prepare repository context.
   - Confirm the worktree is clean before switching or creating branches:
     ```bash
     git status --short
     ```
   - If the checkout is dirty, stop and ask. If a separate worktree seems useful, follow `git-worktree-safety` before creating one.
   - Refresh remote refs when network access is available:
     ```bash
     git fetch --prune origin
     ```
   - Read repo-local rules first: `AGENTS.md`, `.github/copilot-instructions.md`, `CLAUDE.md`, `GEMINI.md`, `CONTRIBUTING.md`, and root README files when present.

2. Establish Gitflow.
   - Identify production as exactly one of `main` or `master`, unless the user supplies a repo-specific production branch.
   - Identify development from `origin/HEAD` when it differs from production, or from root README/CONTRIBUTING Gitflow wording plus a real development branch.
   - Treat README or CONTRIBUTING wording such as `gitflow`, `git flow`, `hotfix/`, or Gitflow-style release/hotfix process descriptions as Gitflow evidence.
   - Treat `--main` and `--develop` as branch overrides only. They do not prove Gitflow by themselves.
   - If signals are missing or mixed, stop and ask the user to confirm production and development branches.

3. Resolve the hotfix branch.
   - If the user gives only a suffix, use `hotfix/<suffix>`. In Jira-tracked repos the suffix must be `<KEY>-<number>_<description>`; if the key is missing, ask for it.
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
   - Follow `agent-policy` → `references/coding-standards.md`.
   - Run applicable validation per `agent-policy` → `references/validation.md`, preferring Makefile targets. If validation tooling is absent, report that explicitly.

5. Commit and push.
   - Reconfirm the current branch:
     ```bash
     git branch --show-current
     ```
   - If it is not the expected hotfix branch, stop.
   - Commit with the `git-commit` skill. It handles identity, the branch gate, hooks, and the `Co-Authored-By:` trailer.
   - Push the hotfix branch without force. This is a safe operation and needs no confirmation:
     ```bash
     git push -u origin <hotfix-branch>
     ```
   - Never push to production, development, or release branches directly without explicit approval.

6. Create pull requests.
   - Ask the user to list release branches, or confirm that there are none.
   - Create PRs from the hotfix branch to:
     - production, such as `main` or `master`
     - development, such as `develop`
     - each user-specified release branch
   - Create each PR through the `pr-create` skill with an explicit base, one per target. It enforces `.github/pull_request_template.md`, runs validation, and adds the attribution footer from `agent-policy` → `references/attribution.md` and the Jira comment.
   - If `pr-create` is unavailable, write the filled body non-interactively (never open `$EDITOR`), end it with the attribution footer, and use explicit bases and heads:
     ```bash
     gh pr create --base main --head <hotfix-branch> --title "<title>" --body-file <body-file>
     gh pr create --base develop --head <hotfix-branch> --title "<title>" --body-file <body-file>
     gh pr create --base release/<name> --head <hotfix-branch> --title "<title>" --body-file <body-file>
     ```
   - If the direct development PR conflicts, keep the production PR as the source of truth. After the production PR merges, create a separate merge-forward branch from development (named per `agent-policy` → `references/git.md`) that merges production back into development, then open that PR to development via `pr-create`.
   - Return every PR URL and note which target branch each PR uses.

## Stop And Ask

Stop and ask the user when:

- Gitflow cannot be proven.
- Production or development branch detection is ambiguous.
- The requested hotfix branch exists but is not based on production.
- Release branch targets are unknown.
- Local branch naming policy conflicts with the required hotfix branch pattern, or the Jira key is unknown.
- Any push would require history rewriting, or would go directly to a production, development, or release branch.
- You are considering an additional worktree (see `git-worktree-safety`).
