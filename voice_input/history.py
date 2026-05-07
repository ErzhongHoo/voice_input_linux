from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path


MAX_HISTORY_ENTRIES = 100


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    created_at: str
    text: str
    asr_provider: str = ""


def default_history_path() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "voice-input-linux" / "history.json"


def load_history(path: str | Path | None = None) -> list[HistoryEntry]:
    history_path = Path(path).expanduser() if path is not None else default_history_path()
    if not history_path.exists():
        return []

    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    entries: list[HistoryEntry] = []
    for raw_entry in payload:
        if not isinstance(raw_entry, dict):
            continue
        text = str(raw_entry.get("text", "")).strip()
        created_at = str(raw_entry.get("created_at", "")).strip()
        if not text or not created_at:
            continue
        entries.append(
            HistoryEntry(
                created_at=created_at,
                text=text,
                asr_provider=str(raw_entry.get("asr_provider", "")).strip(),
            )
        )
    return entries


def append_history(
    text: str,
    asr_provider: str = "",
    path: str | Path | None = None,
    max_entries: int = MAX_HISTORY_ENTRIES,
) -> list[HistoryEntry]:
    value = text.strip()
    if not value:
        return load_history(path)

    entry = HistoryEntry(
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        text=value,
        asr_provider=asr_provider,
    )
    entries = [entry, *load_history(path)][:max(1, max_entries)]
    write_history(entries, path)
    return entries


def clear_history(path: str | Path | None = None) -> None:
    write_history([], path)


def write_history(entries: list[HistoryEntry], path: str | Path | None = None) -> None:
    history_path = Path(path).expanduser() if path is not None else default_history_path()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(entry) for entry in entries]
    temporary_path = history_path.with_name(f"{history_path.name}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(history_path)
