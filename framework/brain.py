"""Brain — local, file-first memory. No vector DB in the skeleton."""
from __future__ import annotations

from .state import StateStore


def record(store: StateStore, event_type: str, detail: dict) -> dict:
    state = store.load()
    event = {"type": event_type, **detail}
    state["brain_events"].append(event)
    store.save(state)
    return event


def events(store: StateStore, event_type: str | None = None) -> list[dict]:
    state = store.load()
    evs = state["brain_events"]
    return [e for e in evs if event_type is None or e.get("type") == event_type]
