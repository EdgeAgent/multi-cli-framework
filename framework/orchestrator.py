"""Parallel runner — mock agents in the skeleton (clearly labelled).

A mock agent writes its output to its own sandbox only, never to a
shared directory, so two parallel agents cannot overwrite each other.
Replace MockAgent.run with a real CLI runner (Codex / OpenCode / Pi /
local Ollama) in a later step — the isolation, watch, and gate
contracts around it do not change.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import brain, mcp, skills
from .sandbox import create_sandbox
from .state import StateStore


class MockAgent:
    """Deterministic stand-in for a real model/CLI agent.

    fail=True simulates a failing agent (tests fail). no_evidence=True
    simulates an agent that makes a claim without an evidence bundle —
    Court must disqualify it, fail-closed.
    """

    def __init__(self, name: str, model: str, fail: bool = False, no_evidence: bool = False,
                 skills: list[str] | None = None, mcp_tools: list[str] | None = None):
        self.name = name
        self.model = model
        self.fail = fail
        self.no_evidence = no_evidence
        self.skill_names = list(skills or [])
        self.mcp_tools = list(mcp_tools or [])

    def run(self, store: StateStore, section: str, task: str) -> dict:
        sandbox = create_sandbox(store, section, self.name)
        started = time.time()
        # An agent run = model + skills + MCP tools + Brain context.
        # Skills are playbooks, not prompts: load them, record the use.
        loaded_skills = []
        for skill_name in self.skill_names:
            try:
                loaded_skills.append(skills.use_skill(store, self.name, skill_name)["name"])
            except ValueError:
                loaded_skills.append(f"{skill_name} (unknown — skipped, recorded)")
                brain.record(store, "skill_missing", {"agent": self.name, "skill": skill_name})
        mcp_results = []
        for spec in self.mcp_tools:
            if "/" not in spec:
                continue
            server, tool = spec.split("/", 1)
            try:
                mcp_results.append(mcp.call_tool(store, server, tool))
            except Exception as exc:  # noqa: BLE001 — one bad tool must not kill the run
                mcp_results.append({"server": server, "tool": tool, "error": str(exc)})
        brain_context = brain.relevant(store, task=task, agent=self.name)
        # Simulate work; real runners replace this block only.
        time.sleep(0.01)
        output = sandbox / "output.txt"
        output.write_text(f"agent={self.name}\nmodel={self.model}\ntask={task}\nresult={'FAIL' if self.fail else 'PASS'}\n")
        evidence = None
        if not self.no_evidence:
            evidence = {
                "file": "output.txt",
                "line": 1,
                "test": "output contains PASS" if not self.fail else "output contains FAIL",
                "unknowns": ["mock agent: no real model was called"],
            }
            (sandbox / "evidence.json").write_text(json.dumps(evidence, indent=2))
        result = {
            "agent": self.name,
            "model": self.model,
            "section": section,
            "sandbox": str(sandbox),
            "passes_tests": not self.fail,
            "lint_pass": not self.fail,
            "contract_ok": True,
            "diff_size": len(output.read_text()),
            "cost": 0.0,  # mock: no real spend
            "time_seconds": round(time.time() - started, 3),
            "evidence": evidence,
            "status": "failed" if self.fail else "done",
            "skills": loaded_skills,
            "mcp_tools": [r.get("tool") for r in mcp_results],
            "brain_context": [e.get("type") for e in brain_context],
        }
        brain.record(store, "run", {"agent": self.name, "task": task, "status": result["status"],
                                     "skills": loaded_skills,
                                     "mcp_tools": result["mcp_tools"]})
        return result


def run_parallel(store: StateStore, task: str, agents: list[MockAgent], section: str = "default") -> list[dict]:
    """Wave-based parallel run: all agents in one wave, one dead agent
    never kills the wave — it is marked failed and the wave continues."""
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, len(agents))) as pool:
        futures = [pool.submit(agent.run, store, section, task) for agent in agents]
        for future in futures:
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 — one dead agent must not kill the wave
                results.append({"agent": "unknown", "status": "failed", "error": str(exc), "passes_tests": False})
    state = store.load()
    state["runs"].append({"task": task, "section": section, "results": results})
    store.save(state)
    return results
