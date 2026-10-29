"""Battle Court v1 — judge, don't just merge.

Order: automated checks first, human pick second, winner staged only.
A test-failing side, a contract-breaking side, or a side with no
evidence bundle can NEVER win, no matter how good it looks — fail-closed.
Winner = promoted to the approval queue. It is NOT auto-merged and NOT
auto-shipped; the approval gate still fires on the exact ship/merge.
Loser = stopped + archived with reasons. Tie/neither = both archived.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import brain
from .sandbox import archive_sandbox
from .state import StateStore


def automated_score(candidate: dict) -> dict:
    """Score one candidate. Disqualified if tests fail, contract breaks,
    or the evidence bundle is missing/incomplete."""
    evidence = candidate.get("evidence") or {}
    evidence_ok = bool(
        evidence.get("file") and evidence.get("test") and "unknowns" in evidence
    )
    disqualified = []
    if not candidate.get("passes_tests"):
        disqualified.append("tests failed")
    if not candidate.get("lint_pass", True):
        disqualified.append("lint failed")
    if not candidate.get("contract_ok", True):
        disqualified.append("contract broken")
    if not evidence_ok:
        disqualified.append("evidence bundle missing or incomplete — fail-closed")
    score = 0
    if candidate.get("passes_tests"):
        score += 50
    if candidate.get("lint_pass", True):
        score += 20
    if candidate.get("contract_ok", True):
        score += 20
    if evidence_ok:
        score += 10
    # Smaller, cheaper diffs win ties — but never over a test failure.
    score -= min(5, candidate.get("diff_size", 0) // 1000)
    return {"score": max(0, score), "disqualified": disqualified, "evidence_ok": evidence_ok}


def judge(store: StateStore, battle_id: str, candidates: list[dict], pick: str | None) -> dict:
    """candidates: list of orchestrator result dicts, exactly 2 in v1.
    pick: 'a' | 'b' | 'none' | None (None = no human pick yet)."""
    if len(candidates) != 2:
        raise ValueError("Court v1 requires exactly 2 candidates")
    scored = [(c, automated_score(c)) for c in candidates]
    for candidate, score in scored:
        candidate["court_score"] = score["score"]
        candidate["court_disqualified"] = score["disqualified"]

    winner = loser = None
    outcome = "no_winner"
    if pick in ("a", "b"):
        chosen = candidates[0] if pick == "a" else candidates[1]
        other = candidates[1] if pick == "a" else candidates[0]
        if automated_score(chosen)["disqualified"]:
            raise ValueError(
                f"cannot pick {chosen['agent']}: disqualified — "
                + ", ".join(automated_score(chosen)["disqualified"])
            )
        winner, loser, outcome = chosen, other, "winner"
    elif pick == "none":
        outcome = "no_winner"

    # Stage winner only; archive loser (and both on no_winner).
    staged_path = None
    if winner:
        staged_path = store.dir / "staged" / battle_id / winner["agent"]
        staged_path.mkdir(parents=True, exist_ok=True)
        src = Path(winner["sandbox"]) / "output.txt"
        if src.exists():
            shutil.copy(src, staged_path / "output.txt")
    archived = []
    to_archive = [loser] if loser else candidates
    for cand in to_archive:
        if cand is None:
            continue
        archived.append(str(archive_sandbox(store, cand["section"], cand["agent"], reason=f"battle {battle_id}: {outcome}")))

    record = {
        "battle_id": battle_id,
        "outcome": outcome,
        "winner": winner["agent"] if winner else None,
        "loser": loser["agent"] if loser else None,
        "scores": {c["agent"]: automated_score(c)["score"] for c in candidates},
        "staged": str(staged_path) if staged_path else None,
        "archived": archived,
        "shipped": False,  # Court never ships. Ship needs the approval gate.
    }
    state = store.load()
    state["battles"].append(record)
    store.save(state)
    brain.record(store, "battle", record)
    return record
