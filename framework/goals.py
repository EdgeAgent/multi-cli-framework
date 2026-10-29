"""Goals, Tasks, Deliverables, Environments — stored locally in state.

No new database, no new service. These are lists in
<root>/.framework/state.json, plus Brain events, so they travel with
the workspace and survive a restart. They are the planning tabs the
TUI renders (Goals / Tasks / What's Next) and the CLI lists.

An environment is the one-action bundle for a new agent: section +
agent + sandbox + model + skills + MCP tools + Brain context, created
live without restarting the framework. It reuses the dynamic
spawn/delete machinery — it does not invent a second registry.
"""
from __future__ import annotations

from . import brain
from .sandbox import create_sandbox
from .state import StateStore


def _next_id(items: list[dict]) -> int:
    return max((i.get("id", 0) for i in items), default=0) + 1


def add_goal(store: StateStore, title: str, progress: int = 0) -> dict:
    state = store.load()
    item = {"id": _next_id(state["goals"]), "title": title,
            "progress": max(0, min(100, progress)),
            "status": "done" if progress >= 100 else "active"}
    state["goals"].append(item)
    store.save(state)
    brain.record(store, "goal_added", item)
    return item


def set_goal_progress(store: StateStore, goal_id: int, progress: int) -> dict:
    state = store.load()
    for item in state["goals"]:
        if item["id"] == goal_id:
            item["progress"] = max(0, min(100, progress))
            item["status"] = "done" if progress >= 100 else "active"
            store.save(state)
            brain.record(store, "goal_progress", item)
            return item
    raise ValueError(f"unknown goal: {goal_id}")


def add_task(store: StateStore, title: str, owner: str = "", section: str = "") -> dict:
    state = store.load()
    item = {"id": _next_id(state["tasks"]), "title": title, "status": "todo",
            "owner": owner, "section": section}
    state["tasks"].append(item)
    store.save(state)
    brain.record(store, "task_added", item)
    return item


def set_task_status(store: StateStore, task_id: int, status: str) -> dict:
    if status not in ("todo", "doing", "done", "blocked"):
        raise ValueError(f"unknown task status: {status}")
    state = store.load()
    for item in state["tasks"]:
        if item["id"] == task_id:
            item["status"] = status
            store.save(state)
            brain.record(store, "task_status", item)
            return item
    raise ValueError(f"unknown task: {task_id}")


def add_deliverable(store: StateStore, title: str) -> dict:
    """Deliverables are ordered by insertion (due_order) — What's Next
    is simply deliverables in due order, open ones first."""
    state = store.load()
    item = {"id": _next_id(state["deliverables"]), "title": title,
            "due_order": len(state["deliverables"]) + 1, "status": "pending"}
    state["deliverables"].append(item)
    store.save(state)
    brain.record(store, "deliverable_added", item)
    return item


def set_deliverable_status(store: StateStore, deliverable_id: int, status: str) -> dict:
    if status not in ("pending", "done", "blocked"):
        raise ValueError(f"unknown deliverable status: {status}")
    state = store.load()
    for item in state["deliverables"]:
        if item["id"] == deliverable_id:
            item["status"] = status
            store.save(state)
            brain.record(store, "deliverable_status", item)
            return item
    raise ValueError(f"unknown deliverable: {deliverable_id}")


def whats_next(store: StateStore) -> list[dict]:
    """Next deliverables due, in order, open ones first."""
    state = store.load()
    items = sorted(state["deliverables"], key=lambda d: d["due_order"])
    return [i for i in items if i["status"] != "done"] + [i for i in items if i["status"] == "done"]


def add_environment(store: StateStore, name: str, model: str = "local",
                    skills: list[str] | None = None,
                    mcp_tools: list[str] | None = None) -> dict:
    """One action: section + agent + sandbox + model + skills + MCP.

    Live, no restart. The section/agent go through the normal registry
    (so spawn/delete, TUI panes, and kill switch all work), the
    sandbox is created immediately, and the bundle is recorded in
    state['environments'] and in the Brain. Deleting the environment
    uses the normal section delete (archive by default).
    """
    section = store.add_section(name, role="builder", model=model)
    agent = store.spawn_agent(name, "agent-1", model=model)
    sandbox = create_sandbox(store, name, "agent-1")
    env = {"name": name, "section": name, "agent": "agent-1", "model": model,
           "skills": skills or [], "mcp_tools": mcp_tools or [],
           "sandbox": str(sandbox), "status": "active"}
    state = store.load()
    state.setdefault("environments", {})[name] = env
    store.save(state)
    brain.record(store, "environment_added", env)
    return env
