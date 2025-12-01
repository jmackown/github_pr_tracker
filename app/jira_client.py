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
    url = f"{base}/rest/api/3/issue/{key}?fields=summary,status,components,assignee"

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
    assignee = fields.get("assignee") or {}
    return {
        "key": key,
        "status": status,
        "summary": summary,
        "url": f"{base}/browse/{key}",
        "components": components,
        "assignee": {
            "displayName": assignee.get("displayName"),
            "emailAddress": assignee.get("emailAddress"),
            "accountId": assignee.get("accountId"),
        },
    }


async def resolve_account_id() -> Optional[str]:
    if settings.jira_account_id:
        return settings.jira_account_id
    query = settings.jira_email or settings.jira_username
    if not query:
        return None

    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/3/user/search?query={urllib.parse.quote(query)}"

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
        users = json.loads(data)
        if not users:
            return None
        return users[0].get("accountId")
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] error resolving account id: {exc!r}")
        return None


async def fetch_project_components(project_key: str) -> list[dict]:
    if not settings.jira_enabled:
        return []

    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/3/project/{project_key}/components"

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
        return payload or []
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] error fetching project components for {project_key}: {exc!r}")
        return []


async def add_components_to_issue(key: str, component_ids: list[str]) -> bool:
    if not settings.jira_enabled or not component_ids:
        return False

    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/3/issue/{key}"

    auth = f"{settings.jira_email}:{settings.jira_api_token}".encode()
    token = b64encode(auth).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = json.dumps(
        {
            "update": {
                "components": [{"add": {"id": cid}} for cid in component_ids],
            }
        }
    ).encode()

    def _post():
        req = urllib.request.Request(url, headers=headers, data=payload, method="PUT")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read()

    try:
        await asyncio.to_thread(_post)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] error adding components to {key}: {exc!r}")
        return False


async def assign_issue(key: str) -> bool:
    if not settings.jira_enabled:
        return False
    account_id = await resolve_account_id()
    if not account_id:
        print("[jira] no account id found for assignment")
        return False

    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/3/issue/{key}/assignee"

    auth = f"{settings.jira_email}:{settings.jira_api_token}".encode()
    token = b64encode(auth).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = json.dumps({"accountId": account_id}).encode()

    def _put():
        req = urllib.request.Request(url, headers=headers, data=payload, method="PUT")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read()

    try:
        await asyncio.to_thread(_put)
        print(f"[jira] assigned {key} to {settings.jira_email}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] error assigning {key}: {exc!r}")
        return False


async def fetch_jira_transitions(key: str) -> list[dict]:
    if not settings.jira_enabled:
        return []

    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/3/issue/{key}/transitions?expand=transitions.fields"

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
        return payload.get("transitions", []) or []
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] error fetching transitions for {key}: {exc!r}")
        return []


async def transition_jira_issue(key: str, transition_id: str) -> bool:
    if not settings.jira_enabled:
        return False

    base = settings.jira_base_url.rstrip("/")
    url = f"{base}/rest/api/3/issue/{key}/transitions"

    auth = f"{settings.jira_email}:{settings.jira_api_token}".encode()
    token = b64encode(auth).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = json.dumps({"transition": {"id": transition_id}}).encode()

    def _post():
        req = urllib.request.Request(url, headers=headers, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read()

    try:
        await asyncio.to_thread(_post)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[jira] error transitioning {key}: {exc!r}")
        return False
