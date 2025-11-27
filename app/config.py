import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """App configuration loaded from environment / .env."""

    config_file: str | None = None  # optional path to YAML/JSON

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
    jira_project_prefixes: str | None = None  # comma-separated; optional filter
    jira_status_needs_review: str | None = None  # comma-separated expected statuses
    jira_status_draft: str | None = None
    jira_status_reviewed: str | None = None
    jira_status_merged: str | None = None

    db_reset_on_start: bool = False  # set true to delete/recreate SQLite on startup

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

    def jira_status_list(self, value: str | None, default: list[str]) -> list[str]:
        if value is None:
            return default
        return [v.strip() for v in value.split(",") if v.strip()]


def build_settings() -> Settings:
    # Load optional config file for non-sensitive defaults
    from .config_loader import load_config_file

    config_path = os.environ.get("PRDASH_CONFIG_FILE")
    if not config_path and Path("config.yml").exists():
        config_path = "config.yml"
    file_data = load_config_file(config_path)
    return Settings(config_file=config_path, **file_data)


settings = build_settings()
