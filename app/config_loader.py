import json
from pathlib import Path
from typing import Any, Dict

import yaml


def load_config_file(path: str | None) -> Dict[str, Any]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}

    try:
        if file_path.suffix.lower() in {".yml", ".yaml"}:
            return yaml.safe_load(file_path.read_text()) or {}
        if file_path.suffix.lower() == ".json":
            return json.loads(file_path.read_text())
    except Exception as exc:  # noqa: BLE001
        print(f"[config] failed to load {path}: {exc!r}")
    return {}
