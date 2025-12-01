import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import click
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from .db import SessionLocal, init_db, PullRequest
from .config import settings
from .polling import poll_loop, match_components
from .jira_client import (
    fetch_jira_issue,
    fetch_jira_transitions,
    transition_jira_issue,
    fetch_project_components,
    add_components_to_issue,
)
from .jira_transitions import expected_statuses_for_lane, pick_transition

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


def load_transition_map():
    path = settings.jira_transition_map_file
    if not path:
        return {}
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
            return data
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] failed to load transition map {path}: {exc!r}")
        return {}


async def apply_transition_by_name(key: str, transitions: list[dict], name: str) -> bool:
    name_lower = name.lower()
    tid = None
    for t in transitions:
        if t.get("name", "").lower() == name_lower:
            tid = t.get("id")
            break
        if (t.get("to", {}) or {}).get("name", "").lower() == name_lower:
            tid = t.get("id")
            break
    if not tid:
        # fallback: contains match
        for t in transitions:
            if name_lower in t.get("name", "").lower():
                tid = t.get("id")
                break
            if name_lower in (t.get("to", {}) or {}).get("name", "").lower():
                tid = t.get("id")
                break
    if not tid:
        print(f"[jira] no transition matches name '{name}'. Available: {[ (tr.get('id'), tr.get('name'), (tr.get('to') or {}).get('name')) for tr in transitions ]}")
        return False
    if not tid:
        return False
    print(f"[jira] applying step transition {tid} via name '{name}'")
    return await transition_jira_issue(key, tid)


def hardcoded_path(target: str):
    target_lower = target.lower()
    if target_lower == "in review":
        return [
            ("awaiting refinement", "451", "Ready for Development"),
            ("ready for dev", "461", "Add to Cycle/Sprint"),
            ("awaiting development", "21", "Start Development"),
            ("in development", "491", "In Review"),
        ]
    if target_lower == "awaiting qa":
        return [
            ("awaiting refinement", "451", "Ready for Development"),
            ("ready for dev", "461", "Add to Cycle/Sprint"),
            ("awaiting development", "21", "Start Development"),
            ("in development", "491", "In Review"),
            ("in review", "611", "No design review necessary"),
        ]
    return []


async def refresh_pr_jira(session: AsyncSession, key: str, issue: dict | None):
    if not issue:
        return
    stmt = select(PullRequest).where(PullRequest.jira_key == key)
    pr_obj = (await session.execute(stmt)).scalar_one_or_none()
    if not pr_obj:
        return
    comps = issue.get("components") or []
    pr_obj.jira_status = issue.get("status")
    pr_obj.jira_summary = issue.get("summary")
    pr_obj.jira_url = issue.get("url")
    pr_obj.jira_last_synced_at = datetime.utcnow()
    pr_obj.jira_components = comps
    pr_obj.jira_components_match = match_components(
        {"repo_name": pr_obj.repo_name}, comps
    )
    pr_obj.raw["jira_components"] = comps


@app.post("/jira/{key}/transition")
async def jira_transition(
    request: Request,
    key: str,
    target: str = Form(...),
    lane: str = Form(...),
    is_draft: bool = Form(False),
):
    if not settings.jira_enabled:
        raise HTTPException(status_code=400, detail="Jira not configured")

    # Safety: only allow for PRs owned by current user
    async with SessionLocal() as session:
        pr_match = await session.execute(
            select(PullRequest).where(PullRequest.jira_key == key, PullRequest.is_mine.is_(True))
        )
        if not pr_match.scalars().first():
            raise HTTPException(status_code=403, detail="Not allowed to transition this issue")

    targets = expected_statuses_for_lane(lane, is_draft)
    if not targets:
        raise HTTPException(status_code=400, detail="No target statuses for lane")

    transitions = await fetch_jira_transitions(key)
    transition_id = pick_transition(transitions, targets)
    issue = await fetch_jira_issue(key)
    current_status = (issue or {}).get("status")
    print(f"[jira] transition {key}: current={current_status}, target={targets}, direct_id={transition_id}")

    if not transition_id:
        trans_map = load_transition_map().get("transitions_into", {})
        path_map = load_transition_map().get("path_to_in_review", {})
        hc_path = hardcoded_path(target)
        max_steps = 6
        for _ in range(max_steps):
            transitions = await fetch_jira_transitions(key)
            transition_id = pick_transition(transitions, targets)
            if transition_id:
                print(f"[jira] applying direct transition {transition_id} to {targets}")
                if not await transition_jira_issue(key, transition_id):
                    raise HTTPException(status_code=500, detail="Transition failed")
                issue = await fetch_jira_issue(key)
                break

            # Candidate steps: hardcoded path + configured transitions_into + path_to_in_review (if applicable)
            candidate_steps = []
            candidate_steps.extend([{"from": a, "id": b, "via": c} for a, b, c in hc_path])
            for tgt, step_list in trans_map.items():
                candidate_steps.extend(step_list)
            if target.lower() == "in review" and path_map:
                candidate_steps.extend(path_map.get("transitions", []))

            matched_step = None
            for step in candidate_steps:
                if step.get("from", "").lower() == (current_status or "").lower():
                    matched_step = step
                    break

            if not matched_step:
                print(f"[jira] no step from {current_status}, available steps: {candidate_steps}")
                raise HTTPException(status_code=400, detail="No matching transition for target status")

            via = matched_step.get("via") or matched_step.get("action") or matched_step.get("lands_in")
            forced_id = matched_step.get("id")
            if forced_id:
                print(f"[jira] applying forced transition id {forced_id} ({via}) from {current_status}")
                if not await transition_jira_issue(key, forced_id):
                    raise HTTPException(status_code=400, detail=f"Cannot apply step {via or forced_id}")
            else:
                if not via:
                    print(f"[jira] matched step from {current_status} missing transition hint")
                    raise HTTPException(status_code=400, detail="No matching transition for target status")
                if not await apply_transition_by_name(key, transitions, via):
                    raise HTTPException(status_code=400, detail=f"Cannot apply step {via}")

            issue = await fetch_jira_issue(key)
            current_status = (issue or {}).get("status", current_status)
    else:
        print(f"[jira] applying direct transition {transition_id} to {targets}")
        if not await transition_jira_issue(key, transition_id):
            raise HTTPException(status_code=500, detail="Transition failed")
        issue = await fetch_jira_issue(key)

    # Render with live Jira data; persistence will be handled by the poller
    groups, last_sync = [], None
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


@app.post("/jira/{key}/components/fix")
async def jira_fix_components(
    request: Request,
    key: str,
    repo: str = Form(...),
):
    if not settings.jira_enabled or not settings.jira_components_enabled:
        raise HTTPException(status_code=400, detail="Jira components not enabled")

    async with SessionLocal() as session:
        pr_match = await session.execute(
            select(PullRequest).where(PullRequest.jira_key == key, PullRequest.is_mine.is_(True))
        )
        if not pr_match.scalars().first():
            raise HTTPException(status_code=403, detail="Not allowed to edit components for this issue")

    issue = await fetch_jira_issue(key)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    project_key = key.split("-", 1)[0]
    desired = []
    repo_lower = repo.lower()
    for comp, repo_name in settings.jira_component_map().items():
        if repo_name == repo_lower:
            desired.append(comp)
    if not desired:
        raise HTTPException(status_code=400, detail="No component mapping for repo")

    existing = issue.get("components") or []
    missing = [c for c in desired if c.lower() not in [e.lower() for e in existing]]
    if not missing:
        # Nothing to do; return current table
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

    project_components = await fetch_project_components(project_key)
    name_to_id = {c.get("name", "").lower(): c.get("id") for c in project_components}
    ids_to_add = [name_to_id[c.lower()] for c in missing if c.lower() in name_to_id]
    if not ids_to_add:
        raise HTTPException(status_code=400, detail="Desired components not found in project")

    ok = await add_components_to_issue(key, ids_to_add)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to add components")

    # Render with live Jira data; persistence will be handled by the poller
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


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind")
@click.option("--port", default=8000, show_default=True, help="Port to bind")
@click.option("--reload/--no-reload", default=False, show_default=True, help="Enable autoreload")
def cli(host: str, port: int, reload: bool):
    """Run the PR dashboard server."""
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
