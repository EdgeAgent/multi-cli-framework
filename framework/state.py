"""Live registry state: sections, agents, contracts, runs, brain events.

State lives in <root>/.framework/state.json — a plain JSON file, not a
database, so it is human-readable and git-friendly. The registry is the
single source of truth for dynamic add/delete: changing it hot-reloads
only that section, never the whole framework.
"""
from __future__ import annotations

import json
from pathlib import Path


def state_dir(root: str | Path) -> Path:
    return Path(root) / ".framework"


def default_state() -> dict:
    return {
        "version": "0.1.0-skeleton",
        "sections": {},  # name -> {role, model, status}
        "agents": {},  # "section/agent" -> {model, role, status}
        "contracts": [],  # {agent, files[], apis[], schemas[], plan}
        "runs": [],
        "battles": [],
        "brain_events": [],
        "mcp_servers": {},  # name -> {command, transport, tools[], allow[]}
        "goals": [],  # {id, title, progress, status}
        "tasks": [],  # {id, title, status, owner, section}
        "deliverables": [],  # {id, title, due_order, status}
        "environments": {},  # name -> {section, agent, model, skills[], mcp_tools[], sandbox}
        "cron_jobs": [],  # scheduler jobs, see scheduler.py
        "tombstones": [],  # deleted sections, kept so the TUI can show them without crashing
        "learning_proposals": [],
        "router_overrides": {},
        "killed": False,
    }


class StateStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.dir = state_dir(root)
        self.path = self.dir / "state.json"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "sandboxes").mkdir(exist_ok=True)
        (self.dir / "archive").mkdir(exist_ok=True)
        (self.dir / "staged").mkdir(exist_ok=True)
        if not self.path.exists():
            self.save(default_state())

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            data = default_state()
        merged = default_state()
        merged.update(data)
        return merged

    def save(self, state: dict) -> None:
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True))

    # --- sections / agents -------------------------------------------------
    def add_section(self, name: str, role: str = "builder", model: str = "local") -> dict:
        state = self.load()
        if name in state["sections"]:
            raise ValueError(f"section already exists: {name}")
        state["sections"][name] = {"role": role, "model": model, "status": "active"}
        self.save(state)
        return state["sections"][name]

    def delete_section(self, name: str, archive: str = "") -> dict:
        """Remove from the live registry only. Archiving is done by the
        caller (sandbox.archive) before this is called — delete never
        silently wipes, it only unregisters."""
        state = self.load()
        if name not in state["sections"]:
            raise ValueError(f"unknown section: {name}")
        removed = state["sections"].pop(name)
        state["agents"] = {
            k: v for k, v in state["agents"].items() if not k.startswith(name + "/")
        }
        # Tombstone: the TUI shows this and keeps every other pane running.
        # Deleting a section mid-run must never crash the watch screen.
        from datetime import datetime, timezone

        state["tombstones"].append(
            {
                "section": name,
                "deleted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "archive": archive,
                "status": "deleted",
            }
        )
        self.save(state)
        return removed

    def spawn_agent(self, section: str, name: str, model: str = "local", role: str = "builder") -> dict:
        state = self.load()
        if section not in state["sections"]:
            raise ValueError(f"unknown section: {section}")
        key = f"{section}/{name}"
        if key in state["agents"]:
            raise ValueError(f"agent already exists: {key}")
        state["agents"][key] = {"model": model, "role": role, "status": "running"}
        self.save(state)
        return state["agents"][key]

    def set_agent_status(self, section: str, name: str, status: str) -> None:
        state = self.load()
        key = f"{section}/{name}"
        if key not in state["agents"]:
            raise ValueError(f"unknown agent: {key}")
        state["agents"][key]["status"] = status
        self.save(state)

    def kill_all(self) -> None:
        state = self.load()
        state["killed"] = True
        for agent in state["agents"].values():
            agent["status"] = "stopped"
        for section in state["sections"].values():
            section["status"] = "stopped"
        self.save(state)
