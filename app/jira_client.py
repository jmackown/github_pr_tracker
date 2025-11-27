import asyncio
import json
import re
import urllib.request
from base64 import b64encode
from typing import Optional

from .config import settings


JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+)[\s-]?(\d+)\b", re.IGNORECASE)


def parse_jira_key(text: str) -> Optional[str]:
    match = JIRA_KEY_RE.search(text or "")
    if match:
        return f"{match.group(1).upper()}-{match.group(2)}"
    return None


def parse_jira_keys(text: str) -> list[str]:
    if not text:
        return []
    keys = {f"{m[0].upper()}-{m[1]}" for m in JIRA_KEY_RE.findall(text)}
    return list(keys)


async def fetch_jira_issue(key: str) -> Optional[dict]:
    if not settings.jira_enabled:
        return None

    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/3/issue/{key}?fields=summary,status"

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
        payload = json.loads(data)
        fields = payload.get("fields", {})
        status = fields.get("status", {}).get("name")
        summary = fields.get("summary")
        return {
            "key": key,
            "status": status,
            "summary": summary,
            "url": f"{base}/browse/{key}",
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] error fetching {key}: {exc!r}")
        return None
