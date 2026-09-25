from scripts.release_policy import check_pull_request, check_version


def test_release_version_matches_all_manifests_and_changelog():
    assert check_version("0.1.0") == []


def test_main_rejects_ordinary_branches_without_git_queries():
    assert check_pull_request("main", "feature/new-api") == [
        "pull requests to main must come from release/vX.Y.Z or hotfix/vX.Y.Z"
    ]


def test_develop_accepts_ordinary_branches():
    assert check_pull_request("develop", "feature/new-api") == []
