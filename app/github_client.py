from datetime import datetime
from typing import Any, Dict, List

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from .config import settings

GITHUB_API_URL = "https://api.github.com/graphql"


def build_gql_client() -> Client:
    transport = AIOHTTPTransport(
        url=GITHUB_API_URL,
        headers={"Authorization": f"Bearer {settings.github_token}"}
    )
    return Client(transport=transport, fetch_schema_from_transport=False)


PR_LIST_QUERY = gql("""
query RepoPRs($owner: String!, $name: String!, $first: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      first: $first,
      states: [OPEN, MERGED],
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      nodes {
        number
        title
        url
        author { login }
        isDraft
        state
        mergeStateStatus
        updatedAt
        mergedAt
        
        reviewRequests(first: 10) {
          nodes {
            requestedReviewer {
              ... on User {
                login
              }
              ... on Team {
                slug
              }
            }
          }
        }

        reviews(last: 10) {
          nodes {
            author { login }
            state
          }
        }
        commits(last: 1) {
          nodes {
            commit {
              oid
              statusCheckRollup {
                state
                contexts(first: 10) {
                  nodes {
                    __typename
                    ... on CheckRun {
                      name
                      status
                      conclusion
                    }
                    ... on StatusContext {
                      context
                      state
                    }
                  }
                }
              }
            }
          }
        }
        mergeCommit {
          oid
          statusCheckRollup {
            state
            contexts(first: 10) {
              nodes {
                __typename
                ... on CheckRun {
                  name
                  status
                  conclusion
                }
                ... on StatusContext {
                  context
                  state
                }
              }
            }
          }
        }
      }
    }
  }
}
""")

PR_SINGLE_QUERY = gql("""
query SinglePR($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      title
      url
      author { login }
      isDraft
      state
      mergeStateStatus
      updatedAt
      mergedAt
      reviews(last: 10) {
        nodes {
          author { login }
          state
        }
      }
      reviewRequests(first: 10) {
          nodes {
            requestedReviewer {
              ... on User {
                login
              }
              ... on Team {
                slug
              }
            }
          }
        }
      commits(last: 1) {
        nodes {
          commit {
            oid
            statusCheckRollup {
              state
              contexts(first: 10) {
                nodes {
                  __typename
                  ... on CheckRun {
                    name
                    status
                    conclusion
                  }
                  ... on StatusContext {
                    context
                    state
                  }
                }
              }
            }
          }
        }
      }
      mergeCommit {
        oid
        statusCheckRollup {
          state
          contexts(first: 10) {
            nodes {
              __typename
              ... on CheckRun {
                name
                status
                conclusion
              }
              ... on StatusContext {
                context
                state
              }
            }
          }
        }
      }
    }
  }
}
""")


def summarise_commit_rollup(rollup: Dict[str, Any] | None, label: str = "checks") -> str:
    if not rollup:
        return f"no {label}"

    state = rollup.get("state") or "UNKNOWN"
    contexts = rollup.get("contexts", {}).get("nodes", [])
    return f"{state} ({len(contexts)} {label})"


def summarise_ci(node: Dict[str, Any]) -> str:
    commits = node.get("commits", {}).get("nodes", [])
    if not commits:
        return "no commits"

    commit = commits[0]["commit"]
    rollup = commit.get("statusCheckRollup")
    return summarise_commit_rollup(rollup)


def summarise_merge_ci(node: Dict[str, Any]) -> str | None:
    merge_commit = node.get("mergeCommit")
    if not merge_commit:
        return None

    rollup = merge_commit.get("statusCheckRollup")
    return summarise_commit_rollup(rollup, label="merge checks")


def summarise_reviews(node: Dict[str, Any]) -> str:
    reviews = node.get("reviews", {}).get("nodes", [])
    dismissed_present = any(r.get("state") == "DISMISSED" for r in reviews)
    states = [
        r["state"]
        for r in reviews
        if r.get("state") and r.get("state") != "DISMISSED"
    ]

    if not states:
        return "needs re-review" if dismissed_present else "needs review"

    if "APPROVED" in states:
        return "approved"
    if "CHANGES_REQUESTED" in states:
        return "changes requested"

    return states[-1] if states else "reviewed"


def parse_iso_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def map_pr_nodes(owner: str, name: str, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    mapped = []

    for node in nodes:
        log = node["author"]["login"] if node.get("author") else "unknown"

        requested = []
        requested_teams = []
        for rr in node.get("reviewRequests", {}).get("nodes", []):
            user = rr.get("requestedReviewer")
            if user and "login" in user:
                requested.append(user["login"])
            if user and "slug" in user:
                requested_teams.append(user["slug"])

        merged_at = parse_iso_dt(node["mergedAt"]) if node.get("mergedAt") else None
        merge_commit = node.get("mergeCommit") or {}

        merge_state = (node.get("mergeStateStatus") or "").upper()
        has_conflicts = (merge_state == "DIRTY")

        mapped.append(
            {
                "repo_owner": owner,
                "repo_name": name,
                "number": node["number"],
                "title": node["title"],
                "url": node["url"],
                "author": log,
                "state": node["state"],
                "is_draft": node["isDraft"],
                "review_status": summarise_reviews(node),
                "ci_summary": summarise_ci(node),
                "merge_ci_summary": summarise_merge_ci(node),
                "last_commit_sha": (
                    node.get("commits", {})
                    .get("nodes", [{}])[0]
                    .get("commit", {})
                    .get("oid")
                ),
                "merge_commit_sha": merge_commit.get("oid"),
                "has_conflicts": has_conflicts,
                "updated_at": parse_iso_dt(node["updatedAt"]),
                "merged_at": merged_at,
                "raw": node,
                "requested_reviewers": requested,
                "requested_review_teams": requested_teams,
            }
        )
    return mapped


async def fetch_repo_prs(client: Client, owner: str, name: str, first: int = 20):
    variables = {"owner": owner, "name": name, "first": first}
    result = await client.execute_async(PR_LIST_QUERY, variable_values=variables)
    repo = result["repository"]
    if not repo:
        return []
    return map_pr_nodes(owner, name, repo["pullRequests"]["nodes"])


async def fetch_single_pr(client: Client, owner: str, name: str, number: int):
    variables = {"owner": owner, "name": name, "number": number}
    result = await client.execute_async(PR_SINGLE_QUERY, variable_values=variables)

    repo = result["repository"]
    if not repo or not repo["pullRequest"]:
        return None

    return map_pr_nodes(owner, name, [repo["pullRequest"]])[0]
