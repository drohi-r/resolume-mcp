# AGENTS.md

## Project

- Product: `resolume-mcp`
- Domain: Resolume Arena / Avenue control
- Protocols: REST, WebSocket, OSC
- Main entrypoint:
- `uv run python -m resolume_mcp`

## Core Rules

- Keep transport behavior inside the existing `src/resolume_mcp/` client/server layers.
- Preserve live-show safety: destructive or stateful operations must stay explicit and reviewable.
- Register every tool through `_tool(...)` in `server.py`. Write and destructive tools are then appended to the JSONL audit log automatically; tools that return 404 or do nothing on the validated Arena build get `experimental=True`.
- Prefer small, targeted changes. Do not redesign the surface without a concrete need.
- Add tests for every behavior change.

## Key Commands

```bash
uv sync
uv run python -m pytest -v
uv run python -m resolume_mcp
```

## Key Paths

- `src/resolume_mcp/server.py`: MCP server
- `src/resolume_mcp/audit.py`: JSONL audit log of write and destructive calls
- `src/resolume_mcp/`: protocol and tool implementation
- `tests/`: verification

## When Editing

- Preserve backward-compatible tool behavior unless a change is deliberate and documented.
- Keep docs and examples aligned with the actual tool surface.
