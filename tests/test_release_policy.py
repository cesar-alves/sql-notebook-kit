from scripts.release_policy import (
    HOTFIX_BRANCH,
    RELEASE_BRANCH,
    check_pull_request,
    check_version,
)


def test_release_version_matches_all_manifests_and_changelog():
    assert check_version("0.1.0") == []


def test_main_rejects_ordinary_branches_without_git_queries():
    assert check_pull_request("main", "feature/new-api") == [
        "pull requests to main must come from release/vX.Y.Z or hotfix/vX.Y.Z"
    ]


def test_develop_accepts_ordinary_branches():
    assert check_pull_request("develop", "feature/new-api") == []


def test_zero_major_release_and_hotfix_branches_are_valid():
    assert RELEASE_BRANCH.fullmatch("release/v0.1.0")
    assert HOTFIX_BRANCH.fullmatch("hotfix/v0.1.1")


def test_release_branch_versions_reject_incomplete_or_leading_zero_forms():
    assert RELEASE_BRANCH.fullmatch("release/v0.1") is None
    assert RELEASE_BRANCH.fullmatch("release/v00.1.0") is None
    assert RELEASE_BRANCH.fullmatch("release/v0.01.0") is None
