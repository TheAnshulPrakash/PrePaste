"""Persistent, per-user storage shared by the PrePaste apps.

Nothing is written beside the application executable.  Settings and local scan
history live in the current Windows user's AppData folder, so an update or a
portable copy of the project does not lose preferences.
"""

from __future__ import annotations

import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_NAME = "PrePaste"
SETTINGS_FILE_NAME = "settings.json"
HISTORY_FILE_NAME = "history.json"
VIEWER_SELECTION_FILE_NAME = "viewer_selection.json"

# The entity names are Presidio entity types.  Credential labels are kept
# separately so they can be displayed clearly in the settings experience.
PII_ENTITIES = {
    "EMAIL_ADDRESS": True,
    "PHONE_NUMBER": True,
    "CREDIT_CARD": True,
    "PERSON": False,
    "US_SSN": True,
    "LOCATION": False,
    "DATE_TIME": False,
    "ORGANIZATION": False,
    "IP_ADDRESS": False,
    "URL": False,
    "IBAN_CODE": False,
    "NRP": False,
}

CREDENTIAL_TYPES = {
    "OpenAI API key": True,
    "Anthropic API key": True,
    "Hugging Face token": True,
    "GitHub personal access token": True,
    "Google API key": True,
    "Google OAuth token": True,
    "AWS access key ID": True,
    "Stripe secret key": True,
    "Slack token": True,
    "MongoDB connection URI": True,
    "Supabase JWT": True,
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 1,
    "entities": PII_ENTITIES,
    "credential_types": CREDENTIAL_TYPES,
    "model": "en_core_web_lg",
    "language": "en",
    "confidence_threshold": 0.5,
    "scan_clipboard": True,
    "redact_on_request": True,
    "launch_at_sign_in": False,
    "show_desktop_alerts": True,
    "always_on_top": True,
    "top_margin": 24,
    "right_margin": 24,
    "keep_history": True,
    "history_limit": 100,
}


def data_directory() -> Path:
    """Return the writable data location for the current user."""
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if root:
        return Path(root) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def settings_path() -> Path:
    return data_directory() / SETTINGS_FILE_NAME


def history_path() -> Path:
    return data_directory() / HISTORY_FILE_NAME


def viewer_selection_path() -> Path:
    """Return the small, local pointer file used by the redaction viewer."""
    return data_directory() / VIEWER_SELECTION_FILE_NAME


def _deep_merge(defaults: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return fallback


def load_settings() -> dict[str, Any]:
    """Load preferences, repairing missing fields with safe defaults."""
    saved = _read_json(settings_path(), {})
    return _deep_merge(DEFAULT_SETTINGS, saved if isinstance(saved, dict) else {})


def save_settings(settings: dict[str, Any]) -> Path:
    """Atomically save settings and return the concrete path written."""
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = settings_path()
    temporary_path = path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(settings, file, indent=2, ensure_ascii=False, sort_keys=True)
    temporary_path.replace(path)
    return path


def load_history() -> list[dict[str, Any]]:
    entries = _read_json(history_path(), [])
    return entries if isinstance(entries, list) else []


def add_history_entry(
    findings: list[dict[str, Any]], text_length: int, source: str = "Manual scan"
) -> None:
    """Store metadata only — never the clipboard text or detected secrets."""
    settings = load_settings()
    if not settings.get("keep_history", True):
        return
    entries = load_history()
    entries.insert(
        0,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "finding_count": len(findings),
            "types": sorted(
                {str(item.get("entity_type", "Unknown")) for item in findings}
            ),
            "text_length": text_length,
        },
    )
    limit = max(1, int(settings.get("history_limit", 100)))
    _write_history(entries[:limit])


def add_redaction_history_entry(
    original_text: str,
    redacted_text: str,
    line_numbers: list[int],
    source: str = "Clipboard redaction",
) -> None:
    """Store one full clipboard redaction and the affected line numbers."""
    settings = load_settings()
    if not settings.get("keep_history", True):
        return

    clean_line_numbers = sorted({int(line) for line in line_numbers if int(line) > 0})
    record_id = str(uuid.uuid4())

    entries = load_history()
    entries.insert(
        0,
        {
            "id": record_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "kind": "redaction",
            "line_numbers": clean_line_numbers,
            "original_text": original_text,
            "redacted_text": redacted_text,
        },
    )
    limit = max(1, int(settings.get("history_limit", 100)))
    _write_history(entries[:limit])
    return record_id


def select_redaction_for_viewer(redaction_id: str) -> Path:
    """Atomically point the standalone viewer at a saved redaction record.

    A temporary file is written and then replaced, so the viewer never reads a
    half-written JSON document when the clipboard process and viewer overlap.
    """
    clean_id = str(redaction_id).strip()
    if not clean_id:
        raise ValueError("A redaction ID is required")

    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = viewer_selection_path()
    temporary_path = path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump({"id": clean_id}, file, indent=2)
    temporary_path.replace(path)
    return path


def clear_history() -> None:
    _write_history([])


def _write_history(entries: list[dict[str, Any]]) -> None:
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = history_path()
    temporary_path = path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(entries, file, indent=2, ensure_ascii=False)
    temporary_path.replace(path)
