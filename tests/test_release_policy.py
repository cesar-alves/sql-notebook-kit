import subprocess

from scripts import release_policy
from scripts.release_policy import HOTFIX_BRANCH, RELEASE_BRANCH


def test_release_version_matches_all_manifests_and_changelog():
    assert release_policy.check_version("0.1.0") == []


def test_main_rejects_ordinary_branches_without_git_queries():
    assert release_policy.check_pull_request("main", "feature/new-api") == [
        "pull requests to main must come from release/vX.Y.Z or hotfix/vX.Y.Z"
    ]


def test_develop_accepts_ordinary_branches():
    assert release_policy.check_pull_request("develop", "feature/new-api") == []


def test_zero_major_release_and_hotfix_branches_are_valid():
    assert RELEASE_BRANCH.fullmatch("release/v0.1.0")
    assert HOTFIX_BRANCH.fullmatch("hotfix/v0.1.1")


def test_release_branch_versions_reject_incomplete_or_leading_zero_forms():
    assert RELEASE_BRANCH.fullmatch("release/v0.1") is None
    assert RELEASE_BRANCH.fullmatch("release/v00.1.0") is None
    assert RELEASE_BRANCH.fullmatch("release/v0.01.0") is None


def _git_result(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout, "")


def test_release_branch_accepts_develop_ancestry_beyond_main(monkeypatch):
    monkeypatch.setattr(release_policy, "_is_ancestor", lambda ancestor, commit: True)

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        if args == ("git", "merge-base", "HEAD", "origin/develop"):
            return _git_result("develop-commit\n")
        if args == ("git", "rev-parse", "origin/main"):
            return _git_result("main-commit\n")
        raise AssertionError(args)

    monkeypatch.setattr(release_policy, "_run", run)

    assert (
        release_policy.check_pull_request("main", "release/v0.1.0", commit="HEAD")
        == []
    )


def test_release_branch_rejects_no_develop_ancestry_beyond_main(monkeypatch):
    monkeypatch.setattr(release_policy, "_is_ancestor", lambda ancestor, commit: True)
    monkeypatch.setattr(
        release_policy, "_run", lambda *args: _git_result("main-commit\n")
    )

    assert release_policy.check_pull_request(
        "main", "release/v0.1.0", commit="HEAD"
    ) == [
        "release/v0.1.0 has no release ancestry beyond origin/main; cut it from develop"
    ]


def test_hotfix_branch_accepts_current_main_ancestry(monkeypatch):
    monkeypatch.setattr(release_policy, "_is_ancestor", lambda ancestor, commit: True)
    monkeypatch.setattr(release_policy, "check_version", lambda expected: [])
    monkeypatch.setattr(
        release_policy, "_run", lambda *args: _git_result("main-commit\n")
    )

    assert (
        release_policy.check_pull_request("main", "hotfix/v0.1.1", commit="HEAD")
        == []
    )
