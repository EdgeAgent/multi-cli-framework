"""Always-on learning — proposal-only, never write-and-act.

Learning runs under every mode, but it is read + propose, not write +
act. At most ONE rule change per cycle, human approval before it takes
effect, and it can NEVER touch the immutable core (gate, safety lists,
keys, kill switch, auto-send/ship/pay/delete). A proposal touching the
core is auto-rejected here, before it ever reaches a human.
"""
from __future__ import annotations

from .gate import check_immutable
from .state import StateStore


def propose(store: StateStore, rule: str, evidence: str = "", target: str = "") -> dict:
    """Propose exactly one rule. Returns the proposal with status
    'rejected' (core touch or empty rule) or 'pending' (needs human approval)."""
    state = store.load()
    if not rule.strip():
        proposal = {"rule": rule, "status": "rejected", "reason": "empty rule"}
    elif check_immutable(target) or check_immutable(rule):
        proposal = {
            "rule": rule, "target": target, "status": "rejected",
            "reason": "touches immutable core (approval gate / safety / keys / kill switch) — auto-rejected",
        }
    else:
        proposal = {"rule": rule, "target": target, "evidence": evidence, "status": "pending"}
    state["learning_proposals"].append(proposal)
    store.save(state)
    return proposal


def apply_proposal(store: StateStore, index: int, approve: bool = False) -> dict:
    """Apply a pending proposal only with explicit human approval.
    Rejected proposals can never be applied."""
    state = store.load()
    proposal = state["learning_proposals"][index]
    if proposal["status"] != "pending":
        raise ValueError(f"cannot apply proposal with status {proposal['status']}")
    if not approve:
        raise ValueError("learning proposal requires explicit human approval")
    proposal["status"] = "applied"
    state["router_overrides"][proposal.get("target", "general")] = proposal["rule"]
    store.save(state)
    return proposal
