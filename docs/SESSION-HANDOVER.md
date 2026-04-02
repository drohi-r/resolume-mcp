# Resolume MCP Session Handover

## Purpose

This file is the current internal handoff snapshot for the private `resolume-mcp` repo.

## Current state

- Repo path: `/Users/Drohi/Projects/resolume-mcp`
- Project type: private MCP server for Resolume Arena/Avenue
- Validation status: `83 passed`
- Live validation: local Resolume instance confirmed reachable on `127.0.0.1:8080`
- Live API reality on this machine:
  - composition, layer, clip, and deck parameter helpers are now aligned to `/parameter/by-id/{id}`
  - Advanced Output HTTP paths currently return `404`

## Current capability shape

- Generic full-surface access:
  - REST request helpers
  - WebSocket verb helpers
  - OSC send helper

- Composition and playback:
  - composition overview and audit
  - layer snapshot and audit
  - clip snapshot and audit
  - batch layer/column/clip selection helpers
  - BPM control
  - composition transport control kept build-dependent because `transport/playing` was not exposed in the validated REST payload
  - clip trigger/disconnect helpers
  - batch clip trigger/disconnect helpers
  - layer prep and batch layer prep
  - playback prep helper
  - playback monitor helper
  - playback subscribe/unsubscribe helper

- Decks:
  - deck list and single-deck read
  - deck parameter get/set/trigger/reset
  - deck snapshot
  - deck audit
  - deck prep helper
  - batch deck prep helper
  - deck monitor helper
  - deck subscribe/unsubscribe helpers
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
2. Add startup examples for the eventual MCP host/client integration path.
3. Decide when to commit and initialize remote/private git hosting for this repo.
4. Consider trimming bootstrap-heavy websocket output in named tools if operator-facing responses need to be cleaner.

## Notes

- The design intentionally keeps the generic REST/WebSocket/OSC layer as the fallback for any Resolume path not yet wrapped by a named tool.
- Named tools are being added as operator-friendly workflow accelerators, not as a replacement for the generic surface.
- `docs/GETTING-STARTED.md` now exists as the first-run and connection guide.
- `docs/LIVE-VALIDATION.md` now exists with concrete findings from the local Resolume instance.
