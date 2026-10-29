"""Contract Registry — declare before you code (Battle Court step 1).

Every agent must declare, before writing code, the files, APIs and
schemas it will touch. Cross-agent conflicts are flagged here, before
coding, not after a clean git merge breaks the build.
"""
from __future__ import annotations

from .state import StateStore


def declare(store: StateStore, agent: str, files=(), apis=(), schemas=(), plan: str = "") -> dict:
    state = store.load()
    entry = {
        "agent": agent,
        "files": sorted(set(files or [])),
        "apis": sorted(set(apis or [])),
        "schemas": sorted(set(schemas or [])),
        "plan": plan,
    }
    state["contracts"].append(entry)
    store.save(state)
    return entry


def find_conflicts(store: StateStore) -> list[dict]:
    """A conflict = two different agents declaring the same file, API, or schema."""
    state = store.load()
    contracts = state["contracts"]
    conflicts: list[dict] = []
    for i, a in enumerate(contracts):
        for b in contracts[i + 1:]:
            if a["agent"] == b["agent"]:
                continue
            for kind in ("files", "apis", "schemas"):
                shared = sorted(set(a[kind]) & set(b[kind]))
                for item in shared:
                    conflicts.append(
                        {"kind": kind, "item": item, "agents": [a["agent"], b["agent"]]}
                    )
    return conflicts


def check_before_coding(store: StateStore) -> list[dict]:
    """Call before any agent writes code. Non-empty = stop and resolve first."""
    return find_conflicts(store)
