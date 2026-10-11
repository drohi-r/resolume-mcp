<p align="center">
  <img src="assets/banner.svg" alt="Resolume MCP" width="100%">
</p>

# Resolume MCP

<p align="center">
  <a href="https://github.com/drohi-r/resolume-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-orange?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue?style=for-the-badge" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/MCP_Tools-159-9B59FF?style=for-the-badge" alt="159 MCP Tools">
</p>

An MCP server for [Resolume Arena and Avenue](https://resolume.com). Exposes 159 tools by default (209 with `RESOLUME_EXPERIMENTAL_TOOLS=1`) covering composition control, playback, Advanced Output management, and show recovery — so AI assistants can operate Resolume via REST, WebSocket, and OSC.

Built for live production. Pairs with [grandMA2 MCP](https://github.com/drohi-r/grandma2-mcp), [MADRIX MCP](https://github.com/drohi-r/madrix-mcp), [Companion MCP](https://github.com/drohi-r/companion-mcp), and [Beyond MCP](https://github.com/drohi-r/beyond-mcp) for full AI-driven show control.

## What it does

| Area | What you get |
|------|-------------|
| **Composition control** | Layers, clips, columns, groups, decks — get snapshots, trigger playback, manage media, batch operations |
| **Advanced Output** | Screen and slice management via both REST API and XML inspection. Backup, diff, rename, reroute, warp alignment |
| **Playback & monitoring** | Transport control, parameter subscriptions, state polling, show-readiness audits |
| **Effects** | Add, remove, move, rename effects across composition, layer, group, and clip scopes |
| **Safety** | 33 destructive tools gated behind `confirm_destructive=True`, plus path-based gating on the generic REST/WebSocket/OSC tools. Host allowlist. Atomic XML writes. JSONL audit log of every write |

## Quick start

```bash
# Clone and install
git clone https://github.com/drohi-r/resolume-mcp && cd resolume-mcp
uv sync

# Run the server (connects to Resolume on localhost:8080)
uv run python -m resolume_mcp
```

Make sure Resolume Arena or Avenue is running with the REST API enabled (Preferences → OSC/HTTP → HTTP API).

For remote control:
- use LAN or WireGuard, not the public internet
- set `RESOLUME_HOST` to the remote machine
- include that host in `RESOLUME_ALLOWED_HOSTS`

## Configuration

The server reads configuration from environment variables. All have sensible defaults for local development.

| Variable | Default | Description |
|----------|---------|-------------|
| `RESOLUME_HOST` | `127.0.0.1` | Resolume instance IP |
| `RESOLUME_HTTP_PORT` | `8080` | HTTP API port |
| `RESOLUME_OSC_PORT` | `7000` | OSC listener port |
| `RESOLUME_ALLOWED_HOSTS` | `127.0.0.1,localhost,::1` | Comma-separated allowlist for target hosts. Set `*` to allow any. |
| `RESOLUME_USE_HTTPS` | `false` | Use HTTPS for API calls (`true`, `yes`, `1`) |
| `RESOLUME_DOCUMENTS_ROOT` | `~/Documents/Resolume Arena` | Resolume documents path |
| `RESOLUME_ADVANCED_OUTPUT_XML` | `~/Documents/Resolume Arena/Preferences/AdvancedOutput.xml` | Advanced Output XML path |
| `RESOLUME_SLICES_XML` | `~/Documents/Resolume Arena/Preferences/slices.xml` | Slices XML path |
| `RESOLUME_AUDIT_LOG` | `~/Documents/Resolume Arena/Logs/resolume-mcp-audit.jsonl` | JSONL audit log of every write and destructive tool call. Set `off` to disable. |
| `RESOLUME_EXPERIMENTAL_TOOLS` | `false` | Also register the 50 tools that return 404 or do nothing on Arena 7.23: Advanced Output over REST/WebSocket, the `unsubscribe_*` no-ops, `prepare_deck`, `prepare_multiple_decks` and `get_node`. |

## Architecture

```mermaid
graph TD
    A["Resolume MCP Server<br/><code>resolume_mcp</code><br/>159 tools · safety gate · audit log"] --> B
    A --> C
    A --> D
    B["REST Client<br/>Composition · clips · layers · effects"] --> E
    C["WebSocket Client<br/>Parameter subscriptions · state polling"] --> E
    D["OSC Client<br/>Transport control"] --> E
    E["Resolume Arena / Avenue<br/>HTTP API on port 8080"]

    F["Advanced Output Engine<br/>XML inspection · atomic writes · backup"] -.-> A
    G["Safety Gate<br/>20 destructive ops + generic-tool path gate"] -.-> A

    style A fill:#1a1a2e,stroke:#9B59FF,color:#fff
    style B fill:#1a1a2e,stroke:#9B59FF,color:#fff
    style C fill:#1a1a2e,stroke:#9B59FF,color:#fff
    style D fill:#1a1a2e,stroke:#9B59FF,color:#fff
    style E fill:#1a1a2e,stroke:#0f3460,color:#fff
    style F fill:#0f3460,stroke:#0f3460,color:#fff
    style G fill:#0f3460,stroke:#0f3460,color:#fff
```

## Claude Desktop

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "resolume": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/resolume-mcp", "python", "-m", "resolume_mcp"],
      "env": {
        "RESOLUME_HOST": "127.0.0.1",
        "RESOLUME_HTTP_PORT": "8080",
        "RESOLUME_ALLOWED_HOSTS": "127.0.0.1,localhost,::1"
      }
    }
  }
}
```

## VS Code / Cursor

Add to `.vscode/mcp.json` in your project:

```json
{
  "servers": {
    "resolume": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/resolume-mcp", "python", "-m", "resolume_mcp"],
      "env": {
        "RESOLUME_HOST": "127.0.0.1",
        "RESOLUME_HTTP_PORT": "8080",
        "RESOLUME_ALLOWED_HOSTS": "127.0.0.1,localhost,::1"
      }
    }
  }
}
```

## Codex

Create a `codex.json` MCP config file:

```json
{
  "mcpServers": {
    "resolume": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/resolume-mcp", "python", "-m", "resolume_mcp"],
      "env": {
        "RESOLUME_HOST": "127.0.0.1",
        "RESOLUME_HTTP_PORT": "8080",
        "RESOLUME_ALLOWED_HOSTS": "127.0.0.1,localhost,::1"
      }
    }
  }
}
```

Then run Codex with:

```bash
codex --mcp-config codex.json
```

## Skills

The server includes 7 operator skills — structured workflows for common live-show scenarios:

| Skill | When to use |
|-------|-------------|
| `playback-prep-and-busking` | Preparing Resolume for a live run or operator handoff |
| `advanced-output-setup` | Setting up screens, slices, and routing for a show |
| `output-routing-festival` | Fast rerouting for festival or guest rig changes |
| `output-warp-alignment` | Aligning screen geometry and slice warping |
| `festival-recovery-fast` | Recovering a show under time pressure |
| `show-recovery-and-triage` | Diagnosing transport, output, or layer issues |
| `deck-control-and-inspection` | Managing deck snapshots, audits, and parameters |

## Safety model

- **Read operations** (snapshots, audits, parameter gets): always safe, no confirmation needed
- **Destructive operations** (clear, disconnect, remove, new/open composition, close deck, Advanced Output restore): require `confirm_destructive=True`
- **Generic tools** (`rest_*`, `websocket_*`, `set_param`, `trigger_param`, `trigger_deck_action`, `osc_send`): require `confirm_destructive=True` when the call matches a known-destructive pattern — REST `DELETE`, WebSocket `remove`, paths ending in `clear`/`clearclips`/`disconnect-all`/`disconnectall`, `/composition/new`, `/composition/open`, deck `close`, or `connect` with `false`. This is best-effort: a `set` on `/parameter/by-id/{id}` cannot be classified.
- **Host allowlisting**: only `127.0.0.1`, `localhost`, and `::1` are permitted by default. Add LAN hosts explicitly via `RESOLUME_ALLOWED_HOSTS`. Set `*` to allow any host. The `osc_send` host override is checked against the same allowlist.
- **Audit log**: every write and destructive call, confirmed or not, is appended to `RESOLUME_AUDIT_LOG` as one JSON line with timestamp, target, tool, arguments, outcome (`ok`, `confirmation_required`, `error`), duration and a short result summary (`status_code`, `verified`, `cleared`, `disconnected`, ...). Reads are not logged and payload bodies are never logged. A tool that calls other tools is recorded once.
- **Advanced Output XML writes**: atomic (temp file + rename) to prevent corruption
- **Polling loops**: crash-resilient — return last known state if Resolume becomes unreachable

## How tools report results

- Every tool has a description and MCP annotations (`readOnlyHint` / `destructiveHint`), so clients can auto-approve reads and warn before destructive calls.
- `get_composition_summary` and `get_layer_summary` give compact state (names, bypass, opacity, loaded and playing clips). The raw `get_composition`, `list_layers` and `get_layer` payloads run to hundreds of KB on real shows.
- `wait_for_resolume` polls until Arena's REST API answers after launch.
- `source:///` and `effect:///` URIs are percent-encoded automatically, so display names with spaces or parentheses work.
- Choice parameters are checked against their options before sending; a set that does not stick is resent once.
- `disconnect_clip` falls back to clearing the clip's layer when Arena ignores `connect=false` (only that clip stops; media stays). `disconnect_selected_clip` finds the selected clip's layer in the composition and does the same; `disconnect_column` clears only the layers still playing that column and reports `playing_layers_before`, `cleared_layers` and `playing_layers_after`.
- The Documents folder is found through Windows (including OneDrive redirection); `RESOLUME_DOCUMENTS_ROOT` also moves the default XML paths.
- Parameter reads come from the REST payload, one request per layer/clip/deck. WebSocket results report `bootstrap_message_count` instead of embedding Resolume's startup state.
- Named `set_*` tools verify by reading the value back over REST: `value_before`, `value_after`, `verified`.
- `subscribe_*` tools watch for `duration_s` seconds (max 30) on one connection and return the updates received. Subscriptions end when the call returns, so the `unsubscribe_*` no-ops are only registered with `RESOLUME_EXPERIMENTAL_TOOLS=1`.
- Advanced Output over REST/WebSocket returns 404 on Arena 7.23 (macOS and Windows), so those tools are hidden unless `RESOLUME_EXPERIMENTAL_TOOLS=1`. The `*_xml` tools work on the local `AdvancedOutput.xml` and are always registered.
- WebSocket `get` waits at most 2 s for the matching reply (`reply_timed_out` says if none came); other actions are fire-and-forget.
- If Resolume is unreachable, the error names the URL and what to check.

## Development

```bash
# Install and sync dependencies
uv sync

# Run tests
uv run python -m pytest -v
```

## License

[Apache 2.0](LICENSE)
