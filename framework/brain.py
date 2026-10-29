"""Brain — local, file-first memory. No vector DB, no external service.

Events live in <root>/.framework/state.json under brain_events, so the
Brain is human-readable, git-friendly, and travels with the workspace.
Every run records: model + skills used + MCP tools called + Brain
context consulted + battle verdicts + learning events — so a run is
auditable, not just a prompt that produced output.

Search is plain substring search over event JSON (stdlib only). A
vector index is a later step only if it earns it; it is not claimed
here.
"""
from __future__ import annotations

import json

from .state import StateStore


def record(store: StateStore, event_type: str, detail: dict) -> dict:
    state = store.load()
    event = {"id": len(state["brain_events"]) + 1, "type": event_type, **detail}
    state["brain_events"].append(event)
    store.save(state)
    return event


def events(store: StateStore, event_type: str | None = None) -> list[dict]:
    state = store.load()
    evs = state["brain_events"]
    return [e for e in evs if event_type is None or e.get("type") == event_type]


def search(store: StateStore, term: str, event_type: str | None = None) -> list[dict]:
    """Case-insensitive substring search over all Brain events."""
    needle = term.lower()
    return [e for e in events(store, event_type)
            if needle in json.dumps(e, default=str).lower()]


def show(store: StateStore, index: int) -> dict:
    """Show one event by its id, or by 0-based position if no id matches."""
    evs = events(store)
    for e in evs:
        if e.get("id") == index:
            return e
    if 0 <= index < len(evs):
        return evs[index]
    raise ValueError(f"no Brain event with id/index {index}")


def relevant(store: StateStore, task: str = "", agent: str = "", limit: int = 5) -> list[dict]:
    """Brain context for a run: most recent events mentioning the task
    words, or by the same agent — newest first, capped. This is what
    an agent 'remembers' before it starts; it is context, not a claim
    that the past run was correct."""
    evs = list(reversed(events(store)))
    if not task and not agent:
        return evs[:limit]
    words = [w.lower() for w in task.split() if len(w) > 2]
    picked = []
    for e in evs:
        blob = json.dumps(e, default=str).lower()
        if (agent and e.get("agent") == agent) or any(w in blob for w in words):
            picked.append(e)
        if len(picked) >= limit:
            break
    return picked
