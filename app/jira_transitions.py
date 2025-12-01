from typing import List, Optional

from .config import settings


def expected_statuses_for_lane(title: str, is_draft: bool) -> List[str]:
    """
    Returns the list of expected Jira statuses for a given board lane and draft state.
    """
    if title == "My PRs that need review":
        if is_draft:
            return settings.jira_status_list(settings.jira_status_draft, ["In Development"])
        return settings.jira_status_list(settings.jira_status_needs_review, ["In Review"])
    if title == "My PRs that have been reviewed":
        return settings.jira_status_list(settings.jira_status_reviewed, ["In Review"])
    if title.startswith("Merged PRs"):
        return settings.jira_status_list(
            settings.jira_status_merged,
            ["Ready for QA", "QA", "In QA", "Released", "Done", "Closed", "Production"],
        )
    return []


def pick_transition(transitions: List[dict], targets: List[str]) -> Optional[str]:
    """
    Given a list of transitions from Jira and target statuses/names,
    return the first matching transition id, or None.
    """
    if not transitions or not targets:
        return None
    targets_lower = [t.lower() for t in targets]

    for t in transitions:
        to_name = (t.get("to", {}) or {}).get("name", "")
        if to_name and to_name.lower() in targets_lower:
            return t.get("id")

    for t in transitions:
        name = t.get("name", "")
        if name and name.lower() in targets_lower:
            return t.get("id")

    return None
