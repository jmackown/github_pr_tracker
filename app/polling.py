import asyncio
from datetime import datetime
from typing import Dict, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import PullRequest, SessionLocal
from .github_client import (
    build_gql_client,
    fetch_repo_prs,
    fetch_single_pr,
)
from .jira_client import fetch_jira_issue


async def upsert_pr(session: AsyncSession, data: Dict) -> None:
    key: Tuple[str, str, int] = (
        data["repo_owner"],
        data["repo_name"],
        data["number"],
    )

    stmt = select(PullRequest).where(
        PullRequest.repo_owner == key[0],
        PullRequest.repo_name == key[1],
        PullRequest.number == key[2],
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    is_mine = (data["author"].lower() == settings.github_username.lower())

    if existing:
        existing.title = data["title"]
        existing.state = data["state"]
        existing.is_draft = data["is_draft"]
        existing.review_status = data["review_status"]
        existing.ci_summary = data["ci_summary"]
        existing.merge_ci_summary = data.get("merge_ci_summary")
        existing.last_commit_sha = data["last_commit_sha"]
        existing.merge_commit_sha = data.get("merge_commit_sha")
        existing.has_conflicts = data.get("has_conflicts", False)
        existing.size_tier = data.get("size_tier", 0)
        existing.jira_key = data.get("jira_key")
        existing.jira_keys = data.get("jira_keys")
        existing.jira_status = data.get("jira_status")
        existing.jira_summary = data.get("jira_summary")
        existing.jira_url = data.get("jira_url")
        existing.jira_last_synced_at = data.get("jira_last_synced_at")
        existing.updated_at = data["updated_at"]
        existing.merged_at = data.get("merged_at")
        existing.last_synced_at = datetime.utcnow()
        existing.raw = data["raw"]
        existing.is_mine = is_mine
    else:
        session.add(
            PullRequest(
                repo_owner=data["repo_owner"],
                repo_name=data["repo_name"],
                number=data["number"],
                title=data["title"],
                author=data["author"],
                url=data["url"],
                state=data["state"],
                is_draft=data["is_draft"],
                review_status=data["review_status"],
                ci_summary=data["ci_summary"],
                merge_ci_summary=data.get("merge_ci_summary"),
                last_commit_sha=data["last_commit_sha"],
                merge_commit_sha=data.get("merge_commit_sha"),
                has_conflicts=data.get("has_conflicts", False),
                size_tier=data.get("size_tier", 0),
                jira_key=data.get("jira_key"),
                jira_keys=data.get("jira_keys"),
                jira_status=data.get("jira_status"),
                jira_summary=data.get("jira_summary"),
                jira_url=data.get("jira_url"),
                jira_last_synced_at=data.get("jira_last_synced_at"),
                is_mine=is_mine,
                updated_at=data["updated_at"],
                merged_at=data.get("merged_at"),
                last_synced_at=datetime.utcnow(),
                raw=data["raw"],
            )
        )


async def poll_once() -> None:
    async with SessionLocal() as session:
        client = build_gql_client()

        # All open PRs in tracked repos
        for owner, name in settings.repo_list():
            prs = await fetch_repo_prs(client, owner, name)
            for pr in prs:
                author = pr["author"].lower()
                reviewers = [r.lower() for r in pr.get("requested_reviewers", [])]
                review_teams = [t.lower() for t in pr.get("requested_review_teams", [])]

                if settings.jira_enabled and pr.get("jira_key"):
                    issue = await fetch_jira_issue(pr["jira_key"])
                    if issue:
                        pr["jira_status"] = issue.get("status")
                        pr["jira_summary"] = issue.get("summary")
                        pr["jira_url"] = issue.get("url")
                        pr["jira_last_synced_at"] = datetime.utcnow()

                if (
                    author == settings.github_username.lower()
                    or settings.github_username.lower() in reviewers
                    or review_teams  # include team review requests
                ):
                    await upsert_pr(session, pr)

        # Explicit watched PRs
        for owner, name, number in settings.watched_pr_list():
            pr = await fetch_single_pr(client, owner, name, number)
            if pr:
                if settings.jira_enabled and pr.get("jira_key"):
                    issue = await fetch_jira_issue(pr["jira_key"])
                    if issue:
                        pr["jira_status"] = issue.get("status")
                        pr["jira_summary"] = issue.get("summary")
                        pr["jira_url"] = issue.get("url")
                        pr["jira_last_synced_at"] = datetime.utcnow()
                await upsert_pr(session, pr)

        await session.commit()


async def poll_loop() -> None:
    interval = settings.poll_interval_seconds
    while True:
        try:
            await poll_once()
        except Exception as exc:  # tighten later
            print(f"[poll_loop] Error: {exc!r}")
        await asyncio.sleep(interval)
