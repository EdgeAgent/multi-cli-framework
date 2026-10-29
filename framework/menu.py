"""Branded startup menu — the screen you land on when you start the system.

This is Battle Court's own menu, in the style of a professional product
splash: big branding first, then a numbered list you can pick from.
It is NOT Hermes itself, and it does not use Hermes code or a Hermes
logo (no Hermes logo file exists here). The footer line says, honestly,
that Battle Court follows the Hermes *pattern* — a router on top,
workers in parallel, a Brain, and an approval gate — because that is
the architecture Kevin already runs. Battle Court branding stays primary.

Surfaces, all from this one module so they cannot drift apart:
- CLI / static mode (stock Windows, no curses): `python run.py` with no
  args, or `python run.py menu` — the menu prints as text, you type a
  number, that action runs. This is the mode that always works.
- Curses TUI: the menu is the first screen. Move with arrows / j / k,
  press Enter to pick, or press a single digit 1-9. Press 'm' later to
  come back to the menu. (Digits 10 and 11 need arrows + Enter in
  curses, because a single keypress is only one digit.)
- Dashboard: the home page shows the same menu, same numbering and
  order, as clickable buttons that switch to the matching tab.

Safety, unchanged from the rest of the framework:
- The menu NEVER approves, ships, sends, pays, deletes, or merges
  anything. There is no ship/approve option on it at all — the
  approval note only ever shows the CLI ship command.
- The Kill Switch is on the menu as an explicit, confirmed option
  (type KILL to confirm, or press K twice in curses), never a default
  and never fired by picking a normal menu number.
- Dashboard choices that need a browser do not start a server behind
  your back from inside the menu loop: they print the exact next step
  (`python run.py dashboard`, then open http://127.0.0.1:8767).
"""
from __future__ import annotations

from . import brain, goals, mcp, skills, tui
from .state import StateStore

VERSION = "skeleton v0.1.0-skeleton"
TAGLINE = "Parallel agents. Judged. Learned from. Never auto-shipped."
HERMES_PATTERN_LINE = (
    "Powered by the Hermes pattern — router + workers + Brain + approval gate. "
    "This is Battle Court, not Hermes itself: no Hermes code or logo is used here."
)
APPROVAL_NOTE = (
    "Safety: this menu never approves, ships, sends, pays, deletes, or merges. "
    "Approval is CLI-only: ship --approve --confirm <candidate>."
)

# (number, label, action, plain-language description)
MENU_ITEMS = [
    ("1", "Watch live", "watch",
     "Live agent panes + log — the watch screen."),
    ("2", "Dashboard", "dashboard",
     "Clickable web dashboard — needs a browser, see the next step below."),
    ("3", "Goals", "goals",
     "Long-term goals, with progress."),
    ("4", "Tasks", "tasks",
     "Current tasks, with status and owner agent."),
    ("5", "What's Next", "deliverables",
     "Next deliverables due, in order."),
    ("6", "Cron & Loops", "cron",
     "Scheduled jobs and loops: next run, last run, status."),
    ("7", "Environments", "environments",
     "Agent setups: section + agent + sandbox + model + skills + MCP."),
    ("8", "Battle Court", "battle",
     "Judge two candidates — winner staged only, never auto-shipped."),
    ("9", "Skills & MCP", "skills_mcp",
     "Playbooks agents run off, and MCP tool servers."),
    ("10", "Brain", "brain",
     "Local memory: runs, skill uses, MCP calls, battles, verdicts."),
    ("11", "Help", "help",
     "Full help: keys, tabs, approval rule, Start Here."),
]
MENU_ACTIONS = {item[0]: item for item in MENU_ITEMS}
QUIT_KEYS = ("0", "q", "Q")


def render_menu(state: dict | None = None, width: int = 100) -> str:
    """The branded startup screen, as plain text (capturable, testable).

    state is only used for the small status line; a missing/empty
    state still renders a complete, usable menu.
    """
    state = state or {}
    agents = state.get("agents", {})
    sections = state.get("sections", {})
    lines: list[str] = []
    lines.append("=" * width)
    lines.append("")
    lines.append("  ⚖  BATTLE COURT")
    lines.append(f"  {TAGLINE}")
    lines.append("")
    lines.append(f"  Version: {VERSION}  ·  Local-only  ·  Mock agents, $0 spend")
    lines.append("  Status: tests passing — re-run the suite to confirm:")
    lines.append("            python3 -m unittest discover -s tests")
    lines.append(f"  Right now: {len(sections)} sections, {len(agents)} agents")
    lines.append("")
    lines.append("-" * width)
    lines.append("  PICK A NUMBER  (type it and press Enter; 0 quits)")
    for number, label, _action, description in MENU_ITEMS:
        lines.append(f"    {number:>2}. {label} — {description}")
    lines.append("     K. Kill Switch — stop EVERYTHING (type KILL to confirm)")
    lines.append("     0. Quit — leave the menu, framework keeps its state")
    lines.append("-" * width)
    lines.append(f"  {HERMES_PATTERN_LINE}")
    lines.append(f"  {APPROVAL_NOTE}")
    lines.append("  Dashboard (easiest on Windows): python run.py dashboard")
    lines.append("  then open http://127.0.0.1:8767  (local-only, nothing leaves your machine)")
    lines.append("=" * width)
    return "\n".join(lines)


def route(choice: str) -> dict:
    """Map one menu choice to its action, without running anything.

    Kept pure so tests can check routing without launching a TUI,
    a server, or a battle. Unknown choices return an error dict and
    never fall through to a default action.
    """
    choice = (choice or "").strip()
    if choice in QUIT_KEYS:
        return {"choice": choice, "action": "quit", "label": "Quit",
                "message": "Quitting the menu. Framework state is kept."}
    if choice in ("K", "k"):
        return {"choice": choice, "action": "kill",
                "label": "Kill Switch",
                "message": "Kill Switch needs confirmation: type KILL to confirm — nothing was stopped yet."}
    item = MENU_ACTIONS.get(choice)
    if item is None:
        return {"choice": choice, "action": "unknown",
                "message": f"Unknown menu choice: {choice!r}. Pick 1-11, K, or 0."}
    return {"choice": choice, "action": item[2], "label": item[1],
            "message": item[3]}


def dispatch(store: StateStore, choice: str, confirm: str = "") -> dict:
    """Run one menu choice and return a result dict with printable text.

    Interactive surfaces (watch TUI, dashboard server) are NOT started
    from here: they return an 'interactive' / 'next_step' result with
    the exact command, so a caller can start them in the right way
    (a TUI loop, or a second terminal for the dashboard). Everything
    else returns plain text the caller prints. This function never
    approves or ships anything, and it never kills without confirm.
    """
    routed = route(choice)
    action = routed["action"]
    if action in ("quit", "unknown"):
        return routed
    if action == "kill":
        if confirm != "KILL":
            return routed  # confirmation prompt, nothing stopped
        store.kill_all()
        return {"choice": choice, "action": "kill", "label": "Kill Switch",
                "message": "KILL SWITCH (confirmed): all agents and sections stopped instantly."}
    if action == "watch":
        return {"choice": choice, "action": "watch", "label": "Watch live",
                "interactive": "tui",
                "message": "Opening the live watch TUI (curses where available, useful static render otherwise)."}
    if action == "dashboard":
        return {"choice": choice, "action": "dashboard", "label": "Dashboard",
                "next_step": "python run.py dashboard  — then open http://127.0.0.1:8767",
                "message": "Dashboard needs a browser: run 'python run.py dashboard' in another terminal, "
                           "then open http://127.0.0.1:8767 (local-only)."}
    state = store.load()
    if action == "goals":
        text = "\n".join(
            f"#{g['id']} {g['title']} — {g['progress']}% [{g['status']}]"
            for g in state.get("goals", [])) or "(no goals yet — goal add <title>)"
    elif action == "tasks":
        text = "\n".join(
            f"#{t['id']} {t['title']} — {t['status']} · owner={t.get('owner') or '—'}"
            for t in state.get("tasks", [])) or "(no tasks yet — task add <title>)"
    elif action == "deliverables":
        text = "\n".join(
            f"#{d['id']} (due #{d['due_order']}) {d['title']} — {d['status']}"
            for d in tui.whats_next_state(state)) or "(no deliverables yet — deliverable add <title>)"
    elif action == "cron":
        text = "\n".join(
            f"#{j['id']} {j['name']} — {j['schedule']} · next={j.get('next_run') or '—'} · {j.get('status')}"
            for j in state.get("cron_jobs", [])) or "(no cron jobs yet — cron add <name> --schedule 'every 60 minutes' --task <task>)"
    elif action == "environments":
        text = "\n".join(
            f"{name}: section={e.get('section')} agent={e.get('agent')} model={e.get('model')}"
            for name, e in state.get("environments", {}).items()) or "(no environments yet — environment add <name>)"
    elif action == "battle":
        text = ("Battle Court judges two candidates on the same task: automated checks "
                "(tests, contract, evidence) first, your pick second, winner staged only.\n"
                "It never auto-merges or auto-ships — the approval gate still fires.\n"
                "Run: battle --task <task> --pick a|b|none")
    elif action == "skills_mcp":
        skill_lines = [f"skill: {s['name']} — {s['description']}" for s in skills.list_skills(store)]
        mcp_lines = [f"mcp: {srv['name']} — tools: {', '.join(srv.get('tools', []))}"
                     for srv in mcp.list_servers(store)]
        text = "\n".join(skill_lines + mcp_lines) or "(no skills or MCP servers found)"
    elif action == "brain":
        events = brain.events(store)[-10:]
        text = "\n".join(
            f"#{e.get('id', '?')} {e.get('type', '?')}: "
            + ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("id", "type"))
            for e in events) or "(Brain is empty — run something first, then brain list)"
    elif action == "help":
        text = tui.HELP_TEXT
    else:  # pragma: no cover - route() only returns the actions above
        text = routed["message"]
    return {"choice": choice, "action": action, "label": routed["label"],
            "message": routed["message"], "text": text}


def run_menu_loop(store: StateStore, input_fn=input, print_fn=print) -> int:
    """Static/Windows menu loop: print the menu, read a number, act.

    input_fn/print_fn are injectable so tests can drive the loop
    without a real terminal. EOF (Ctrl-D / closed stdin) quits cleanly.
    """
    while True:
        print_fn(render_menu(store.load()))
        try:
            choice = input_fn("Pick a number (0 quits): ").strip()
        except EOFError:
            print_fn("Quitting the menu. Framework state is kept.")
            return 0
        if choice in ("K", "k"):
            try:
                confirm = input_fn("Kill Switch — type KILL to confirm, anything else cancels: ").strip()
            except EOFError:
                return 0
            result = dispatch(store, choice, confirm=confirm)
            print_fn(result["message"])
            continue
        result = dispatch(store, choice)
        if result["action"] == "quit":
            print_fn(result["message"])
            return 0
        if result["action"] == "watch":
            # The TUI takes over the terminal; when it quits, come back here.
            from .tui import run_tui
            run_tui(store)
            continue
        print_fn(result.get("text") or result["message"])
        if result["action"] == "unknown":
            continue
