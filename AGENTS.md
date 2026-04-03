# AGENTS.md

## Project

- Product: `resolume-mcp`
- Domain: Resolume Arena / Avenue control
- Protocols: REST, WebSocket, OSC
- Main entrypoint:
- `uv run python -m resolume_mcp.server`

## Core Rules

- Keep transport behavior inside the existing `src/resolume_mcp/` client/server layers.
- Preserve live-show safety: destructive or stateful operations must stay explicit and reviewable.
- Prefer small, targeted changes. Do not redesign the surface without a concrete need.
- Add tests for every behavior change.

## Key Commands

```bash
uv sync
uv run python -m pytest -v
uv run python -m resolume_mcp.server
```

## Key Paths

- `src/resolume_mcp/server.py`: MCP server
- `src/resolume_mcp/`: protocol and tool implementation
- `tests/`: verification

## When Editing

- Preserve backward-compatible tool behavior unless a change is deliberate and documented.
- Keep docs and examples aligned with the actual tool surface.
