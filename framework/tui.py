"""Actual UI — dependency-free pane renderer + optional curses TUI.

Design constraints (Windows + Linux, no new dependencies):
- The pane *layout* is pure Python: ``render_panes(state)`` returns a
  plain-text, box-drawn screen that can be printed anywhere, captured
  to a file, or rendered to a PNG for screenshots. It never needs
  curses, a GUI, or a server.
- The *interactive* TUI (``run_tui``) uses stdlib ``curses`` when it
  is available (Linux/macOS). On Windows, where stdlib curses is not
  shipped, ``watch --tui`` falls back to the static pane render with
  a clear note — it never crashes, and it never pretends curses ran.
- Watch is read-only by default. Keys are explicit actions, never
  typing into an agent's terminal:
    q  quit the TUI (framework keeps running)
    p  pause all running agents
    r  resume paused agents
    t  takeover: mark the first running agent as taken over by a human
    s  stop all agents (sandboxes frozen, not deleted)
    k  KILL SWITCH: stop everything instantly (sections + agents)
    a  approval note: the gate is NOT bypassed by the TUI. Approval
       still happens via ``ship --approve --confirm <candidate>``.
  The approval gate and kill switch work exactly as in the CLI — the
  TUI is a view + explicit-action surface, not a second gate.
"""
from __future__ import annotations

from . import brain
from .state import StateStore

STATUS_GLYPH = {
    "running": "● working",
    "working": "● working",
    "done": "✓ done",
    "failed": "✗ failed",
    "paused": "⏸ paused",
    "stopped": "■ stopped",
    "waiting": "○ waiting",
    "takeover": "◉ takeover",
    "active": "● active",
}

# Keys the interactive TUI honours. Kept as data so tests can check
# the contract without launching curses.
TUI_KEYS = {
    "q": "quit TUI",
    "p": "pause all running agents",
    "r": "resume paused agents",
    "t": "takeover first running agent",
    "s": "stop all agents",
    "k": "kill switch: stop everything instantly",
    "a": "approval note (gate still via ship --approve --confirm)",
}


def _clip(text: str, width: int) -> str:
    text = str(text)
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _box(title: str, lines: list[str], width: int) -> list[str]:
    inner = max(10, width - 4)
    out = [f"┌─ {_clip(title, inner - 2)} ".ljust(width - 1, "─") + "┐"]
    for line in lines:
        out.append(f"│ {_clip(line, inner).ljust(inner)} │")
    out.append("└" + "─" * (width - 2) + "┘")
    return out


def _last_run_for(state: dict, agent_name: str) -> dict | None:
    for run in reversed(state.get("runs", [])):
        for result in run.get("results", []):
            if result.get("agent") == agent_name:
                return result
    return None


def build_panes(state: dict) -> dict:
    """Turn raw state into panes. Never crashes on missing/empty data,
    and never drops a pane because another section was deleted."""
    sections = state.get("sections", {})
    agents = state.get("agents", {})
    agent_panes = []
    for key, agent in sorted(agents.items()):
        section, _, name = key.partition("/")
        last = _last_run_for(state, name)
        if last:
            tool = "finished" if last.get("status") == "done" else last.get("status", "coding")
            last_out = f"output.txt: {last.get('status', '').upper() or '—'}"
            cost = last.get("cost", 0.0)
            elapsed = last.get("time_seconds", 0)
        else:
            tool = "coding" if agent.get("status") == "running" else "—"
            last_out = "— (no run yet)"
            cost, elapsed = 0.0, 0
        agent_panes.append(
            {
                "section": section,
                "name": name,
                "key": key,
                "model": agent.get("model", "local"),
                "status": agent.get("status", "waiting"),
                "tool": tool,
                "last_output": last_out,
                "cost": cost,
                "time_seconds": elapsed,
            }
        )
    log_lines = []
    for run in state.get("runs", [])[-4:]:
        log_lines.append(f"RUN {run.get('task')}: " + ", ".join(f"{r.get('agent')}={r.get('status')}" for r in run.get("results", [])))
    for battle in state.get("battles", [])[-4:]:
        log_lines.append(f"COURT {battle.get('battle_id')}: {battle.get('outcome')} winner={battle.get('winner')}")
    if not log_lines:
        log_lines = ["(no runs yet — try: run.py run \"hello\")"]
    return {
        "boss": {
            "sections": len(sections),
            "agents": len(agents),
            "killed": bool(state.get("killed")),
        },
        "agents": agent_panes,
        "log": log_lines,
        "tombstones": list(state.get("tombstones", [])),
    }


def render_panes(state: dict, width: int = 100) -> str:
    """Render the full TUI screen as plain text (capturable, testable)."""
    panes = build_panes(state)
    boss = panes["boss"]
    lines: list[str] = []
    lines.append("=" * width)
    lines.append("  BATTLE COURT — MULTI-CLI AGENT FRAMEWORK  ·  live watch (mock agents, $0 spend)")
    lines.append("  Keys: q quit · p pause · r resume · t takeover · s stop · k KILL SWITCH · a approval note")
    lines.append("=" * width)
    lines.extend(
        _box(
            "BOSS",
            [
                f"sections: {boss['sections']}   agents: {boss['agents']}   killed: {boss['killed']}",
                "Approval gate: ON — ship needs --approve --confirm <candidate>. Learning: always-on, proposal-only.",
            ],
            width,
        )
    )
    if not panes["agents"]:
        lines.extend(_box("AGENTS", ["(no agents — spawn one: agent spawn <section> <name>) "], width))
    else:
        # Two panes per row, each ~half width.
        pane_width = max(30, (width - 3) // 2)
        row: list[dict] = []
        for pane in panes["agents"]:
            row.append(pane)
            if len(row) == 2:
                lines.extend(_render_row(row, pane_width))
                row = []
        if row:
            lines.extend(_render_row(row, pane_width))
    for tomb in panes["tombstones"]:
        lines.extend(
            _box(
                f"TOMBSTONE — {tomb.get('section', '?')} deleted",
                [f"deleted at {tomb.get('deleted_at', '—')} · archived at {tomb.get('archive', '—')} · other panes kept running"],
                width,
            )
        )
    lines.extend(_box("LOG", panes["log"], width))
    lines.append(_clip("Watch is read-only by default. Pause / takeover / stop / approve are explicit actions,", width))
    lines.append(_clip("not typing into an agent terminal.", width))
    return "\n".join(lines)


def _render_row(panes: list[dict], width: int) -> list[str]:
    boxes = []
    for pane in panes:
        status = STATUS_GLYPH.get(pane["status"], pane["status"])
        boxes.append(
            _box(
                f"{pane['section']}/{pane['name']}",
                [
                    f"model:  {pane['model']}",
                    f"status: {status}",
                    f"tool:   {pane['tool']}",
                    f"last:   {pane['last_output']}",
                    f"cost:   ${pane['cost']:.2f}   time: {pane['time_seconds']}s",
                ],
                width,
            )
        )
    # Pad a single-pane row with an empty box so columns stay aligned,
    # and pad the shorter box to the taller box's height (a 1-pane row
    # otherwise crashes on the missing lines).
    if len(boxes) == 1:
        boxes.append(_box("—", ["(empty pane)"], width))
    max_h = max(len(b) for b in boxes)
    for b in boxes:
        while len(b) < max_h:
            b.append(" " * width)
    out: list[str] = []
    for i in range(max_h):
        out.append(boxes[0][i] + " " + boxes[1][i])
    return out


def apply_tui_key(store: StateStore, key: str) -> str:
    """Apply one explicit TUI key. Returns a human-readable result.
    'a' deliberately does NOT approve anything — the gate stays CLI-only."""
    state = store.load()
    if key == "p":
        for agent in state["agents"].values():
            if agent["status"] == "running":
                agent["status"] = "paused"
        store.save(state)
        return "paused all running agents"
    if key == "r":
        for agent in state["agents"].values():
            if agent["status"] == "paused":
                agent["status"] = "running"
        store.save(state)
        return "resumed paused agents"
    if key == "t":
        for key_name, agent in state["agents"].items():
            if agent["status"] == "running":
                agent["status"] = "takeover"
                store.save(state)
                brain.record(store, "takeover", {"agent": key_name})
                return f"takeover: human took over {key_name}"
        return "takeover: no running agent to take over"
    if key == "s":
        for agent in state["agents"].values():
            agent["status"] = "stopped"
        store.save(state)
        return "stopped all agents (sandboxes frozen, not deleted)"
    if key == "k":
        store.kill_all()
        return "KILL SWITCH: all agents and sections stopped instantly"
    if key == "a":
        return "Approval note: TUI never auto-approves. Use: ship --approve --confirm <candidate>"
    return f"unknown key: {key!r} (q/p/r/t/s/k/a)"


def run_tui(store: StateStore) -> int:
    """Interactive TUI. Returns 0 on clean quit. Falls back to a static
    pane render (not a crash, not a fake curses session) when curses
    is unavailable — e.g. stock Windows Python."""
    try:
        import curses
    except ImportError:
        print(render_panes(store.load()))
        print("\n[note] curses is not available in this Python (stock Windows).")
        print("Static pane render shown above. Interactive keys need curses (Linux/macOS) or Windows Terminal + windows-curses.")
        return 0

    def _loop(stdscr) -> None:
        try:
            curses.curs_set(0)
        except Exception:
            pass
        stdscr.nodelay(True)
        stdscr.timeout(500)
        while True:
            stdscr.erase()
            text = render_panes(store.load(), width=100)
            for i, line in enumerate(text.splitlines()):
                try:
                    stdscr.addstr(i, 0, line[: stdscr.getmaxyx()[1] - 1])
                except Exception:
                    break
            stdscr.refresh()
            ch = stdscr.getch()
            if ch == -1:
                continue
            key = chr(ch) if 0 <= ch < 256 else ""
            if key == "q":
                break
            if key in TUI_KEYS:
                result = apply_tui_key(store, key)
                stdscr.addstr(0, 0, result[:80])
                stdscr.refresh()
                stdscr.timeout(800)
                stdscr.getch()
                stdscr.timeout(500)

    curses.wrapper(_loop)
    return 0
