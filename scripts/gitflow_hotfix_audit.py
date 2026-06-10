#!/usr/bin/env python3
"""Audit Gitflow hotfix branch readiness without mutating the repository.

Usage:
    scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname>
    scripts/gitflow_hotfix_audit.py --hotfix hotfix/<branchname> --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


GITFLOW_DOCUMENT_PATTERNS = (
    re.compile(r"\bgit[- ]?flow\b", re.IGNORECASE),
    re.compile(r"\bhotfix/", re.IGNORECASE),
    re.compile(r"\brelease/", re.IGNORECASE),
)
HOTFIX_PATTERN = re.compile(r"^hotfix/[A-Za-z0-9._/-]+$")
PRODUCTION_CANDIDATES = ("main", "master")
DEVELOPMENT_CANDIDATES = ("develop", "development", "dev")
FETCH_HEAD_MAX_AGE_SECONDS = 24 * 60 * 60


@dataclass
class AuditResult:
    """Collect audit details and the final status code."""

    ok: bool = False
    exit_code: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    production_branch: str | None = None
    development_branch: str | None = None
    remote_default_branch: str | None = None
    hotfix_branch: str | None = None
    hotfix_valid_name: bool = False
    hotfix_exists_local: bool = False
    hotfix_exists_remote: bool = False
    hotfix_ref: str | None = None
    production_ref: str | None = None
    development_ref: str | None = None
    lineage: str = "not_checked"

    def fail(self, code: int, message: str) -> None:
        """Record a failure without lowering an existing higher-priority code."""
        self.ok = False
        self.errors.append(message)
        if self.exit_code == 0:
            self.exit_code = code

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the audit."""
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "errors": self.errors,
            "warnings": self.warnings,
            "evidence": self.evidence,
            "production_branch": self.production_branch,
            "development_branch": self.development_branch,
            "remote_default_branch": self.remote_default_branch,
            "hotfix_branch": self.hotfix_branch,
            "hotfix_valid_name": self.hotfix_valid_name,
            "hotfix_exists_local": self.hotfix_exists_local,
            "hotfix_exists_remote": self.hotfix_exists_remote,
            "hotfix_ref": self.hotfix_ref,
            "production_ref": self.production_ref,
            "development_ref": self.development_ref,
            "lineage": self.lineage,
        }


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command and capture text output."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_output(args: list[str], cwd: Path) -> str | None:
    """Return stripped git stdout, or None when the command fails."""
    result = run_git(args, cwd)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def git_success(args: list[str], cwd: Path) -> bool:
    """Return true when a git command exits successfully."""
    return run_git(args, cwd).returncode == 0


def ref_exists(ref: str, cwd: Path) -> bool:
    """Return true when a git ref resolves to a commit."""
    return git_success(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd)


def first_existing_ref(branch: str, remote: str, cwd: Path) -> str | None:
    """Return the preferred ref for a branch, checking remote before local."""
    remote_ref = f"refs/remotes/{remote}/{branch}"
    local_ref = f"refs/heads/{branch}"
    if ref_exists(remote_ref, cwd):
        return f"{remote}/{branch}"
    if ref_exists(local_ref, cwd):
        return branch
    return None


def branch_exists(branch: str, remote: str, cwd: Path) -> tuple[bool, bool]:
    """Return local and remote existence for a branch name."""
    local = ref_exists(f"refs/heads/{branch}", cwd)
    remote_exists = ref_exists(f"refs/remotes/{remote}/{branch}", cwd)
    return local, remote_exists


def remote_default_branch(remote: str, cwd: Path) -> str | None:
    """Return the local record of the remote default branch."""
    value = git_output(["symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD"], cwd)
    if not value:
        return None
    prefix = f"{remote}/"
    return value.removeprefix(prefix)


def gitflow_document_evidence(repo_root: Path) -> list[str]:
    """Return top-level documentation evidence that indicates Gitflow."""
    evidence: list[str] = []
    for path in sorted(repo_root.iterdir()):
        normalized_name = path.name.lower()
        is_candidate = normalized_name.startswith("readme") or normalized_name.startswith("contributing")
        if not path.is_file() or not is_candidate:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        matched = [pattern.pattern for pattern in GITFLOW_DOCUMENT_PATTERNS if pattern.search(text)]
        if matched:
            evidence.append(f"{path.name} mentions Gitflow-style terms")
    return evidence


def fetch_head_warning(repo_root: Path, max_age_seconds: int = FETCH_HEAD_MAX_AGE_SECONDS) -> str | None:
    """Return a warning when local remote refs may not reflect the remote."""
    fetch_head_path_text = git_output(["rev-parse", "--git-path", "FETCH_HEAD"], repo_root)
    if not fetch_head_path_text:
        return None

    fetch_head_path = Path(fetch_head_path_text)
    if not fetch_head_path.is_absolute():
        fetch_head_path = repo_root / fetch_head_path
    if not fetch_head_path.exists():
        return "No FETCH_HEAD found. Run `git fetch --prune origin` before relying on remote branch existence."

    age_seconds = time.time() - fetch_head_path.stat().st_mtime
    if age_seconds > max_age_seconds:
        return "FETCH_HEAD is older than 24 hours. Run `git fetch --prune origin` before relying on remote branch existence."
    return None


def valid_hotfix_name(branch: str) -> bool:
    """Return true when the branch follows the hotfix/<name> convention."""
    if not HOTFIX_PATTERN.match(branch):
        return False
    suffix = branch.removeprefix("hotfix/")
    invalid_parts = ("", ".", "..")
    return (
        bool(suffix)
        and not branch.endswith("/")
        and "//" not in branch
        and ".." not in branch
        and all(part not in invalid_parts for part in branch.split("/"))
    )


def detect_production_branch(
    explicit: str | None,
    remote: str,
    remote_default: str | None,
    cwd: Path,
) -> tuple[str | None, str | None, str | None]:
    """Detect the production branch or return an ambiguity message."""
    if explicit:
        if first_existing_ref(explicit, remote, cwd):
            return explicit, None, None
        return None, None, f"Explicit production branch '{explicit}' was not found locally or under {remote}."

    candidates = [branch for branch in PRODUCTION_CANDIDATES if first_existing_ref(branch, remote, cwd)]
    if len(candidates) == 1:
        return candidates[0], None, None
    if len(candidates) > 1:
        if remote_default in candidates:
            return remote_default, f"Both production candidates exist; using {remote}/HEAD ({remote_default}).", None
        return None, None, f"Both production candidates exist: {', '.join(candidates)}."
    return None, None, "No production branch candidate was found. Expected main or master."


def detect_development_branch(
    explicit: str | None,
    production: str,
    remote: str,
    remote_default: str | None,
    gitflow_evidence: list[str],
    cwd: Path,
) -> tuple[str | None, list[str], list[str], str | None]:
    """Detect the development branch and return evidence used."""
    evidence: list[str] = []
    warnings: list[str] = []
    remote_default_is_development = (
        bool(remote_default)
        and remote_default != production
        and bool(first_existing_ref(remote_default or "", remote, cwd))
    )

    if explicit:
        if explicit == production:
            return None, evidence, warnings, "Development branch must differ from production."
        if first_existing_ref(explicit, remote, cwd):
            if remote_default_is_development:
                evidence.append(f"{remote}/HEAD points to {remote_default}, which differs from production")
                if explicit != remote_default:
                    warnings.append(
                        f"Explicit development branch '{explicit}' differs from {remote}/HEAD ({remote_default})."
                    )
            evidence.extend(gitflow_evidence)
            if not evidence:
                warnings.append("Explicit development branch supplied; this is not Gitflow evidence by itself.")
            return explicit, evidence, warnings, None
        return None, evidence, warnings, f"Explicit development branch '{explicit}' was not found locally or under {remote}."

    if remote_default_is_development:
        evidence.append(f"{remote}/HEAD points to {remote_default}, which differs from production")
        return remote_default, evidence, warnings, None

    if gitflow_evidence:
        candidates = [branch for branch in DEVELOPMENT_CANDIDATES if branch != production and first_existing_ref(branch, remote, cwd)]
        if len(candidates) == 1:
            evidence.extend(gitflow_evidence)
            evidence.append(f"development branch candidate exists: {candidates[0]}")
            return candidates[0], evidence, warnings, None
        if len(candidates) > 1:
            return None, evidence, warnings, f"Multiple development branch candidates exist: {', '.join(candidates)}."

    return (
        None,
        evidence,
        warnings,
        "Could not determine a development branch from remote default or README/CONTRIBUTING Gitflow evidence. "
        f"If {remote}/HEAD is missing, run `git remote set-head {remote} -a`, or pass explicit branches with independent Gitflow documentation evidence.",
    )


def rev_list(ref: str, excluded_ref: str, cwd: Path) -> set[str] | None:
    """Return commits reachable from ref but not from excluded_ref."""
    output = git_output(["rev-list", ref, f"^{excluded_ref}"], cwd)
    if output is None:
        return None
    if not output:
        return set()
    return set(output.splitlines())


def validate_lineage(result: AuditResult, cwd: Path) -> None:
    """Validate production reachability and reject development-only history."""
    if not result.hotfix_ref or not result.production_ref or not result.development_ref:
        result.fail(4, "Cannot validate lineage because one or more refs are missing.")
        return

    if not git_success(["merge-base", "--is-ancestor", result.production_ref, result.hotfix_ref], cwd):
        result.lineage = "invalid"
        result.fail(5, f"{result.production_ref} is not an ancestor of {result.hotfix_ref}.")
        return

    hotfix_only = rev_list(result.hotfix_ref, result.production_ref, cwd)
    development_only = rev_list(result.development_ref, result.production_ref, cwd)
    if hotfix_only is None or development_only is None:
        result.lineage = "unknown"
        result.fail(4, "Could not inspect hotfix and development commit ancestry.")
        return

    overlap = hotfix_only.intersection(development_only)
    if overlap:
        result.lineage = "invalid"
        result.fail(
            5,
            "Hotfix history contains commits reachable from development but not production.",
        )
        return

    result.lineage = "valid"


def audit(args: argparse.Namespace) -> AuditResult:
    """Run the Gitflow hotfix audit."""
    result = AuditResult(hotfix_branch=args.hotfix)
    repo_root_text = git_output(["rev-parse", "--show-toplevel"], Path.cwd())
    if not repo_root_text:
        result.fail(4, "Current directory is not inside a git repository.")
        return result

    repo_root = Path(repo_root_text)
    remote = args.remote
    result.remote_default_branch = remote_default_branch(remote, repo_root)
    gitflow_evidence = gitflow_document_evidence(repo_root)
    stale_fetch_warning = fetch_head_warning(repo_root)
    if stale_fetch_warning:
        result.warnings.append(stale_fetch_warning)

    production, production_warning, production_error = detect_production_branch(
        args.main,
        remote,
        result.remote_default_branch,
        repo_root,
    )
    if production_warning:
        result.warnings.append(production_warning)
    if production_error:
        result.fail(2, production_error)
        return result
    result.production_branch = production
    result.production_ref = first_existing_ref(production or "", remote, repo_root)

    development, development_evidence, development_warnings, development_error = detect_development_branch(
        args.develop,
        production or "",
        remote,
        result.remote_default_branch,
        gitflow_evidence,
        repo_root,
    )
    result.warnings.extend(development_warnings)
    if development_error:
        result.fail(2, development_error)
        return result
    result.development_branch = development
    result.development_ref = first_existing_ref(development or "", remote, repo_root)
    result.evidence.extend(development_evidence)

    if not result.evidence:
        result.fail(2, "No strong Gitflow evidence was found.")
        return result

    result.hotfix_valid_name = valid_hotfix_name(args.hotfix)
    if not result.hotfix_valid_name:
        result.fail(3, "Hotfix branch must match hotfix/<branchname>.")
        return result

    result.hotfix_exists_local, result.hotfix_exists_remote = branch_exists(args.hotfix, remote, repo_root)
    if result.hotfix_exists_local:
        result.hotfix_ref = args.hotfix
    elif result.hotfix_exists_remote:
        result.hotfix_ref = f"{remote}/{args.hotfix}"
    else:
        result.lineage = "branch_missing_create_from_production"
        result.ok = True
        return result

    validate_lineage(result, repo_root)
    result.ok = result.exit_code == 0
    return result


def print_human(result: AuditResult) -> None:
    """Print a concise human-readable audit summary."""
    status = "PASS" if result.ok else "FAIL"
    print(f"Gitflow hotfix audit: {status}")
    print(f"Production branch: {result.production_branch or 'unknown'}")
    print(f"Development branch: {result.development_branch or 'unknown'}")
    print(f"Remote default branch: {result.remote_default_branch or 'unknown'}")
    print(f"Hotfix branch: {result.hotfix_branch}")
    print(f"Hotfix exists local: {result.hotfix_exists_local}")
    print(f"Hotfix exists remote: {result.hotfix_exists_remote}")
    print(f"Lineage: {result.lineage}")
    if result.evidence:
        print("Evidence:")
        for item in result.evidence:
            print(f"  - {item}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Audit Gitflow hotfix branch readiness.")
    parser.add_argument("--hotfix", required=True, help="Hotfix branch name, formatted as hotfix/<branchname>.")
    parser.add_argument("--remote", default="origin", help="Remote name to inspect. Defaults to origin.")
    parser.add_argument("--main", help="Explicit production branch, such as main or master.")
    parser.add_argument("--develop", help="Explicit development branch, such as develop.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    """Run the command-line audit."""
    args = parse_args()
    result = audit(args)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print_human(result)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
