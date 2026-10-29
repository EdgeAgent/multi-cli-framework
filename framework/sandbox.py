"""Sandbox — one isolated environment per agent.

Default: one directory per agent under .framework/sandboxes/<section>/<agent>.
If the root is a git repo, callers may also create a git worktree there;
the skeleton uses directories so it works without git, and never lets
two parallel agents share a working directory.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from .state import StateStore


def sandbox_path(store: StateStore, section: str, agent: str) -> Path:
    return store.dir / "sandboxes" / section / agent


def create_sandbox(store: StateStore, section: str, agent: str) -> Path:
    path = sandbox_path(store, section, agent)
    path.mkdir(parents=True, exist_ok=True)
    return path


def archive_sandbox(store: StateStore, section: str, agent: str | None = None, reason: str = "") -> Path:
    """Freeze a sandbox into .framework/archive/. Archive, never wipe,
    is the default for delete. Returns the archive path."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if agent:
        src = sandbox_path(store, section, agent)
        dest = store.dir / "archive" / f"{section}-{agent}-{stamp}"
    else:
        src = store.dir / "sandboxes" / section
        dest = store.dir / "archive" / f"{section}-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    if reason:
        (dest / "ARCHIVE_REASON.txt").write_text(reason)
    return dest


def wipe_sandbox(store: StateStore, section: str, confirm: str = "") -> bool:
    """Destructive wipe, twice-confirmed only: the section must already
    have been archived (caller checks), and confirm must equal the
    section name exactly. There is no wipe-all. Returns True if wiped."""
    if confirm != section:
        return False
    target = store.dir / "sandboxes" / section
    if target.exists():
        shutil.rmtree(target)
    return True
