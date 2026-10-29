"""Skills — reusable playbooks agents run off, not just a model + prompt.

A skill is a Markdown file in skills/ with:
  # <Name>
  <one-paragraph description>
  Tools: tool-a, tool-b
  - step 1
  - step 2

Shipped skills live in <repo>/skills/. A workspace can add its own in
<root>/skills/ — workspace skills win on a name clash. Loading a skill
never executes code: it returns text + an allow-list. An agent run
records every skill it used in the Brain, so a run is auditable:
model + skills + MCP tools + Brain context, not just a prompt.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import brain
from .state import StateStore


def _shipped_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "skills"


def skill_dirs(root) -> list[Path]:
    dirs = []
    ws = Path(root) / "skills"
    if ws not in dirs:
        dirs.append(ws)
    if _shipped_dir() not in dirs:
        dirs.append(_shipped_dir())
    return dirs


def parse_skill(text: str, name: str, path: str = "") -> dict:
    lines = [ln.strip() for ln in text.splitlines()]
    title = name
    description = ""
    tools: list[str] = []
    steps: list[str] = []
    for ln in lines:
        if ln.startswith("# "):
            title = ln[2:].strip()
        elif ln.lower().startswith("tools:"):
            tools = [t.strip() for t in ln.split(":", 1)[1].split(",") if t.strip()]
        elif ln.startswith("- ") or ln[:2].isdigit() and ". " in ln[:4]:
            steps.append(ln.lstrip("- ").split(". ", 1)[-1].strip() if ". " in ln[:4] else ln[2:].strip())
        elif ln and not description and not ln.startswith("#"):
            description = ln
    return {"name": name, "title": title, "description": description,
            "tools": tools, "steps": steps, "path": path, "text": text}


def list_skills(store: StateStore) -> list[dict]:
    seen: dict[str, dict] = {}
    for d in skill_dirs(store.root):
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            skill = parse_skill(f.read_text(encoding="utf-8"), f.stem, str(f))
            seen.setdefault(skill["name"], skill)  # workspace dir is first, so it wins
    return list(seen.values())


def get_skill(store: StateStore, name: str) -> dict:
    for skill in list_skills(store):
        if skill["name"] == name:
            return skill
    raise ValueError(f"unknown skill: {name}")


def add_skill(store: StateStore, source: str) -> dict:
    src = Path(source)
    if not src.exists():
        raise ValueError(f"skill file not found: {source}")
    dest_dir = Path(store.root) / "skills"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy(src, dest)
    skill = parse_skill(dest.read_text(encoding="utf-8"), dest.stem, str(dest))
    brain.record(store, "skill_added", {"skill": skill["name"], "path": str(dest)})
    return skill


def use_skill(store: StateStore, agent: str, skill_name: str) -> dict:
    """Record that an agent used a skill. Returns the skill playbook."""
    skill = get_skill(store, skill_name)
    brain.record(store, "skill_use", {"agent": agent, "skill": skill_name,
                                       "tools": skill["tools"]})
    return skill
