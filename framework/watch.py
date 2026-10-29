"""Live watch — split-pane status text + JSON stream.

Watch is read-only by default. Pause / takeover / stop / approve are
explicit CLI actions, not typing into an agent's pane. A deleted
section's pane is shown as a tombstone, and other panes keep running.
"""
from __future__ import annotations

import json

from .state import StateStore


def render_status(store: StateStore) -> str:
    state = store.load()
    lines = ["=" * 60, "BATTLE COURT — LIVE WATCH", "=" * 60]
    lines.append(f"[BOSS] sections={len(state['sections'])} agents={len(state['agents'])} killed={state['killed']}")
    for name, section in state["sections"].items():
        lines.append(f"--- SECTION: {name} [{section['status']}] role={section['role']} model={section['model']} ---")
        agents = {k: v for k, v in state["agents"].items() if k.startswith(name + "/")}
        if not agents:
            lines.append("    (no agents — empty section, still registered)")
        for key, agent in agents.items():
            lines.append(f"    [{agent['status']}] {key} model={agent['model']}")
    for run in state["runs"][-3:]:
        lines.append(f"[RUN] {run['task']}: " + ", ".join(f"{r['agent']}={r['status']}" for r in run["results"]))
    for battle in state["battles"][-3:]:
        lines.append(f"[COURT] {battle['battle_id']}: {battle['outcome']} winner={battle['winner']}")
    return "\n".join(lines)


def stream_json(store: StateStore) -> str:
    return json.dumps(store.load(), indent=2, sort_keys=True)
