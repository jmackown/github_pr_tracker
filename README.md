# GitHub PR Tracker

A simple FastAPI + HTMX dashboard that shows PRs you authored or need to review, including merge status, CI rollups (head + merge commits), draft/conflict badges, and today’s merged items.

## Quickstart

1) Install uv (fast Python package/venv manager): see https://docs.astral.sh/uv/getting-started/
2) Clone and enter the repo:
   ```bash
   git clone <repo-url>
   cd github_pr_tracker
   ```
3) Install deps (creates a .venv): `uv sync`
4) Copy config and fill non-sensitive defaults:
   ```bash
   cp config.example.yml config.yml
   # edit config.yml with your username, tracked repos, etc.
   ```
5) Set secrets in `.env` (tokens only; env wins over config file):
   ```bash
   PRDASH_CONFIG_FILE=./config.yml
   PRDASH_GITHUB_TOKEN=ghp_xxx
   PRDASH_JIRA_API_TOKEN=atlassian-token   # optional
   ```
   Other settings in `.env` are optional; see `.env.example` for keys.
6) Run the server: `uv run prdash --reload` (or `uv run uvicorn app.main:app --reload`)
7) Open http://127.0.0.1:8000

## How it works

- Poller (`polling.poll_loop`) pulls PRs via GitHub GraphQL and stores them in SQLite (`prdash.db`).
- Filtering: PRs you authored, PRs where you (or your team) are requested as a reviewer, plus explicitly watched PRs.
- Data tracked: draft flag, conflict flag, review summary, head-commit CI summary, merge-commit CI summary, merged_at timestamps (merged PRs are shown if merged today).
- UI: HTMX refreshes every 10s; grouped rows:
  - PRs I need to review
  - My PRs that need review
  - My PRs that have been reviewed
  - Merged PRs (today)
  - Each card shows a “size” tier (trivial/small/.../massive) based on additions/deletions/files/commits, and an optional Jira badge with status/components if configured (keys from title or commit messages).

### Theming

Styles are driven by CSS variables in `app/templates/base.html` under theme blocks (e.g., `.theme-midnight`, `.theme-sunset`). Use the top-right theme toggle to switch. To add another theme, create a `.theme-yourname` block with variables and append its class to the `data-themes` list on the toggle button; the script will rotate through all listed themes.

Current themes: midnight, sunset.

## Testing

```bash
PYTHONPATH=. uv run pytest
```

## Schema note

`prdash.db` is auto-created on startup. It is no longer auto-deleted; if you pull new schema changes, drop the file or `ALTER TABLE` to add new columns (e.g., merge metadata, conflict flag, size tier, jira fields). If you need a clean slate, set `PRDASH_DB_RESET_ON_START=true` (only for local/testing).

## Optional Jira integration

If you want Jira status badges, add these to `.env`:
```
PRDASH_JIRA_BASE_URL=https://your-domain.atlassian.net
PRDASH_JIRA_EMAIL=you@example.com
PRDASH_JIRA_API_TOKEN=atlassian-api-token
# Optional: enable components/status badge; defaults false
PRDASH_JIRA_COMPONENTS_ENABLED=false
# Optional: limit matching to certain projects (comma-separated prefixes, e.g., PLAN,ABC)
PRDASH_JIRA_PROJECT_PREFIXES=
# Optional: expected statuses per lane (comma-separated); defaults shown
PRDASH_JIRA_STATUS_NEEDS_REVIEW=In Review
PRDASH_JIRA_STATUS_DRAFT=In Development
PRDASH_JIRA_STATUS_REVIEWED=In Review
PRDASH_JIRA_STATUS_MERGED=Ready for QA,QA,In QA,Released,Done,Closed,Production
# Optional: map Jira components to repos (YAML map in config.yml)
# In config.yml:
# jira_component_repo_map:
#   ExternalCommunications: external-communication
#   GenRev: ds-genrev
# Env fallback (comma-separated pairs): PRDASH_JIRA_COMPONENT_REPO_MAP=ExternalCommunications:external-communication,GenRev:ds-genrev
# Optional: transition map for multi-step Jira moves (YAML file)
# jira_transition_map_file: docs/jira_workflow_transitions.yml
```
The title must contain a ticket key (e.g., `ABC-123`); Jira calls are skipped entirely if these aren’t set.

## Install/run for others

- Clone and `uv sync`, then `uv run prdash --reload` (or `uv run uvicorn app.main:app --reload`).
- Package entrypoint: `prdash` is defined in `pyproject.toml`, so `pip install .` then `prdash` works too.
- Config via `.env` (see `.env.example`). Jira is optional; the app runs fine without it.
