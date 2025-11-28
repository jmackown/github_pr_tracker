import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import click
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import SessionLocal, init_db, PullRequest
from .config import settings
from .polling import poll_loop

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
async def on_startup():
    await init_db()
    asyncio.create_task(poll_loop())


async def get_session() -> AsyncSession:
    return SessionLocal()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    async with SessionLocal() as session:
        groups, last_sync = await load_pr_groups(session)
        last_sync_str = format_ts(last_sync)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "groups": groups,
            "now": datetime.utcnow(),
            "settings": settings,
            "last_sync": last_sync,
            "last_sync_str": last_sync_str,
        },
    )


@app.get("/fragments/pr-table", response_class=HTMLResponse)
async def pr_table(request: Request):
    async with SessionLocal() as session:
        groups, last_sync = await load_pr_groups(session)
        last_sync_str = format_ts(last_sync)

    return templates.TemplateResponse(
        "_pr_table.html",
        {
            "request": request,
            "groups": groups,
            "now": datetime.utcnow(),
            "settings": settings,
            "last_sync": last_sync,
            "last_sync_str": last_sync_str,
        },
    )


def categorize_prs(prs):
    def is_reviewed(status: str | None) -> bool:
        if not status:
            return False
        lowered = status.lower()
        return lowered in {"approved", "changes requested", "reviewed"}

    review_me = []
    my_needs_review = []
    my_reviewed = []
    merged = []

    for pr in prs:
        if pr.state == "MERGED":
            merged.append(pr)
            continue

        if pr.is_mine:
            if is_reviewed(pr.review_status):
                my_reviewed.append(pr)
            else:
                my_needs_review.append(pr)
        else:
            review_me.append(pr)

    return [
        ("PRs I need to review", review_me),
        ("My PRs that need review", my_needs_review),
        ("My PRs that have been reviewed", my_reviewed),
        ("Merged PRs (today)", merged),
    ]


async def load_pr_groups(session: AsyncSession):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(PullRequest)
        .where(
            (PullRequest.state != "MERGED")
            | (PullRequest.merged_at >= today_start)
        )
        .order_by(PullRequest.is_mine.desc(), PullRequest.updated_at.desc())
    )
    result = await session.execute(stmt)
    prs = result.scalars().all()
    last_sync = None
    for pr in prs:
        if pr.last_synced_at and (last_sync is None or pr.last_synced_at > last_sync):
            last_sync = pr.last_synced_at
    return categorize_prs(prs), last_sync


def format_ts(dt: datetime | None) -> str:
    if not dt:
        return "n/a"
    london = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/London"))
    return london.strftime("%b %d, %Y %H:%M")


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind")
@click.option("--port", default=8000, show_default=True, help="Port to bind")
@click.option("--reload/--no-reload", default=False, show_default=True, help="Enable autoreload")
def cli(host: str, port: int, reload: bool):
    """Run the PR dashboard server."""
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
