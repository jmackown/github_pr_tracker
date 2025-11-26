# GitHub PR Tracker

A simple FastAPI + HTMX dashboard that shows PRs you authored or need to review, including merge status, CI rollups (head + merge commits), draft/conflict badges, and today’s merged items.

## Quickstart

1. Install uv (fast Python package/venv manager): see https://docs.astral.sh/uv/getting-started/
2. Clone and enter the repo:
   ```bash
   git clone <repo-url>
   cd github_pr_tracker
   ```
3. Install deps (creates a .venv): `uv sync`
4. Configure `.env` (all keys are prefixed `PRDASH_`):
   ```
   PRDASH_GITHUB_TOKEN=ghp_xxx
   PRDASH_GITHUB_USERNAME=your-username
   PRDASH_TRACKED_REPOS=owner/repo,owner/repo2
   PRDASH_WATCHED_PRS=owner/repo#123
   PRDASH_POLL_INTERVAL_SECONDS=15
   ```
5. Run the server (dev): `uv run uvicorn app.main:app --reload`
6. Open http://127.0.0.1:8000

## How it works

- Poller (`polling.poll_loop`) pulls PRs via GitHub GraphQL and stores them in SQLite (`prdash.db`).
- Filtering: PRs you authored, PRs where you (or your team) are requested as a reviewer, plus explicitly watched PRs.
- Data tracked: draft flag, conflict flag, review summary, head-commit CI summary, merge-commit CI summary, merged_at timestamps (merged PRs are shown if merged today).
- UI: HTMX refreshes every 10s; grouped rows:
  - PRs I need to review
  - My PRs that need review
  - My PRs that have been reviewed
  - Merged PRs (today)

## Testing

```bash
PYTHONPATH=. uv run pytest
```

## Schema note

`prdash.db` is auto-created on startup. If you pull new schema changes, drop the file or `ALTER TABLE` to add new columns (e.g., merge metadata, conflict flag).
