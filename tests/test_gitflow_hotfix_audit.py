"""Tests for the read-only Gitflow hotfix audit helper.

Usage:
    python3.11 -B -m unittest tests/test_gitflow_hotfix_audit.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "gitflow_hotfix_audit.py"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command in a test repository."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(cmd)}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def write(path: Path, text: str) -> None:
    """Write text to a test file."""
    path.write_text(text, encoding="utf-8")


def init_repo(path: Path, readme: str = "Plain repository.\n") -> None:
    """Initialize a test repository with one commit on main."""
    run(["git", "init", "-b", "main"], path)
    run(["git", "config", "user.name", "Skill Test"], path)
    run(["git", "config", "user.email", "skill-test@example.invalid"], path)
    write(path / "README.md", readme)
    run(["git", "add", "README.md"], path)
    run(["git", "commit", "-m", "initial"], path)


def add_remote(repo: Path, root: Path, name: str, default_branch: str = "main") -> Path:
    """Add a local bare origin and push main."""
    bare = root / f"{name}.git"
    run(["git", "init", "--bare", str(bare)], root)
    run(["git", "remote", "add", "origin", str(bare)], repo)
    run(["git", "push", "-u", "origin", "main"], repo)
    run(["git", "--git-dir", str(bare), "symbolic-ref", "HEAD", f"refs/heads/{default_branch}"], repo)
    run(["git", "remote", "set-head", "origin", default_branch], repo)
    return bare


def add_branch(repo: Path, name: str, filename: str, content: str) -> None:
    """Create and push a branch with one unique commit."""
    run(["git", "switch", "-c", name], repo)
    write(repo / filename, content)
    run(["git", "add", filename], repo)
    run(["git", "commit", "-m", f"add {name}"], repo)
    run(["git", "push", "-u", "origin", name], repo)


def audit(repo: Path, *args: str) -> tuple[int, dict[str, object]]:
    """Run the audit helper and return its exit code and JSON payload."""
    result = run([str(SCRIPT), "--json", *args], repo, check=False)
    return result.returncode, json.loads(result.stdout)


class GitflowHotfixAuditTest(unittest.TestCase):
    """Exercise the audit helper against temporary Git repositories."""

    def test_explicit_develop_does_not_prove_gitflow(self) -> None:
        """Fail when only explicit branches identify a development branch."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp)
            repo = root / "plain"
            repo.mkdir()
            init_repo(repo)
            add_remote(repo, root, "plain-origin")
            add_branch(repo, "foo", "foo.txt", "foo branch\n")

            code, payload = audit(repo, "--hotfix", "hotfix/fix", "--main", "main", "--develop", "foo")

            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertIn("No strong Gitflow evidence", "\n".join(payload["errors"]))
            self.assertIn("not Gitflow evidence", "\n".join(payload["warnings"]))

    def test_documentation_evidence_with_develop_passes(self) -> None:
        """Pass when docs prove Gitflow and a development branch exists."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp)
            repo = root / "gitflow"
            repo.mkdir()
            init_repo(repo, "This repository uses Gitflow with hotfix/ and release/ branches.\n")
            add_remote(repo, root, "gitflow-origin")
            add_branch(repo, "develop", "develop.txt", "development branch\n")

            code, payload = audit(repo, "--hotfix", "hotfix/new-fix")

            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["development_branch"], "develop")
            self.assertIn("README.md mentions Gitflow-style terms", payload["evidence"])

    def test_origin_head_resolves_main_master_ambiguity(self) -> None:
        """Use origin HEAD when both production branch names exist."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp)
            repo = root / "both"
            repo.mkdir()
            init_repo(repo, "Gitflow process uses hotfix/ and release/ branches.\n")
            bare = add_remote(repo, root, "both-origin", default_branch="main")
            add_branch(repo, "master", "master.txt", "legacy branch\n")
            add_branch(repo, "develop", "develop.txt", "development branch\n")
            run(["git", "--git-dir", str(bare), "symbolic-ref", "HEAD", "refs/heads/main"], repo)
            run(["git", "remote", "set-head", "origin", "main"], repo)

            code, payload = audit(repo, "--hotfix", "hotfix/new-fix")

            self.assertEqual(code, 0)
            self.assertEqual(payload["production_branch"], "main")
            self.assertIn("using origin/HEAD", "\n".join(payload["warnings"]))

    def test_hotfix_from_develop_fails_lineage(self) -> None:
        """Reject hotfix history that contains development-only commits."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp)
            repo = root / "bad-lineage"
            repo.mkdir()
            init_repo(repo, "Gitflow process uses hotfix/ and release/ branches.\n")
            bare = add_remote(repo, root, "lineage-origin")
            add_branch(repo, "develop", "develop.txt", "development branch\n")
            run(["git", "--git-dir", str(bare), "symbolic-ref", "HEAD", "refs/heads/develop"], repo)
            run(["git", "remote", "set-head", "origin", "develop"], repo)
            add_branch(repo, "hotfix/from-develop", "bad.txt", "bad hotfix\n")

            code, payload = audit(repo, "--hotfix", "hotfix/from-develop")

            self.assertEqual(code, 5)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["lineage"], "invalid")

    def test_missing_fetch_head_warns_without_fetching(self) -> None:
        """Warn when fetch metadata is absent while preserving success."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp)
            repo = root / "fetch-warning"
            repo.mkdir()
            init_repo(repo, "Gitflow process uses hotfix/ and release/ branches.\n")
            add_remote(repo, root, "warning-origin")
            add_branch(repo, "develop", "develop.txt", "development branch\n")

            code, payload = audit(repo, "--hotfix", "hotfix/new-fix")

            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertIn("No FETCH_HEAD found", "\n".join(payload["warnings"]))

    def test_stale_fetch_head_warns_without_fetching(self) -> None:
        """Warn when fetch metadata is old while preserving success."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp)
            repo = root / "stale-fetch-warning"
            repo.mkdir()
            init_repo(repo, "Gitflow process uses hotfix/ and release/ branches.\n")
            add_remote(repo, root, "stale-warning-origin")
            add_branch(repo, "develop", "develop.txt", "development branch\n")
            fetch_head = repo / ".git" / "FETCH_HEAD"
            write(fetch_head, "old fetch metadata\n")
            old_timestamp = time.time() - (48 * 60 * 60)
            os.utime(fetch_head, (old_timestamp, old_timestamp))

            code, payload = audit(repo, "--hotfix", "hotfix/new-fix")

            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertIn("older than 24 hours", "\n".join(payload["warnings"]))

    def test_invalid_hotfix_branch_name_fails(self) -> None:
        """Reject branch names outside hotfix namespace."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp)
            repo = root / "invalid-name"
            repo.mkdir()
            init_repo(repo, "Gitflow process uses hotfix/ and release/ branches.\n")
            add_remote(repo, root, "invalid-origin")
            add_branch(repo, "develop", "develop.txt", "development branch\n")

            code, payload = audit(repo, "--hotfix", "feature/fix")

            self.assertEqual(code, 3)
            self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
