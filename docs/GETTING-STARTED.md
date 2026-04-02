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
- `RESOLUME_DOCUMENTS_ROOT`
  - default on the current macOS validation machine: `~/Documents/Resolume Arena`
- `RESOLUME_ADVANCED_OUTPUT_XML`
  - default on the current macOS validation machine: `~/Documents/Resolume Arena/Preferences/AdvancedOutput.xml`
- `RESOLUME_SLICES_XML`
  - default on the current macOS validation machine: `~/Documents/Resolume Arena/Preferences/slices.xml`

Important:

- The current repo defaults for XML-backed Advanced Output paths are based on the macOS validation machine.
- For Windows media servers, set the XML path environment variables explicitly so the repo points at the correct Resolume documents/preferences locations on that host.
- Use `get_windows_advanced_output_path_candidates` for likely Windows path shapes.
- Use `probe_advanced_output_paths` on the actual server host to verify the configured paths resolve locally.

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

1. Start with `get_advanced_output_preferences_summary`
2. Then use `get_advanced_output_screen_xml`
3. Then use `get_advanced_output_slice_xml`
4. Use `backup_advanced_output_preferences` before any manual output changes
5. Use `diff_advanced_output_preferences` to compare setups safely
6. Use `export_advanced_output_preferences` to capture a portable bundle
7. Use `preview_restore_advanced_output_preferences` before any restore

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
- On that same build, Advanced Output is persisted to XML under `~/Documents/Resolume Arena/Preferences`, and the repo now has read-only XML tools for that surface.
- The above XML path finding was validated on macOS only. Windows deployment paths should be treated as host-specific configuration, not assumed to match the macOS defaults.
- The XML write helpers currently added are intentionally narrow:
  - rename screen
  - rename slice
  - set soft-edge power
  - set output device attributes
  - set input rect vertices
  - set output rect vertices
  - set homography destination vertices
- They are backup-first file edits, not proof of live reload behavior inside Resolume.
- Deck helpers are live-verified for selection and scroll state; they do not currently assume hidden deck transport controls.

## Design note

This repo intentionally keeps:

- generic REST helpers
- generic WebSocket helpers
- generic OSC helper

as the fallback full-surface access layer.

The named tools are operator-friendly wrappers built on top of that base.
