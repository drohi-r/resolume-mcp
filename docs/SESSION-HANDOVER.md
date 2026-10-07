# Resolume MCP Session Handover

## Purpose

This file is the current internal handoff snapshot for the public `resolume-mcp` repo.

## Current state

- Repo path: wherever this repo is cloned (e.g. `C:\Users\<user>\resolume-mcp` on the Windows media servers)
- Project type: private MCP server for Resolume Arena/Avenue
- Validation status: `256 passed` (2026-10-08, Windows)
- Live validation: local Resolume instance confirmed reachable on `127.0.0.1:8080`
- Validation environment: macOS laptop
- Intended deployment environment: Windows media servers
- Live API reality on this machine:
  - composition, layer, clip, and deck parameter helpers are now aligned to `/parameter/by-id/{id}`
  - some collection endpoints return `404` even though the same data is embedded in parent objects
  - named list/snapshot/audit helpers now fall back to embedded `/composition` and `/composition/layers/{n}` data where needed
  - `trigger_clip` is live-proven on a loaded media clip
  - `set_clip_speed` and `set_clip_transport_position` are live-proven on a loaded media clip, with the normal caveat that position keeps advancing while playback runs
  - on `2026-04-02`, positional, selected, and by-id disconnect were all revalidated after triggering a real clip to `Connected`; all returned `204` but the clip remained connected
  - `insert_clip` is live-proven when given an array of `file://` URIs
  - `open` is now live-proven when the request body is sent as raw `text/plain` with a single `file:///...` URL
  - `openfile` shares the same documented `text/plain` contract but remains un-rechecked after the transport fix because the endpoint is deprecated upstream
  - on `2026-04-02`, positional clear, selected clear, by-id clear, layer `clearclips`, and selected-layer `clearclips` were all revalidated live and did clear media on this build
  - clear verification needs short post-call polling because an immediate read can still show stale `video` and `audio` nodes after the server already reports `204`
  - `effects/video/add/{offset}` is now live-proven on a temporary inserted slot when sent as raw `text/plain effect:///...`
  - clip-effect delete by grid position is also live-proven on the same slot
  - product, effects, sources, and file-info discovery endpoints are live-proven and now wrapped by named tools
  - selected-clip trigger/disconnect and thumbnail-revert helpers are now wrapped
  - selected-layergroup and group-column endpoints still return `404` on this mac build, so those helpers are repo-tested but not live-proven here
  - Advanced Output HTTP paths currently return `404`
  - Advanced Output is persisted locally as XML in `~/Documents/Resolume Arena/Preferences`
  - those XML path findings are macOS-specific and should be reconfigured or revalidated on Windows hosts

## Current capability shape

- Generic full-surface access:
  - REST request helpers
  - WebSocket verb helpers
  - OSC send helper

- Composition and playback:
  - composition overview and audit
  - composition new/open/save/grow-to
  - disconnect-all
  - layer snapshot and audit
  - clip snapshot and audit
  - source/media helpers for clip open, openfile, insert, and thumbnail refresh
  - product/effects/sources/files discovery helpers
  - thumbnail revert helpers for clip and selected clip
  - batch layer/column/clip selection helpers
  - selected layer and selected clip readers
  - BPM control
  - composition transport control kept build-dependent because `transport/playing` was not exposed in the validated REST payload
  - clip trigger/disconnect helpers
  - selected clip trigger/disconnect helpers
  - batch clip trigger/disconnect helpers
  - clip clear, selected clip clear, layer clearclips, and selected layer clearclips
  - layer prep and batch layer prep
  - playback prep helper
  - playback monitor helper
  - playback watch helper (`subscribe_playback_state` collects updates for `duration_s`; unsubscribe is a no-op)
  - add/duplicate helpers for layers, columns, groups, and decks
  - deck open/close helpers
  - group add-layer, move-layer, and clear helpers
  - selected group clear helper
  - group-column get/select/connect helpers
  - generic effect wrappers for composition, layer, group, and clip scopes:
    - add
    - remove
    - get
    - video move
    - display-name rename

- Decks:
  - deck list and single-deck read
  - deck parameter get/set/trigger/reset
  - deck snapshot
  - deck audit
  - deck prep helper
  - batch deck prep helper
  - deck monitor helper
  - deck watch helpers (`subscribe_decks` collects updates for `duration_s`; unsubscribe is a no-op)
  - deck select helper
  - validated live deck schema currently exposes selection and scroll state, not deck transport fields

- Advanced Output:
  - output overview
  - screen snapshot and audit
  - slice snapshot
  - output parameter helpers
  - screen and slice parameter helpers
  - screen/slice watch helpers
  - transform helpers
  - corner helper
  - batch screen/slice update helpers
  - slice routing helper
  - screen prep and multi-screen prep
  - all-screen audit
  - current status on this machine: experimental, because the local Resolume 7 API does not expose Advanced Output HTTP paths
  - XML-backed tools now available:
    - summary
    - screen inspection
    - slice inspection
    - Windows path candidates
    - local path probe
    - backup
    - diff
    - export bundle
    - preview restore
    - backup-first restore
    - guarded XML edits for screen name, slice name, and soft-edge power
    - guarded XML edits for output device, input rect, output rect, and homography destination

## Local skills currently present

- `advanced-output-setup`
- `deck-control-and-inspection`
- `festival-recovery-fast`
- `output-routing-festival`
- `output-warp-alignment`
- `playback-prep-and-busking`
- `show-recovery-and-triage`

## Recommended next work

1. Re-validate all Advanced Output wrappers against a build/control path that actually exposes Advanced Output.
2. Decide whether to add controlled XML write/import helpers after confirming safe reload behavior.
3. Add startup examples for the eventual MCP host/client integration path.
4. Live-check on Windows: WebSocket `set` delivery when the connection closes right after sending, the reply/update message format used for matching, and the `select_clip`/`select_layer`/`select_column` paths. Run `uv run python scripts/live_probe.py --write-checks` against a test composition.
5. Re-validate build-dependent selected-group and active-clip paths on a Windows target or a different Resolume build.

### Gaps found in the AvoidRafa show sessions (Arena 7.23.2, Sep–Oct 2026)

Those sessions bypassed the MCP for most Resolume work (about 96 direct REST calls and 83 `.avc` edits against 32 MCP calls). Already fixed on `feat/mcp-improvements`: oversized reads, the 1 MiB WebSocket limit, unclear connection errors, URI encoding, choice-parameter validation and set retry, the `disconnect_clip` fallback, OneDrive Documents detection, save/open 404 guidance, and `wait_for_resolume`. Still open, roughly by impact:

6. Offline composition (`.avc`) editing with Arena closed: per-clip SMPTE offset (not exposed over REST), moving or reordering layers and clips, removing layers or columns. The show needed custom scripts and several Arena restarts for this.
7. Advanced Output presets (`Presets\Advanced Output\*.xml`): create screens and slices, set NDI or DMX output devices, re-point slice inputs after a layer reorder.
8. Clip setup helpers: transport type (Timeline / BPM Sync / SMPTE n), play mode, column-trigger behavior, resize, plus column add/rename and composition resolution.
9. Parameter access by id over REST (`/parameter/by-id/{id}`); the show scripts used it directly.

## Notes

- The design intentionally keeps the generic REST/WebSocket/OSC layer as the fallback for any Resolume path not yet wrapped by a named tool.
- Named tools are being added as operator-friendly workflow accelerators, not as a replacement for the generic surface.
- `docs/GETTING-STARTED.md` now exists as the first-run and connection guide.
- `docs/LIVE-VALIDATION.md` now exists with concrete findings from the local Resolume instance.
