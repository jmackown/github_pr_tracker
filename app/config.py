from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """App configuration loaded from environment / .env."""

    github_token: str
    github_username: str

    # Comma-separated values, e.g. "owner/repo,owner/repo"
    tracked_repos: str | None = None

    # Explicit PRs: "owner/repo#123,owner/repo#456"
    watched_prs: str | None = None

    poll_interval_seconds: int = 15

    database_url: str = "sqlite+aiosqlite:///./prdash.db"

    jira_base_url: str | None = None  # e.g. https://your-domain.atlassian.net
    jira_email: str | None = None
    jira_api_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PRDASH_",
        extra="ignore",
    )

    def repo_list(self) -> List[tuple[str, str]]:
        if not self.tracked_repos:
            return []
        repos = []
        for item in self.tracked_repos.split(","):
            item = item.strip()
            if not item:
                continue
            owner, name = item.split("/", 1)
            repos.append((owner, name))
        return repos

    def watched_pr_list(self) -> List[tuple[str, str, int]]:
        if not self.watched_prs:
            return []
        prs: List[tuple[str, str, int]] = []
        for item in self.watched_prs.split(","):
            item = item.strip()
            if not item:
                continue
            repo_part, num_str = item.split("#", 1)
            owner, name = repo_part.split("/", 1)
            prs.append((owner, name, int(num_str)))
        return prs

    @property
    def jira_enabled(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)


settings = Settings()
