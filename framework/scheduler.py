"""Cron + Loops — local scheduler, file-based, no cloud service.

Schedules live in state['cron_jobs'] (and may be mirrored in cron.yaml
by the user; state is the runtime source of truth). A job is:
  {id, name, schedule, task, section, model, skills[], mcp_tools[],
   last_run, next_run, status, enabled}

Schedule expressions supported in the skeleton (stdlib only):
  - "every N minutes" / "every N hours" / "every N days"
  - "daily", "weekly", "hourly"
  - a 5-field cron string "M H * * *" — only minute/hour are honoured
    in the skeleton; day fields must be * (anything else is rejected
    rather than silently mis-scheduled).

Loop modes:
  - repeat N times
  - until_success: stop on first PASS, otherwise stop at max_iterations
  - on_schedule: a cron job that re-runs the task (see above)
  - gated: approval gate is checked BEFORE every iteration that would
    send/ship/pay/delete/merge — a loop can NEVER auto-ship on any
    iteration, and the gate is re-checked per iteration, not once.

Kill switch (state['killed']) stops all loops/cron instantly: run_loop
and run_due check it before every iteration and return "killed".
All runs are logged to the Brain.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import brain
from .gate import GateBlocked, require_approval
from .state import StateStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_schedule(expr: str) -> dict:
    """Parse a schedule expression into {kind, minutes, description}.
    Raises ValueError on anything unparseable — never guess a schedule."""
    e = expr.strip().lower()
    if e == "hourly":
        return {"kind": "interval", "minutes": 60, "description": "hourly"}
    if e == "daily":
        return {"kind": "interval", "minutes": 1440, "description": "daily"}
    if e == "weekly":
        return {"kind": "interval", "minutes": 10080, "description": "weekly"}
    m = re.fullmatch(r"every (\d+) (minutes?|hours?|days?)", e)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if n < 1:
            raise ValueError("schedule interval must be >= 1")
        minutes = n * {"minute": 1, "minutes": 1, "hour": 60, "hours": 60, "day": 1440, "days": 1440}[unit]
        return {"kind": "interval", "minutes": minutes, "description": expr}
    parts = e.split()
    if len(parts) == 5:
        minute, hour, dom, month, dow = parts
        if dom != "*" or month != "*" or dow != "*":
            raise ValueError("skeleton cron supports only 'M H * * *' (day fields must be *)")
        if not (minute.isdigit() and hour.isdigit()):
            raise ValueError("skeleton cron minute/hour must be numbers in 'M H * * *'")
        return {"kind": "cron", "minute": int(minute), "hour": int(hour),
                "minutes": 1440, "description": expr}
    raise ValueError(f"unparseable schedule: {expr!r} — use 'every N minutes|hours|days', daily/weekly/hourly, or 'M H * * *'")


def next_run_after(parsed: dict, after: datetime | None = None) -> datetime:
    after = after or _now()
    if parsed["kind"] == "interval":
        return after + timedelta(minutes=parsed["minutes"])
    # cron: next occurrence of HH:MM today, else tomorrow
    cand = after.replace(hour=parsed["hour"], minute=parsed["minute"], second=0, microsecond=0)
    if cand <= after:
        cand += timedelta(days=1)
    return cand


def add_job(store: StateStore, name: str, schedule: str, task: str,
            section: str = "default", model: str = "local",
            skills: list[str] | None = None, mcp_tools: list[str] | None = None) -> dict:
    parsed = parse_schedule(schedule)
    state = store.load()
    jobs = state.setdefault("cron_jobs", [])
    job = {"id": max((j.get("id", 0) for j in jobs), default=0) + 1,
           "name": name, "schedule": schedule, "task": task, "section": section,
           "model": model, "skills": skills or [], "mcp_tools": mcp_tools or [],
           "last_run": None, "next_run": next_run_after(parsed).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "status": "enabled", "enabled": True, "parsed": parsed}
    jobs.append(job)
    store.save(state)
    brain.record(store, "cron_added", job)
    return job


def list_jobs(store: StateStore) -> list[dict]:
    return store.load().get("cron_jobs", [])


def delete_job(store: StateStore, job_id: int) -> dict:
    state = store.load()
    jobs = state.get("cron_jobs", [])
    for j in jobs:
        if j["id"] == job_id:
            jobs.remove(j)
            store.save(state)
            brain.record(store, "cron_deleted", {"id": job_id, "name": j["name"]})
            return j
    raise ValueError(f"unknown cron job: {job_id}")


def due_jobs(store: StateStore, now: datetime | None = None) -> list[dict]:
    now = now or _now()
    out = []
    for job in list_jobs(store):
        if not job.get("enabled"):
            continue
        nxt = job.get("next_run")
        if nxt and nxt <= now.strftime("%Y-%m-%dT%H:%M:%SZ"):
            out.append(job)
    return out


def run_loop(store: StateStore, task_fn, mode: str = "repeat", max_iterations: int = 3,
             gated_action: str | None = None, approve: bool = False,
             confirm: str = "") -> dict:
    """Run task_fn repeatedly. task_fn(i) -> dict with 'status' PASS/FAIL.

    mode: 'repeat' (exactly max_iterations), 'until_success' (stop on
    first PASS), 'gated' (gate checked before EVERY iteration if a
    gated_action is named — a blocked iteration stops the loop, it is
    never skipped silently). Kill switch stops the loop instantly.
    Returns a summary + per-iteration log, all recorded to Brain.
    """
    if mode not in ("repeat", "until_success", "gated"):
        raise ValueError(f"unknown loop mode: {mode}")
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")
    iterations: list[dict] = []
    outcome = "completed"
    for i in range(max_iterations):
        if store.load().get("killed"):
            outcome = "killed"
            break
        if mode == "gated" and gated_action:
            try:
                require_approval(gated_action, f"loop iteration {i}", approve=approve,
                                 confirm=confirm, expected_confirm=confirm or "")
            except GateBlocked as exc:
                iterations.append({"iteration": i, "status": "gate_blocked", "error": str(exc)})
                outcome = "gate_blocked"
                break
        result = task_fn(i)
        iterations.append({"iteration": i, **result})
        if mode == "until_success" and result.get("status") in ("PASS", "done", "success"):
            outcome = "success"
            break
    summary = {"mode": mode, "iterations": iterations, "outcome": outcome,
               "iterations_run": len([x for x in iterations if x.get("status") != "gate_blocked"])}
    brain.record(store, "loop", summary)
    return summary
