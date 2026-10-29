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

from . import brain
from .sandbox import create_sandbox
from .state import StateStore


class MockAgent:
    """Deterministic stand-in for a real model/CLI agent.

    fail=True simulates a failing agent (tests fail). no_evidence=True
    simulates an agent that makes a claim without an evidence bundle —
    Court must disqualify it, fail-closed.
    """

    def __init__(self, name: str, model: str, fail: bool = False, no_evidence: bool = False):
        self.name = name
        self.model = model
        self.fail = fail
        self.no_evidence = no_evidence

    def run(self, store: StateStore, section: str, task: str) -> dict:
        sandbox = create_sandbox(store, section, self.name)
        started = time.time()
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
        }
        brain.record(store, "run", {"agent": self.name, "task": task, "status": result["status"]})
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
