# Resolume MCP Session Handover

## Purpose

This file is the current internal handoff snapshot for the private `resolume-mcp` repo.

## Current state

- Repo path: `/Users/Drohi/Projects/resolume-mcp`
- Project type: private MCP server for Resolume Arena/Avenue
- Validation status: `128 passed`
- Live validation: local Resolume instance confirmed reachable on `127.0.0.1:8080`
- Validation environment: macOS laptop
- Intended deployment environment: Windows media servers
- Live API reality on this machine:
  - composition, layer, clip, and deck parameter helpers are now aligned to `/parameter/by-id/{id}`
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
  - batch layer/column/clip selection helpers
  - selected layer and selected clip readers
  - BPM control
  - composition transport control kept build-dependent because `transport/playing` was not exposed in the validated REST payload
  - clip trigger/disconnect helpers
  - batch clip trigger/disconnect helpers
  - clip clear, selected clip clear, layer clearclips, and selected layer clearclips
  - layer prep and batch layer prep
  - playback prep helper
  - playback monitor helper
  - playback subscribe/unsubscribe helper
  - add/duplicate helpers for layers, columns, groups, and decks
  - deck open/close helpers
  - group add-layer, move-layer, and clear helpers
  - generic effect wrappers for composition, layer, group, and clip scopes:
    - add
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
  - deck subscribe/unsubscribe helpers
  - deck select helper
  - validated live deck schema currently exposes selection and scroll state, not deck transport fields

- Advanced Output:
  - output overview
  - screen snapshot and audit
  - slice snapshot
  - output parameter helpers
  - screen and slice parameter helpers
  - screen/slice subscribe helpers
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
4. Consider trimming bootstrap-heavy websocket output in named tools if operator-facing responses need to be cleaner.
5. Re-validate build-dependent selected-group and active-clip paths on a Windows target or a different Resolume build.

## Notes

- The design intentionally keeps the generic REST/WebSocket/OSC layer as the fallback for any Resolume path not yet wrapped by a named tool.
- Named tools are being added as operator-friendly workflow accelerators, not as a replacement for the generic surface.
- `docs/GETTING-STARTED.md` now exists as the first-run and connection guide.
- `docs/LIVE-VALIDATION.md` now exists with concrete findings from the local Resolume instance.
