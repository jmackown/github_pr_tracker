import asyncio
import json
import re
import urllib.request
import urllib.error
from base64 import b64encode
from typing import Optional

from .config import settings


JIRA_KEY_RE = re.compile(r"\b([A-Z]+)[\s-]?(\d+)\b", re.IGNORECASE)


def parse_jira_key(text: str) -> Optional[str]:
    match = JIRA_KEY_RE.search(text or "")
    if match:
        key = f"{match.group(1).upper()}-{match.group(2)}"
        if _is_allowed_key(key):
            return key
    return None


def parse_jira_keys(text: str) -> list[str]:
    if not text:
        return []
    keys = {f"{m[0].upper()}-{m[1]}" for m in JIRA_KEY_RE.findall(text)}
    return [k for k in keys if _is_allowed_key(k)]


def _allowed_prefixes() -> list[str]:
    prefixes = settings.jira_project_prefixes
    if not prefixes:
        return []
    return [p.strip().upper() for p in prefixes.split(",") if p.strip()]


def _is_allowed_key(key: str) -> bool:
    allowed = _allowed_prefixes()
    if not allowed:
        return True
    prefix = key.split("-", 1)[0]
    return prefix in allowed


async def fetch_jira_issue(key: str) -> Optional[dict]:
    if not settings.jira_enabled:
        return None

    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/3/issue/{key}?fields=summary,status,components"

    auth = f"{settings.jira_email}:{settings.jira_api_token}".encode()
    token = b64encode(auth).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    def _fetch():
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read()

    try:
        data = await asyncio.to_thread(_fetch)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "key": key,
                "status": "not found",
                "summary": None,
                "url": f"{base}/browse/{key}",
            }
        print(f"[jira] error fetching {key}: {exc!r}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] error fetching {key}: {exc!r}")
        return None

    payload = json.loads(data)
    fields = payload.get("fields", {})
    status = fields.get("status", {}).get("name")
    summary = fields.get("summary")
    components = [c.get("name") for c in fields.get("components", []) if c.get("name")]
    return {
        "key": key,
        "status": status,
        "summary": summary,
        "url": f"{base}/browse/{key}",
        "components": components,
    }
