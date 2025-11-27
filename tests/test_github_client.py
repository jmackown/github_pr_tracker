from app.github_client import summarise_ci, summarise_merge_ci, summarise_reviews


def test_summarise_reviews_no_reviews():
    node = {"reviews": {"nodes": []}}
    assert summarise_reviews(node) == "needs review"


def test_summarise_reviews_dismissed_only():
    node = {"reviews": {"nodes": [{"state": "DISMISSED"}]}}
    assert summarise_reviews(node) == "needs re-review"


def test_summarise_reviews_approved():
    node = {"reviews": {"nodes": [{"state": "APPROVED"}]}}
    assert summarise_reviews(node) == "approved"


def test_summarise_ci_no_commits():
    node = {"commits": {"nodes": []}}
    assert summarise_ci(node).startswith("no commits")


def test_summarise_merge_ci_no_commit():
    node = {}
    assert summarise_merge_ci(node) is None


def test_summarise_merge_ci_with_rollup():
    node = {
        "mergeCommit": {
            "statusCheckRollup": {
                "state": "FAILED",
                "contexts": {"nodes": [{}, {}]},
            }
        }
    }
    assert summarise_merge_ci(node) == "FAILED (2 merge checks)"
