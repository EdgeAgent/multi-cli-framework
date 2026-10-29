"""CLI entry: `framework <command>`.

All commands accept --root (workspace root, default: current directory)
and --json (machine-readable output where it makes sense).
No real model calls are made in the skeleton — agents are mocks.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import brain, contracts, learning, router, tui, watch
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
    agents = [MockAgent(name, router.route("build")["model"]) for name in args.agents]
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
