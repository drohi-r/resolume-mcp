---
name: fleet-role
description: Use when resolume-mcp (strauss-visuals/resolume-mcp) needs to act within the strauss-visuals MCP fleet — its own node identity and boundary, which siblings it talks to and why, and how it relates to the render fleet. Complements the generated strauss-fleet skill (the fleet-wide directory); this one is resolume-mcp's specific place in the mesh.
---

# resolume-mcp — role in the strauss-visuals fleet

resolume-mcp is the vendored upstream `drohi-r/resolume-mcp`: an MCP server
exposing ~206 tools for Resolume Arena/Avenue composition control, Advanced
Output management, playback/transport, effects, and show-recovery, talking to
a live Resolume instance over REST, WebSocket, and OSC. This repo hosts no
fleet node itself (the canonical registry's `resolume` node is `planned`, not
sourced from here); it is a pure CONSUMER node-wise. Its `.mcp.json` now
wires it to every enabled fleet node, and its own local `resolume` server
(the direct Resolume connection this repo exists to provide) is preserved
alongside them.

## What this repo exposes

This repo hosts no fleet node; it is a consumer of the fleet. Its domain —
driving Resolume Arena for live output — is exactly what the eventual
`strauss-mcp` `resolume` node and mythos-grid's `resolume-community-mcp`
plugin also target; the overlap between all three is recorded elsewhere
(strauss-mcp / mythos-grid briefs) as intentionally unmerged, not deduplicated
here.

## Who this repo talks to

- `render-fleet` (read_only) — the render-fleet coordinator's probe; relevant
  because generated visuals produced elsewhere in the fleet ultimately need to
  land in a Resolume composition this repo controls.
- `horizon360`, `image-sequencer-pro`, `seamfix` (all local_write) — the
  render-chain repos that actually produce equirect/dome/sequence output;
  this repo is the natural consumer of their finished media for the live
  venue feed.
- `evidencer` (local_write) and `wikid` (read_only) — status/evidence and
  project-context reads, safe to call for show-readiness bookkeeping.

## Render fleet

resolume-mcp does not dispatch render-fleet coordinator jobs itself (no
signed client here) — but it is the natural downstream consumer of what the
render chain produces: horizon360/image-sequencer-pro/seamfix generate or
repair visual assets, sequence them, and hand off finished media that this
repo's Resolume tools (media management, layer/clip triggering) then load
into the live composition for the venue feed. The `render-fleet` node itself
stays a READ-ONLY probe (`check_coordinator`, `coordinator_health`) — job
submission stays with those signed per-repo clients, never this repo.

## Boundary discipline

Call any sibling through its namespaced `<node>__<tool>` name so gateway
policy, approval, audit, and circuit-breaker stay in the loop — never a
sibling's server directly. `read_only` / `local_verify` / `generated_evidence`
are safe to call; anything `local_write` or more permissive is plan-only —
confirm with a human first, never inferring consent from an earlier approval.
This repo's own `resolume` server drives a live venue system directly:
destructive Resolume operations (composition clear, layer changes affecting
a live show) warrant the same care as any `live_system`-boundary sibling call.
