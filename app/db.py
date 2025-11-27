from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Boolean, JSON
from sqlalchemy.engine import make_url

from .config import settings

Base = declarative_base()


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_owner: Mapped[str] = mapped_column(String, index=True)
    repo_name: Mapped[str] = mapped_column(String, index=True)
    number: Mapped[int] = mapped_column(Integer, index=True)

    title: Mapped[str] = mapped_column(String)
    author: Mapped[str] = mapped_column(String, index=True)
    url: Mapped[str] = mapped_column(String)

    state: Mapped[str] = mapped_column(String)  # OPEN / CLOSED / MERGED
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)

    review_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ci_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    merge_ci_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    last_commit_sha: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    merge_commit_sha: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    has_conflicts: Mapped[bool] = mapped_column(Boolean, default=False)
    size_tier: Mapped[int] = mapped_column(Integer, default=0)
    jira_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    jira_keys: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    jira_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    jira_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    jira_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    jira_last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_mine: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime)
    merged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    raw: Mapped[dict] = mapped_column(JSON)

    def key(self):
        return (self.repo_owner, self.repo_name, self.number)


engine = create_async_engine(settings.database_url, future=True, echo=False)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    url = make_url(settings.database_url)
    if url.drivername.startswith("sqlite") and url.database:
        db_path = Path(url.database)
        if db_path.exists():
            db_path.unlink()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
