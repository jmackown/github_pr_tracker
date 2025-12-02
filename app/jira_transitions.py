from typing import List, Optional

from .config import settings

ALLOWED_TARGETS = {"in development", "in review", "awaiting qa"}


def _filter_allowed(statuses: List[str], fallback: List[str]) -> List[str]:
    seen = set()
    allowed = []
    for s in statuses:
        if not s:
            continue
        lower = s.lower()
        if lower in ALLOWED_TARGETS and lower not in seen:
            allowed.append(s)
            seen.add(lower)
    if allowed:
        return allowed
    return fallback


def expected_statuses_for_lane(title: str, is_draft: bool) -> List[str]:
    """
    Returns the list of expected Jira statuses for a given board lane and draft state.
    """
    if title == "My PRs that need review":
        if is_draft:
            draft = settings.jira_status_list(settings.jira_status_draft, [])
            return _filter_allowed(draft, [])
        needs_review = settings.jira_status_list(settings.jira_status_needs_review, [])
        return _filter_allowed(needs_review, [])
    if title == "My PRs that have been reviewed":
        reviewed = settings.jira_status_list(settings.jira_status_reviewed, [])
        return _filter_allowed(reviewed, [])
    if title.startswith("Merged PRs"):
        merged = settings.jira_status_list(settings.jira_status_merged, [])
        merged = _filter_allowed(merged, [])
        return merged
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
