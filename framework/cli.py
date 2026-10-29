"""CLI entry: `framework <command>`.

All commands accept --root (workspace root, default: current directory)
and --json (machine-readable output where it makes sense).
No real model calls are made in the skeleton — agents are mocks.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import brain, contracts, goals, learning, mcp, router, scheduler, skills, tui, watch
from .gate import GateBlocked as _GateBlocked
from .court import judge
from .gate import GateBlocked, require_approval
from .orchestrator import MockAgent, run_parallel
from .sandbox import archive_sandbox, wipe_sandbox
from .state import StateStore


def _store(args) -> StateStore:
    return StateStore(args.root)


def _out(args, obj) -> None:
    if args.json:
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str))


def cmd_run(args) -> int:
    store = _store(args)
    conflicts = contracts.check_before_coding(store)
    if conflicts:
        print("CONTRACT CONFLICTS — resolve before coding:")
        for c in conflicts:
            print(f"  {c['kind']}: {c['item']} declared by {c['agents']}")
        return 2
    skill_list = getattr(args, "skills", None) or []
    mcp_list = getattr(args, "mcp", None) or []
    agents = [MockAgent(name, router.route("build")["model"], skills=skill_list, mcp_tools=mcp_list)
              for name in args.agents]
    results = run_parallel(store, args.task, agents, section=args.section)
    print(watch.render_status(store))
    print(f"\nRun complete: {len(results)} agents, " + ", ".join(f"{r['agent']}={r['status']}" for r in results))
    return 0


def cmd_section(args) -> int:
    store = _store(args)
    if args.action == "add":
        _out(args, store.add_section(args.name, role=args.role, model=args.model))
    elif args.action == "list":
        _out(args, store.load()["sections"])
    elif args.action == "delete":
        # Default = archive, never wipe. Wipe needs --wipe + --confirm <name>.
        archive = archive_sandbox(store, args.name, reason="section delete (archive by default)")
        if args.wipe:
            if not wipe_sandbox(store, args.name, confirm=args.confirm or ""):
                print("WIPE BLOCKED: --wipe requires --confirm <exact section name>. Archive was kept.")
                return 3
            print(f"Section {args.name} wiped (twice-confirmed). Archive was at {archive}.")
        else:
            print(f"Section {args.name} archived at {archive} (not wiped).")
        store.delete_section(args.name, archive=str(archive))
    return 0


def cmd_agent(args) -> int:
    store = _store(args)
    if args.action == "spawn":
        _out(args, store.spawn_agent(args.section, args.name, model=args.model))
    elif args.action == "kill":
        store.set_agent_status(args.section, args.name, "stopped")
        print(f"Agent {args.section}/{args.name} stopped (sandbox frozen, not deleted).")
    elif args.action == "pause":
        store.set_agent_status(args.section, args.name, "paused")
        print(f"Agent {args.section}/{args.name} paused.")
    elif args.action == "list":
        _out(args, store.load()["agents"])
    return 0


def cmd_contract(args) -> int:
    store = _store(args)
    if args.action == "declare":
        _out(args, contracts.declare(store, args.agent, files=args.file, apis=args.api, schemas=args.schema, plan=args.plan))
    elif args.action in ("list", "check"):
        _out(args, {"contracts": store.load()["contracts"], "conflicts": contracts.find_conflicts(store)})
    return 0


def cmd_battle(args) -> int:
    store = _store(args)
    # Two candidates, separate sandboxes, same task.
    a = MockAgent("candidate-a", args.a, fail=args.fail_a, no_evidence=args.no_evidence_a)
    b = MockAgent("candidate-b", args.b, fail=args.fail_b, no_evidence=args.no_evidence_b)
    results = run_parallel(store, args.task, [a, b], section="battle")
    print("--- Automated judging (tests, contract, evidence) ---")
    from .court import automated_score

    for r in results:
        print(f"  {r['agent']} ({r['model']}): {automated_score(r)}")
    if not args.pick:
        print("No human pick yet. Re-run with --pick a, --pick b, or --pick none to judge.")
        print("Winner is NEVER auto-merged or auto-shipped — the approval gate still fires on ship.")
        return 0
    try:
        record = judge(store, args.battle_id, results, pick=args.pick)
    except ValueError as exc:
        print(f"COURT REJECTED: {exc}")
        return 4
    _out(args, record)
    return 0


def cmd_ship(args) -> int:
    store = _store(args)
    try:
        require_approval("ship", args.candidate, approve=args.approve, confirm=args.confirm or "", expected_confirm=args.candidate)
    except GateBlocked as exc:
        print(exc)
        return 5
    print(f"APPROVED: {args.candidate} staged for ship. (Skeleton: no real ship is performed.)")
    return 0


def cmd_watch(args) -> int:
    store = _store(args)
    if getattr(args, "tui", False):
        return tui.run_tui(store)
    if getattr(args, "panes", False):
        print(tui.render_panes(store.load()))
        return 0
    print(watch.stream_json(store) if args.json else watch.render_status(store))
    return 0


def cmd_tui(args) -> int:
    store = _store(args)
    if getattr(args, "panes", False):
        print(tui.render_panes(store.load()))
        return 0
    return tui.run_tui(store)


def cmd_status(args) -> int:
    store = _store(args)
    _out(args, {"sections": store.load()["sections"], "agents": store.load()["agents"]})
    return 0


def cmd_kill(args) -> int:
    store = _store(args)
    store.kill_all()
    print("KILL SWITCH: all agents and sections stopped instantly.")
    return 0


def cmd_learn(args) -> int:
    store = _store(args)
    if args.action == "propose":
        _out(args, learning.propose(store, args.rule, evidence=args.evidence, target=args.target))
    elif args.action == "apply":
        try:
            _out(args, learning.apply_proposal(store, args.index, approve=args.approve))
        except ValueError as exc:
            print(f"LEARN BLOCKED: {exc}")
            return 6
    elif args.action == "list":
        _out(args, store.load()["learning_proposals"])
    return 0


def cmd_skill(args) -> int:
    store = _store(args)
    if args.action == "list":
        _out(args, [{k: v for k, v in s.items() if k != "text"} for s in skills.list_skills(store)])
    elif args.action == "add":
        _out(args, skills.add_skill(store, args.file))
    elif args.action == "use":
        skill = skills.use_skill(store, args.agent, args.skill)
        print(f"Agent {args.agent} used skill {skill['name']}: {skill['description']}")
        print("Steps: " + "; ".join(skill["steps"]))
    return 0


def cmd_mcp(args) -> int:
    store = _store(args)
    if args.action == "list":
        _out(args, mcp.list_servers(store))
    elif args.action == "add":
        tools = [t.strip() for t in (args.tools or "").split(",") if t.strip()]
        _out(args, mcp.add_server(store, args.name, command=args.command, transport=args.transport, tools=tools))
    elif args.action == "call":
        try:
            _out(args, mcp.call_tool(store, args.server, args.tool, approve=args.approve, confirm=args.confirm or ""))
        except _GateBlocked as exc:
            print(exc)
            return 5
        except ValueError as exc:
            print(f"MCP BLOCKED: {exc}")
            return 7
    return 0


def cmd_brain(args) -> int:
    store = _store(args)
    if args.action == "search":
        _out(args, brain.search(store, args.term or ""))
    elif args.action == "show":
        try:
            idx = int(args.term) if args.term else args.index
            _out(args, brain.show(store, idx))
        except ValueError as exc:
            print(f"BRAIN: {exc}")
            return 7
    elif args.action == "list":
        _out(args, brain.events(store))
    return 0


def cmd_goal(args) -> int:
    store = _store(args)
    if args.action == "add":
        _out(args, goals.add_goal(store, args.title, progress=args.progress))
    elif args.action == "list":
        _out(args, store.load()["goals"])
    elif args.action == "progress":
        _out(args, goals.set_goal_progress(store, args.id, args.progress))
    return 0


def cmd_task(args) -> int:
    store = _store(args)
    if args.action == "add":
        _out(args, goals.add_task(store, args.title, owner=args.owner, section=args.section))
    elif args.action == "list":
        _out(args, store.load()["tasks"])
    elif args.action == "status":
        _out(args, goals.set_task_status(store, args.id, args.status))
    return 0


def cmd_deliverable(args) -> int:
    store = _store(args)
    if args.action == "add":
        _out(args, goals.add_deliverable(store, args.title))
    elif args.action == "list":
        _out(args, goals.whats_next(store))
    elif args.action == "status":
        _out(args, goals.set_deliverable_status(store, args.id, args.status))
    return 0


def cmd_environment(args) -> int:
    store = _store(args)
    if args.action == "add":
        _out(args, goals.add_environment(store, args.name, model=args.model,
                                         skills=args.skills or [], mcp_tools=args.mcp or []))
    elif args.action == "list":
        _out(args, store.load().get("environments", {}))
    return 0


def cmd_cron(args) -> int:
    store = _store(args)
    if args.action == "add":
        _out(args, scheduler.add_job(store, args.name, args.schedule, args.task,
                                     section=args.section, model=args.model,
                                     skills=args.skills or [], mcp_tools=args.mcp or []))
    elif args.action == "list":
        _out(args, scheduler.list_jobs(store))
    elif args.action == "delete":
        try:
            _out(args, scheduler.delete_job(store, args.id))
        except ValueError as exc:
            print(f"CRON: {exc}")
            return 7
    elif args.action == "due":
        _out(args, scheduler.due_jobs(store))
    return 0


def cmd_loop(args) -> int:
    store = _store(args)
    # Demo loop body: a mock task that succeeds on the configured iteration.
    succeed_on = args.succeed_on

    def _task(i: int) -> dict:
        return {"status": "PASS" if i == succeed_on else "FAIL", "iteration": i}

    summary = scheduler.run_loop(store, _task, mode=args.mode, max_iterations=args.max,
                                 gated_action=args.gated, approve=args.approve,
                                 confirm=args.confirm or "")
    _out(args, summary)
    return 0


def cmd_tabs(args) -> int:
    store = _store(args)
    print(tui.render_tabs(store.load()))
    return 0


def cmd_rea(args) -> int:
    """REA inspect — read-only, skeleton placeholder.

    Full REA inspect (morluto/rea MCP + Ghidra evidence) is NOT yet
    implemented. This command only reports that boundary honestly and
    never writes, ships, or rebuilds anything.
    """
    print(f"REA inspect (skeleton, read-only): target={args.target}")
    print("Full REA inspect is not yet implemented. No analysis, write, or rebuild was performed.")
    print("Lawful scope only: software you own or are authorised to examine.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="framework", description="Multi-CLI agent framework — Battle Court + Evolution Engine (skeleton)")
    p.add_argument("--root", default=".", help="workspace root (default: current directory)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help='run a task with parallel agents, e.g. run "hello"')
    r.add_argument("task")
    r.add_argument("--agents", nargs="+", default=["agent-a", "agent-b"])
    r.add_argument("--section", default="default")
    r.add_argument("--skills", nargs="*", default=[])
    r.add_argument("--mcp", nargs="*", default=[], help="MCP tools as server/tool, e.g. rea/inspect")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("section", help="add / list / delete a section")
    s.add_argument("action", choices=["add", "list", "delete"])
    s.add_argument("name", nargs="?")
    s.add_argument("--role", default="builder")
    s.add_argument("--model", default="local")
    s.add_argument("--wipe", action="store_true")
    s.add_argument("--confirm", default="")
    s.set_defaults(func=cmd_section)

    a = sub.add_parser("agent", help="spawn / kill / pause / list an agent")
    a.add_argument("action", choices=["spawn", "kill", "pause", "list"])
    a.add_argument("section", nargs="?")
    a.add_argument("name", nargs="?")
    a.add_argument("--model", default="local")
    a.set_defaults(func=cmd_agent)

    c = sub.add_parser("contract", help="declare / list / check contracts")
    c.add_argument("action", choices=["declare", "list", "check"])
    c.add_argument("--agent", default="")
    c.add_argument("--file", action="append", default=[])
    c.add_argument("--api", action="append", default=[])
    c.add_argument("--schema", action="append", default=[])
    c.add_argument("--plan", default="")
    c.set_defaults(func=cmd_contract)

    b = sub.add_parser("battle", help="Battle Court v1: two candidates, judged, winner staged only")
    b.add_argument("--task", required=True)
    b.add_argument("--a", default="glm-5.3-flash:free")
    b.add_argument("--b", default="qwen3-coder:free")
    b.add_argument("--pick", choices=["a", "b", "none"], default=None)
    b.add_argument("--battle-id", default="battle-1")
    b.add_argument("--fail-a", action="store_true")
    b.add_argument("--fail-b", action="store_true")
    b.add_argument("--no-evidence-a", action="store_true")
    b.add_argument("--no-evidence-b", action="store_true")
    b.set_defaults(func=cmd_battle)

    sh = sub.add_parser("ship", help="ship a staged candidate — approval gate only")
    sh.add_argument("--candidate", required=True)
    sh.add_argument("--approve", action="store_true")
    sh.add_argument("--confirm", default="")
    sh.set_defaults(func=cmd_ship)

    w = sub.add_parser("watch", help="live watch panes / JSON stream")
    w.add_argument("--panes", action="store_true", help="render the actual TUI panes as text (capturable)")
    w.add_argument("--tui", action="store_true", help="interactive TUI (curses where available, static panes otherwise)")
    w.set_defaults(func=cmd_watch)
    tu = sub.add_parser("tui", help="open the actual UI (same as watch --tui)")
    tu.add_argument("--panes", action="store_true", help="render panes as text instead of interactive TUI")
    tu.set_defaults(func=cmd_tui)
    st = sub.add_parser("status", help="sections and agents")
    st.set_defaults(func=cmd_status)
    k = sub.add_parser("kill", help="kill switch: stop everything instantly")
    k.set_defaults(func=cmd_kill)

    le = sub.add_parser("learn", help="always-on learning proposals (proposal-only)")
    le.add_argument("action", choices=["propose", "apply", "list"])
    le.add_argument("--rule", default="")
    le.add_argument("--evidence", default="")
    le.add_argument("--target", default="")
    le.add_argument("--index", type=int, default=0)
    le.add_argument("--approve", action="store_true")
    le.set_defaults(func=cmd_learn)

    sk = sub.add_parser("skill", help="list / add / use a skill playbook")
    sk.add_argument("action", choices=["list", "add", "use"])
    sk.add_argument("agent", nargs="?")
    sk.add_argument("skill", nargs="?")
    sk.add_argument("--file", default="")
    sk.set_defaults(func=cmd_skill)

    mc = sub.add_parser("mcp", help="list / add / call an MCP server (mock calls in skeleton)")
    mc.add_argument("action", choices=["list", "add", "call"])
    mc.add_argument("--name", default="")
    mc.add_argument("--server", default="")
    mc.add_argument("--tool", default="")
    mc.add_argument("--command", default="")
    mc.add_argument("--transport", default="stdio")
    mc.add_argument("--tools", default="")
    mc.add_argument("--approve", action="store_true")
    mc.add_argument("--confirm", default="")
    mc.set_defaults(func=cmd_mcp)

    br = sub.add_parser("brain", help="search / show / list Brain events (local, file-first)")
    br.add_argument("action", choices=["search", "show", "list"])
    br.add_argument("term", nargs="?")
    br.add_argument("--index", type=int, default=0)
    br.set_defaults(func=cmd_brain)
    # brain show takes the term position as index if given
    # (handled in cmd_brain via args.index; 'brain show 3' sets term='3')

    go = sub.add_parser("goal", help="add / list / progress a long-term goal")
    go.add_argument("action", choices=["add", "list", "progress"])
    go.add_argument("title", nargs="?")
    go.add_argument("--id", type=int, default=0)
    go.add_argument("--progress", type=int, default=0)
    go.set_defaults(func=cmd_goal)

    ta = sub.add_parser("task", help="add / list / status a current task")
    ta.add_argument("action", choices=["add", "list", "status"])
    ta.add_argument("title", nargs="?")
    ta.add_argument("--id", type=int, default=0)
    ta.add_argument("--status", default="todo")
    ta.add_argument("--owner", default="")
    ta.add_argument("--section", default="")
    ta.set_defaults(func=cmd_task)

    de = sub.add_parser("deliverable", help="add / list (What's Next) / status a deliverable")
    de.add_argument("action", choices=["add", "list", "status"])
    de.add_argument("title", nargs="?")
    de.add_argument("--id", type=int, default=0)
    de.add_argument("--status", default="pending")
    de.set_defaults(func=cmd_deliverable)

    en = sub.add_parser("environment", help="add / list an agent environment (section+agent+sandbox+model+skills+MCP)")
    en.add_argument("action", choices=["add", "list"])
    en.add_argument("name", nargs="?")
    en.add_argument("--model", default="local")
    en.add_argument("--skills", nargs="*", default=[])
    en.add_argument("--mcp", nargs="*", default=[])
    en.set_defaults(func=cmd_environment)

    tabs = sub.add_parser("tabs", help="Goals / Tasks / What's Next / Cron & Loops / Environments tabs (text)")
    tabs.set_defaults(func=cmd_tabs)

    cr = sub.add_parser("cron", help="add / list / delete / due cron jobs (local scheduler)")
    cr.add_argument("action", choices=["add", "list", "delete", "due"])
    cr.add_argument("name", nargs="?")
    cr.add_argument("--schedule", default="daily")
    cr.add_argument("--task", default="")
    cr.add_argument("--section", default="default")
    cr.add_argument("--model", default="local")
    cr.add_argument("--skills", nargs="*", default=[])
    cr.add_argument("--mcp", nargs="*", default=[])
    cr.add_argument("--id", type=int, default=0)
    cr.set_defaults(func=cmd_cron)

    lo = sub.add_parser("loop", help="repeat / until_success / gated loop (mock task body in skeleton)")
    lo.add_argument("--mode", choices=["repeat", "until_success", "gated"], default="repeat")
    lo.add_argument("--max", type=int, default=3)
    lo.add_argument("--succeed-on", type=int, default=-1)
    lo.add_argument("--gated", default="")
    lo.add_argument("--approve", action="store_true")
    lo.add_argument("--confirm", default="")
    lo.set_defaults(func=cmd_loop)

    rea = sub.add_parser("rea", help="REA inspect (skeleton: read-only placeholder)")
    rea.add_argument("target")
    rea.set_defaults(func=cmd_rea)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
