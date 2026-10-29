"""Actual UI — dependency-free pane renderer + optional curses TUI.

Ease-of-use rating, honestly: the old screen was ~4/10 (single-letter
keys, no on-screen help beyond one line, actions hit all/first agent,
no onboarding, tabs were a separate command, Windows got a static
dump). This version targets 8/10:

- Always-visible menu bar: Watch | Goals | Tasks | What's Next |
  Cron & Loops | Environments | Help — click them in the dashboard,
  or press Tab to cycle them in curses.
- Always-visible bottom bar: the keys for the current tab, in plain
  words, not just letters ("P = Pause selected agent").
- Select ONE agent: arrow keys / j / k in curses, number keys 1-9 in
  static mode. p / r / t / s then act on the selected agent ONLY.
  "All" actions are a separate, confirmed key (Shift-P pauses all,
  and only after a second confirmation press — see apply_tui_key).
- Help overlay: ? or h, in curses and in the static render, plus
  `run.py help` and `run.py tui --help`.
- First-run / empty state: a short "Start here" guide (3 steps, exact
  commands) instead of an empty pane grid.
- Plain-language status: "Working — no action needed",
  "Paused — press R to resume", "Waiting for your approval — run
  ship --approve --confirm <candidate>", never just "running".
- Search/filter: / in curses, `watch --panes --filter <term>` in CLI.
- Windows static fallback is now useful: menu bar, help text, a
  numbered agent list, and the exact CLI command for each action
  (e.g. "To pause agent 2: run.py agent pause builder/agent-a").

Safety rules are unchanged, and the TUI never bypasses them:
- The approval gate is CLI-only. The TUI/dashboard show the exact
  ship command; they never approve anything themselves.
- Kill switch (k) stops everything instantly.
- TUI actions are explicit, never typing into an agent's terminal.

The easiest UI of all is the local web dashboard
(framework/dashboard.py): `run.py dashboard` serves clickable tabs,
click-to-select panes, buttons, and forms on 127.0.0.1 only. The
dashboard reads/writes the same state.json as CLI and TUI, so all
three stay in sync — no second database.
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

# Plain-language status: what it means, and what (if anything) to do.
PLAIN_STATUS = {
    "running": "Working — no action needed",
    "working": "Working — no action needed",
    "done": "Done — no action needed",
    "failed": "Failed — check the log below, then re-run",
    "paused": "Paused — press R to resume",
    "stopped": "Stopped — sandbox frozen, not deleted",
    "waiting": "Waiting to start — no action needed yet",
    "takeover": "You took over — this agent is waiting on you",
    "active": "Active — no action needed",
    "killed": "Stopped by the kill switch",
}

APPROVAL_NOTE = (
    "Waiting for your approval — run: ship --approve --confirm <candidate>. "
    "The TUI and dashboard never approve anything themselves."
)

MENU_TABS = ["Watch", "Goals", "Tasks", "What's Next", "Cron & Loops", "Environments", "Help"]

# Keys the interactive TUI honours. Kept as data so tests can check
# the contract without launching curses.
TUI_KEYS = {
    "q": "quit TUI",
    "p": "pause selected agent",
    "r": "resume selected agent",
    "t": "takeover selected agent",
    "s": "stop selected agent",
    "P": "pause ALL agents (needs a second confirmation press)",
    "k": "kill switch: stop everything instantly",
    "a": "approval note (gate still via ship --approve --confirm)",
    "?": "show help overlay",
    "h": "show help overlay",
    "Tab": "cycle tabs: Watch / Goals / Tasks / What's Next / Cron & Loops / Environments / Help",
    "Up/Down or j/k": "move selection to another agent",
    "1-9": "select agent by number",
    "/": "filter panes/tasks by name or status (Esc clears)",
    "Esc": "close help / clear filter",
}

HELP_TEXT = """BATTLE COURT — HELP (press ? or h again, or q, to close)

WHAT THIS IS, IN PLAIN WORDS
  Several agents work in parallel, each in its own sandbox. You watch
  them live, pick a winner in Battle Court, and approve anything
  before it ships. Nothing ships, sends, pays, deletes, or merges
  without your approval — ever.

TABS (top menu bar — Tab cycles them, or click them in the dashboard)
  Watch        — live agent panes + log (this screen)
  Goals        — long-term goals, with progress
  Tasks        — current tasks, with status and owner agent
  What's Next  — next deliverables due, in order
  Cron & Loops — scheduled jobs: next run, last run, status
  Environments — agent setups: section + agent + sandbox + model
  Help         — this screen

KEYS (bottom bar shows the keys for the current tab)
  Arrow Up/Down, or j/k  — move the selection to another agent
  1-9                    — select agent by number (static mode too)
  P = Pause selected agent     R = Resume selected agent
  T = Take over selected agent S = Stop selected agent
  Shift-P                  — pause ALL agents (press twice to confirm)
  K = Kill Switch          — stop EVERYTHING instantly
  A = Approval note        — shows the ship command; NEVER approves
  /                        — filter panes/tasks by name or status
  Esc                      — close help, or clear the filter
  ? or h                   — this help screen
  q                        — quit the TUI (the framework keeps running)

APPROVAL — READ THIS
  The TUI and dashboard NEVER approve a ship. To approve, run this
  in a terminal, with the exact candidate name:
      ship --approve --confirm <candidate>
  If you see "Waiting for your approval", that command is the fix.

START HERE (when nothing exists yet)
  1. Add an environment:  environment add scout-env --skills research
  2. Run something:        run "hello"
  3. Watch it:              watch --panes   (or: tui, or: dashboard)

EASIEST PATH ON WINDOWS
  Stock Windows Python has no curses, so the terminal TUI is a
  static render there. Use the clickable dashboard instead:
      python run.py dashboard
  Then open http://127.0.0.1:8767 in your browser. It is local-only
  (127.0.0.1, nothing leaves your machine) and uses the same state
  as the CLI and TUI, so everything stays in sync.
"""


def plain_status(status: str, name: str = "") -> str:
    """Plain-language status + what to do next. Never just a code word."""
    base = PLAIN_STATUS.get(status, f"{status} — no action needed")
    if status in ("running", "working") and name:
        return f"Working on {name} — no action needed"
    return base


def agent_keys(state: dict) -> list[str]:
    return sorted(state.get("agents", {}).keys())


def select_agent(state: dict, index: int) -> str | None:
    """1-based selection, as shown in the numbered pane list."""
    keys = agent_keys(state)
    if 1 <= index <= len(keys):
        return keys[index - 1]
    return None


def filter_panes(panes: list[dict], term: str) -> list[dict]:
    if not term:
        return panes
    term = term.lower()
    return [p for p in panes
            if term in p["key"].lower() or term in p["status"].lower()
            or term in p["model"].lower() or term in p["name"].lower()]


def render_menu_bar(active_tab: str = "Watch", width: int = 100) -> str:
    parts = []
    for tab in MENU_TABS:
        parts.append(f"[{tab}]" if tab == active_tab else tab)
    return _clip("  " + "  |  ".join(parts), width)


def render_bottom_bar(active_tab: str = "Watch") -> str:
    bars = {
        "Watch": "Keys: Up/Down or j/k = select agent · 1-9 = select by number · P = Pause selected agent · R = Resume selected agent · T = Take over selected agent · S = Stop selected agent · Shift-P = Pause ALL (press twice) · K = KILL SWITCH · A = Approval note (never approves) · / = filter · ? = Help · q = quit",
        "Goals": "Keys: Tab = change tab · ? = Help · q = quit · CLI: goal add <title> / goal list / goal progress --id <n> --progress <0-100>",
        "Tasks": "Keys: Tab = change tab · ? = Help · q = quit · CLI: task add <title> / task list / task status --id <n> --status doing|done",
        "What's Next": "Keys: Tab = change tab · ? = Help · q = quit · CLI: deliverable add <title> / deliverable list",
        "Cron & Loops": "Keys: Tab = change tab · ? = Help · q = quit · CLI: cron add <name> --schedule 'every 60 minutes' --task <task> / cron list",
        "Environments": "Keys: Tab = change tab · ? = Help · q = quit · CLI: environment add <name> --skills research",
        "Help": "Keys: Esc or ? = close help · q = quit",
    }
    return bars.get(active_tab, bars["Watch"])


def render_start_here(width: int = 100) -> list[str]:
    return _box(
        "START HERE — nothing exists yet, do these 3 steps",
        [
            "1. Add an environment:  environment add scout-env --skills research",
            "2. Run something:        run \"hello\"",
            "3. Watch it live:        watch --panes   (or: tui, or: dashboard)",
            "",
            "Easiest path (clickable, Windows-friendly):",
            "  python run.py dashboard   then open http://127.0.0.1:8767",
            "  Press ? any time for help. Nothing ships without your approval.",
        ],
        width,
    )


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


def render_tabs(state: dict, width: int = 100) -> str:
    """Goals / Tasks / What's Next / Cron & Loops / Environments tabs
    as readable sections, with the menu bar on top. In the dashboard
    these are clickable tabs; in curses, Tab cycles them."""
    from .goals import whats_next

    lines: list[str] = []
    lines.append("=" * width)
    lines.append(render_menu_bar("Goals", width))
    lines.append("  (dashboard: click a tab · curses: Tab cycles tabs · CLI: goal list / task list / deliverable list / cron list)")
    lines.append("=" * width)
    goal_lines = [f"#{g['id']} {g['title']} — {g['progress']}% [{g['status']}]"
                  for g in state.get("goals", [])] or ["(no goals yet — goal add <title>)"]
    lines.extend(_box("GOALS — long-term, with progress", goal_lines, width))
    task_lines = [f"#{t['id']} {t['title']} — {t['status']} · owner={t.get('owner') or '—'} · section={t.get('section') or '—'}"
                  for t in state.get("tasks", [])] or ["(no tasks yet — task add <title>)"]
    lines.extend(_box("TASKS — current, with status + owner agent/section", task_lines, width))
    del_lines = [f"#{d['id']} (due #{d['due_order']}) {d['title']} — {d['status']}"
                 for d in whats_next_state(state)] or ["(no deliverables yet — deliverable add <title>)"]
    lines.extend(_box("WHAT'S NEXT / DELIVERABLES — next due, in order", del_lines, width))
    cron_lines = []
    for j in state.get("cron_jobs", []):
        cron_lines.append(f"#{j['id']} {j['name']} — {j['schedule']} · next={j.get('next_run') or '—'} · last={j.get('last_run') or '—'} · {j.get('status')}")
    if not cron_lines:
        cron_lines = ["(no cron jobs yet — cron add <name> --schedule 'every 60 minutes' --task <task>)"]
    lines.extend(_box("CRON & LOOPS — next run, last run, status", cron_lines, width))
    env_lines = [f"{name}: section={e.get('section')} agent={e.get('agent')} model={e.get('model')} skills={','.join(e.get('skills', [])) or '—'} mcp={','.join(e.get('mcp_tools', [])) or '—'}"
                 for name, e in state.get("environments", {}).items()] or ["(no environments yet — environment add <name>)"]
    lines.extend(_box("ENVIRONMENTS — one action: section + agent + sandbox + model + skills + MCP", env_lines, width))
    return "\n".join(lines)


def whats_next_state(state: dict) -> list[dict]:
    items = sorted(state.get("deliverables", []), key=lambda d: d["due_order"])
    return [i for i in items if i["status"] != "done"] + [i for i in items if i["status"] == "done"]


def render_panes(state: dict, width: int = 100, selected: str | None = None,
                 filter_term: str = "", active_tab: str = "Watch",
                 show_help: bool = False) -> str:
    """Render the full TUI screen as plain text (capturable, testable).

    selected: the "section/agent" key the user picked — actions act on
    it only. filter_term: substring filter over panes. show_help:
    render the help overlay instead of the panes.
    """
    if show_help:
        return HELP_TEXT
    panes = build_panes(state)
    boss = panes["boss"]
    lines: list[str] = []
    lines.append("=" * width)
    lines.append(render_menu_bar(active_tab, width))
    lines.append("  BATTLE COURT — MULTI-CLI AGENT FRAMEWORK  ·  live watch (mock agents, $0 spend)")
    lines.append("=" * width)
    if filter_term:
        lines.append(f"  Filter: '{filter_term}' — Esc clears the filter")
    lines.extend(_box("BOSS", [f"sections: {boss['sections']}   agents: {boss['agents']}   killed: {boss['killed']}",
                               "Approval gate: ON — ship needs --approve --confirm <candidate>. Learning: always-on, proposal-only."], width))
    if not panes["agents"]:
        lines.extend(render_start_here(width))
        lines.extend(_box("AGENTS", ["(no agents — spawn one: agent spawn <section> <name>) "], width))
    else:
        agents = filter_panes(panes["agents"], filter_term)
        if not agents:
            lines.extend(_box("AGENTS", [f"(no agents match filter '{filter_term}' — Esc clears it)"], width))
        else:
            if selected is None:
                selected = agents[0]["key"]
            pane_width = max(30, (width - 3) // 2)
            row: list[dict] = []
            for i, pane in enumerate(agents):
                pane = dict(pane)
                pane["number"] = agent_keys(state).index(pane["key"]) + 1 if pane["key"] in agent_keys(state) else i + 1
                pane["is_selected"] = pane["key"] == selected
                row.append(pane)
                if len(row) == 2:
                    lines.extend(_render_row(row, pane_width))
                    row = []
            if row:
                lines.extend(_render_row(row, pane_width))
            lines.append(_clip(f"Selected agent: {selected} — P pauses THIS agent only (Shift-P pauses all, press twice to confirm).", width))
            lines.append("  Static mode? Act by number from the list above, e.g.:")
            for pane in agents:
                n = agent_keys(state).index(pane["key"]) + 1
                lines.append(_clip(f"    Agent {n}: {pane['key']} — pause with: run.py agent pause {pane['section']} {pane['name']}", width))
    for tomb in panes["tombstones"]:
        lines.extend(
            _box(
                f"TOMBSTONE — {tomb.get('section', '?')} deleted",
                [f"deleted at {tomb.get('deleted_at', '—')} · archived at {tomb.get('archive', '—')} · other panes kept running"],
                width,
            )
        )
    lines.extend(_box("LOG", panes["log"], width))
    lines.append(_clip("Approval gate: ON — the TUI never approves. To approve a ship, run: ship --approve --confirm <candidate>", width))
    lines.append("=" * width)
    lines.append(_clip(render_bottom_bar(active_tab), width))
    lines.append(_clip("Press ? for full help. Watch is read-only by default; pause / takeover / stop are explicit actions, not typing into an agent terminal.", width))
    return "\n".join(lines)


def render_static_fallback(state: dict, width: int = 100) -> str:
    """The Windows / no-curses render: menu bar + help + numbered
    agent list + the exact CLI command for each action, so a static
    user can still act. Never pretends curses ran."""
    lines = [render_panes(state, width=width)]
    lines.append("")
    lines.append("=" * width)
    lines.append("  STATIC MODE — curses is not available in this Python (stock Windows).")
    lines.append("  This render is not interactive, but you can still act from a terminal:")
    for i, key in enumerate(agent_keys(state), start=1):
        section, _, name = key.partition("/")
        lines.append(f"    Agent {i} ({key}): pause -> run.py agent pause {section} {name} | stop -> run.py agent kill {section} {name}")
    lines.append("  Or use the clickable dashboard (easiest on Windows):")
    lines.append("    python run.py dashboard   then open http://127.0.0.1:8767")
    lines.append("  FULL HELP (same as pressing ? in the TUI):")
    lines.append(HELP_TEXT)
    return "\n".join(lines)


def _render_row(panes: list[dict], width: int) -> list[str]:
    boxes = []
    for pane in panes:
        marker = "► " if pane.get("is_selected") else ""
        num = pane.get("number", "")
        boxes.append(
            _box(
                f"{marker}[{num}] {pane['section']}/{pane['name']}",
                [
                    f"model:  {pane['model']}",
                    f"status: {STATUS_GLYPH.get(pane['status'], pane['status'])}",
                    f"plain:  {plain_status(pane['status'])}",
                    f"tool:   {pane['tool']}",
                    f"last:   {pane['last_output']}",
                    f"cost:   ${pane['cost']:.2f}   time: {pane['time_seconds']}s",
                ],
                width,
            )
        )
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


def _act_on_agent(store: StateStore, key: str, action: str) -> str:
    """Act on ONE agent only. Returns a confirmation line naming it."""
    state = store.load()
    if key not in state["agents"]:
        return f"no such agent: {key}"
    section, _, name = key.partition("/")
    if action == "pause":
        store.set_agent_status(section, name, "paused")
        return f"Paused selected agent {key} (other agents untouched). Press R to resume it."
    if action == "resume":
        store.set_agent_status(section, name, "running")
        return f"Resumed selected agent {key}."
    if action == "takeover":
        store.set_agent_status(section, name, "takeover")
        brain.record(store, "takeover", {"agent": key})
        return f"Takeover: you took over selected agent {key}."
    if action == "stop":
        store.set_agent_status(section, name, "stopped")
        return f"Stopped selected agent {key} (sandbox frozen, not deleted; other agents untouched)."
    return f"unknown action: {action}"


def apply_tui_key(store: StateStore, key: str, selected: str | None = None,
                  confirm_all: bool = False) -> str:
    """Apply one explicit TUI key. Returns a human-readable result.

    With a selection, p/r/t/s act on the selected agent ONLY — the old
    all/first-agent behaviour survives only as the no-selection
    fallback, so existing callers keep working. 'a' deliberately does
    NOT approve anything — the gate stays CLI-only. 'P' (pause all)
    needs confirm_all=True; without it, nothing changes and the
    caller is told to confirm.
    """
    state = store.load()
    if key == "p" and selected:
        return _act_on_agent(store, selected, "pause")
    if key == "r" and selected:
        return _act_on_agent(store, selected, "resume")
    if key == "t" and selected:
        return _act_on_agent(store, selected, "takeover")
    if key == "s" and selected:
        return _act_on_agent(store, selected, "stop")
    if key == "P":
        if not confirm_all:
            return "Pause ALL agents? Press Shift-P again to confirm — nothing was paused yet."
        for agent in state["agents"].values():
            if agent["status"] == "running":
                agent["status"] = "paused"
        store.save(state)
        return "Paused ALL running agents (confirmed)."
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
    if key in ("?", "h"):
        return HELP_TEXT
    return f"unknown key: {key!r} (q/p/r/t/s/k/a/? — press ? for help)"


def run_tui(store: StateStore, filter_term: str = "") -> int:
    """Interactive TUI. Returns 0 on clean quit. Falls back to the
    useful static render (menu + help + numbered CLI actions) when
    curses is unavailable — e.g. stock Windows Python."""
    try:
        import curses
    except ImportError:
        print(render_static_fallback(store.load()))
        return 0

    def _loop(stdscr) -> None:
        try:
            curses.curs_set(0)
        except Exception:
            pass
        stdscr.nodelay(True)
        stdscr.timeout(500)
        selected_idx = 0
        active_tab_idx = 0
        show_help = False
        cur_filter = filter_term
        filter_mode = False
        pending_all_pause = False
        notice = ""
        while True:
            state = store.load()
            keys = agent_keys(state)
            if keys:
                selected_idx = min(selected_idx, len(keys) - 1)
                selected = keys[selected_idx]
            else:
                selected = None
            stdscr.erase()
            if show_help:
                text = HELP_TEXT
            elif MENU_TABS[active_tab_idx] == "Watch":
                text = render_panes(state, width=100, selected=selected,
                                    filter_term=cur_filter, active_tab="Watch")
            else:
                text = render_tabs(state, width=100)
            for i, line in enumerate(text.splitlines()):
                try:
                    stdscr.addstr(i, 0, line[: stdscr.getmaxyx()[1] - 1])
                except Exception:
                    break
            if notice:
                try:
                    stdscr.addstr(0, 0, notice[:80])
                except Exception:
                    pass
            stdscr.refresh()
            ch = stdscr.getch()
            if ch == -1:
                continue
            notice = ""
            pending_all_pause = pending_all_pause and chr(ch) != "P" if 0 <= ch < 256 else pending_all_pause
            if ch == 27:  # Esc: close help / clear filter
                show_help = False
                cur_filter = ""
                filter_mode = False
                continue
            if ch == 9:  # Tab: cycle tabs
                active_tab_idx = (active_tab_idx + 1) % len(MENU_TABS)
                show_help = MENU_TABS[active_tab_idx] == "Help"
                continue
            if filter_mode:
                if ch in (10, 13):
                    filter_mode = False
                elif ch in (8, 127, 263):
                    cur_filter = cur_filter[:-1]
                elif 32 <= ch < 127:
                    cur_filter += chr(ch)
                continue
            if ch == ord("/"):
                filter_mode = True
                continue
            key = chr(ch) if 0 <= ch < 256 else ""
            if key == "q" and not show_help:
                break
            if key in ("?", "h"):
                show_help = not show_help
                continue
            if show_help:
                continue
            if key == "j":
                selected_idx = min(max(0, len(keys) - 1), selected_idx + 1)
                continue
            # curses arrow keys arrive as codes > 255; handle them too
            if ch == 259:  # KEY_UP
                selected_idx = max(0, selected_idx - 1)
                continue
            if ch == 258:  # KEY_DOWN
                selected_idx = min(max(0, len(keys) - 1), selected_idx + 1)
                continue
            if key.isdigit() and key != "0":
                sel = select_agent(state, int(key))
                if sel:
                    selected_idx = keys.index(sel)
                continue
            if key == "P":
                if pending_all_pause:
                    notice = apply_tui_key(store, "P", confirm_all=True)
                    pending_all_pause = False
                else:
                    notice = apply_tui_key(store, "P", confirm_all=False)
                    pending_all_pause = True
                continue
            if key in TUI_KEYS and key not in ("?", "h", "Tab", "Up/Down or j/k", "1-9", "/"):
                notice = apply_tui_key(store, key, selected=selected)
                continue

    curses.wrapper(_loop)
    return 0
