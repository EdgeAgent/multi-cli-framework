"""Approval gate + kill switch — the immutable core.

Nothing in this file may be weakened by learning, by a battle winner,
or by any agent. Learning proposals that touch these names are rejected
automatically in learning.py, before they ever reach a human.
"""
from __future__ import annotations

IMMUTABLE_CORE = frozenset(
    {
        "approval_gate",
        "safety_list",
        "scrub_list",
        "keys",
        "credentials",
        "kill_switch",
        "auto_send",
        "auto_ship",
        "auto_pay",
        "auto_delete",
        "auto_merge",
    }
)

BLOCKED_ACTIONS = ("send", "ship", "pay", "delete", "merge")


class GateBlocked(Exception):
    """Raised when an approval-gated action is attempted without approval."""


def require_approval(action: str, detail: str, approve: bool = False, confirm: str = "", expected_confirm: str = "") -> None:
    """Block send/ship/pay/delete/merge unless explicitly approved.

    For destructive actions (ship/merge/delete) a confirm string matching
    the exact target is also required, so a bare --approve flag is not
    enough to ship something by accident.
    """
    if action not in BLOCKED_ACTIONS:
        return
    if not approve:
        raise GateBlocked(
            f"APPROVAL GATE BLOCKED: {action} '{detail}' was NOT approved. "
            "Re-run with explicit approval — nothing was sent, shipped, paid, deleted, or merged."
        )
    if action in ("ship", "merge", "delete") and expected_confirm and confirm != expected_confirm:
        raise GateBlocked(
            f"APPROVAL GATE BLOCKED: {action} '{detail}' confirm does not match "
            f"expected '{expected_confirm}'. Nothing was {action}ed."
        )


def check_immutable(target: str) -> bool:
    """True if a learning proposal target touches the immutable core."""
    lowered = target.lower()
    return any(word in lowered for word in IMMUTABLE_CORE)
