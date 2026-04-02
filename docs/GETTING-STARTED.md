# Getting Started

## Purpose

This document is the first-run guide for the private `resolume-mcp` repo.

## Requirements

- Python `3.12+`
- `uv`
- Resolume Arena or Avenue reachable on the target host
- Resolume API access enabled for the host/port you plan to use

## Default config

Environment variables:

- `RESOLUME_HOST`
  - default: `127.0.0.1`
- `RESOLUME_HTTP_PORT`
  - default: `8080`
- `RESOLUME_OSC_PORT`
  - default: `7000`
- `RESOLUME_USE_HTTPS`
  - default: `0`

## Local setup

From the repo root:

```bash
uv sync
```

## Run tests

```bash
uv run python -m pytest -q
```

## Verify config

Use the MCP tool:

- `get_server_config`

This confirms the effective HTTP base URL, WebSocket URL, and OSC port.

Important:

- WebSocket should resolve to `/api/v1`
- example: `ws://127.0.0.1:8080/api/v1`

## First connection checks

Start with read-only validation:

1. `get_server_config`
2. `get_composition`
3. `get_composition_overview`
4. `get_output_overview`
5. `audit_show_readiness`

If those work, the basic HTTP/WebSocket surface is behaving.

For actual live-instance notes from this machine, see:

- `docs/LIVE-VALIDATION.md`

## First safe operator checks

Playback:

1. `audit_composition`
2. `get_layer_snapshot`
3. `get_clip_snapshot`

Output:

1. Verify first that your local Resolume build actually exposes Advanced Output over HTTP.
2. If it does, start with `audit_all_output_screens`
3. Then use `get_output_screen_snapshot` and `get_output_slice_snapshot`

Decks:

1. `list_decks`
2. `get_deck_snapshot`
3. `audit_deck`

## First controlled write checks

Use minimal-impact writes first:

- `set_composition_playing`
- `set_composition_bpm`
- `prepare_layer`
- `prepare_output_screen`
- `prepare_deck`

Do not jump straight to batch writes until the single-surface writes behave as expected against the target Resolume instance.

Notes:

- On the validated local Resolume 7 build used for this repo, `set_composition_playing` is treated as build-dependent because composition transport was not exposed in the REST payload.
- On that same build, Advanced Output HTTP endpoints returned `404`, so output helpers should be treated as experimental until your target machine exposes them.
- Deck helpers are live-verified for selection and scroll state; they do not currently assume hidden deck transport controls.

## Design note

This repo intentionally keeps:

- generic REST helpers
- generic WebSocket helpers
- generic OSC helper

as the fallback full-surface access layer.

The named tools are operator-friendly wrappers built on top of that base.
