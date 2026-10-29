"""MCP — Model Context Protocol server registry (skeleton, mock calls).

An MCP server is a tool provider an agent can call: name, command,
transport (stdio in the skeleton), a tool list, and an allow-list.
Real MCP protocol negotiation (JSON-RPC over stdio, SSE, HTTP) is NOT
wired in this skeleton — calls below are clearly-labelled mocks that
exercise the registry, allow-list, Brain logging, and approval gate
without needing a real server or any network. Wiring a real server
replaces call_tool's mock body only; the registry, gate, and logging
contracts do not change.

Dangerous tools are approval-gated exactly like ship/send/pay/delete/
merge in gate.py: without explicit approval the call is blocked and
nothing happens.
"""
from __future__ import annotations

from pathlib import Path

from . import brain
from .gate import GateBlocked, require_approval
from .state import StateStore

DANGEROUS_TOOL_WORDS = ("send", "ship", "pay", "delete", "merge")


def is_dangerous(tool: str) -> bool:
    lowered = tool.lower()
    return any(word in lowered for word in DANGEROUS_TOOL_WORDS)


def load_config(store: StateStore) -> dict:
    """Minimal mcp.yaml reader (stdlib only, no PyYAML dependency).

    Expected shape:
      servers:
        - name: rea
          command: npx rea-agents
          transport: stdio
          tools: [inspect, decompile]
    Lines that do not parse are ignored; registry entries added via
    the CLI (state) always take precedence. The shipped <repo>/mcp.yaml
    is a fallback, so a workspace run from /tmp still sees the example
    servers — a workspace mcp.yaml wins on a name clash.
    """
    servers: dict[str, dict] = {}
    for cfg in (Path(__file__).resolve().parent.parent / "mcp.yaml",
                Path(store.root) / "mcp.yaml"):
        if not cfg.exists():
            continue
        current: dict | None = None
        for raw in cfg.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("- name:"):
                current = {"name": line.split(":", 1)[1].strip(), "transport": "stdio", "tools": []}
                servers[current["name"]] = current
            elif current is not None and ":" in line:
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if key == "tools":
                    val = val.strip("[]")
                    current["tools"] = [t.strip() for t in val.split(",") if t.strip()]
                elif key in ("command", "transport"):
                    current[key] = val
    return servers


def list_servers(store: StateStore) -> list[dict]:
    merged = dict(load_config(store))
    merged.update(store.load().get("mcp_servers", {}))
    return list(merged.values())


def get_server(store: StateStore, name: str) -> dict:
    for server in list_servers(store):
        if server.get("name") == name:
            return server
    raise ValueError(f"unknown MCP server: {name}")


def add_server(store: StateStore, name: str, command: str = "", transport: str = "stdio",
               tools: list[str] | None = None) -> dict:
    state = store.load()
    entry = {"name": name, "command": command, "transport": transport,
             "tools": tools or []}
    state.setdefault("mcp_servers", {})[name] = entry
    store.save(state)
    brain.record(store, "mcp_server_added", {"server": name, "transport": transport})
    return entry


def call_tool(store: StateStore, server_name: str, tool: str, approve: bool = False,
              confirm: str = "") -> dict:
    """Mock MCP call, fully logged, dangerous tools gated.

    Returns {"mock": True, ...} always in the skeleton. A real server
    call must keep the same logging + gating, and must never bypass
    the gate for a dangerous tool.
    """
    server = get_server(store, server_name)
    allowed = server.get("tools", [])
    if allowed and tool not in allowed:
        raise ValueError(f"MCP tool {tool!r} not in allow-list for server {server_name}: {allowed}")
    if is_dangerous(tool):
        # Map the tool to its gated action (send/ship/pay/delete/merge).
        action = next((w for w in DANGEROUS_TOOL_WORDS if w in tool.lower()), "send")
        try:
            require_approval(action, f"mcp:{server_name}/{tool}", approve=approve,
                             confirm=confirm, expected_confirm=tool)
        except GateBlocked as exc:
            brain.record(store, "mcp_call_blocked", {"server": server_name, "tool": tool})
            raise
    result = {"server": server_name, "tool": tool, "mock": True,
              "result": f"mock MCP result from {server_name}/{tool} (no real server connected in skeleton)"}
    brain.record(store, "mcp_call", {"server": server_name, "tool": tool, "mock": True})
    return result
