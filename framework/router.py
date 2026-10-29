"""Model router — local first, free next, frontier only for planner/judge.

No real model calls are made in the skeleton; this module returns the
routing decision (provider, model, tier) that a real runner would use.
It never silently upgrades to a paid model: a paid tier without explicit
approval falls back to free, then local, then pauses.
"""
from __future__ import annotations

# task_type -> (provider, model, tier) — data, not code, mirrors router.yaml
ROUTES = {
    "draft": ("ollama", "qwen3-coder:30b", "local"),
    "scout": ("ollama", "qwen3-coder:30b", "local"),
    "build": ("openrouter-free", "glm-5.3-flash:free", "free"),
    "refactor": ("openrouter-free", "glm-5.3-flash:free", "free"),
    "review": ("ollama", "devstral-small-2", "local"),
    "test": ("ollama", "qwen3-coder:30b", "local"),
    "plan": ("frontier", "claude-sonnet-4.6", "paid"),
    "judge": ("frontier", "claude-sonnet-4.6", "paid"),
    "default": ("openrouter-free", "qwen3-coder:free", "free"),
}

FALLBACK_CHAIN = ["free", "local", "pause"]


def route(task_type: str, approve_paid: bool = False) -> dict:
    provider, model, tier = ROUTES.get(task_type, ROUTES["default"])
    if tier == "paid" and not approve_paid:
        # Never silently upgrade: fall back, do not pay.
        return {
            "provider": "openrouter-free",
            "model": "qwen3-coder:free",
            "tier": "free",
            "fallback_from_paid": True,
            "paused": False,
            "note": "Paid model requested without approval; fell back to free. Approve explicitly to use the paid tier.",
        }
    return {"provider": provider, "model": model, "tier": tier, "fallback_from_paid": False, "paused": False}


def fallback_after_error(current_tier: str) -> dict:
    """free -> local -> pause. Never free -> paid on an error."""
    if current_tier == "free":
        return {"provider": "ollama", "model": "qwen3-coder:30b", "tier": "local", "paused": False}
    return {"provider": None, "model": None, "tier": "pause", "paused": True,
            "note": "Local fallback also unavailable; paused for human decision."}
