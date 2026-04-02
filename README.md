# Resolume MCP

Private MCP server project for Resolume Arena/Avenue control.

Planned focus:
- composition and transport control
- layers, clips, columns, groups
- advanced output: screens, slices, routing, output parameter control
- playback triggers and parameter control
- safe read/write separation
- Resolume REST/OSC integration where appropriate

Status:
- generic REST / WebSocket / OSC foundation in place
- live validation completed against the local Resolume instance on this machine
- composition, layer, clip, and deck helpers now resolve live websocket parameters through `/parameter/by-id/{id}` where the local REST schema exposes them
- clip audit, batch clip trigger/disconnect, and batch layer clear helpers in place
- playback preparation helpers in place for composition and layers, with composition transport control treated as build-dependent
- playback monitoring and batch selection helpers in place
- playback subscribe/unsubscribe bundles in place
- Advanced Output screen and slice wrappers are present but currently experimental on this machine because the local Resolume 7 HTTP API returns `404` for the probed Advanced Output endpoints
- deck access and deck-parameter helpers in place
- deck snapshot and audit helpers are live-verified against the current deck schema
- deck prep and transport-style deck helpers are intentionally conservative because the validated deck schema does not expose deck transport fields
- column trigger/disconnect helpers in place
- output screen/slice parameter-path helpers in place
- output transform helper in place for common slice transform updates
- composition/layer/clip parameter monitoring helpers in place
- output screen/slice subscribe helpers in place
- output corner helper in place for common warp-style updates
- batch output helpers in place for multi-screen and multi-slice updates
- batch slice routing helper in place for fast Advanced Output input assignment
- composition overview and layer/clip snapshot readers in place
- output overview and screen/slice snapshot readers in place
- composition audit and layer audit helpers in place
- output screen audit and all-screen audit helpers in place
- output preparation helper in place for fast screen enable/unbypass/opacity setup
- multi-screen preparation helper in place
- show-readiness audit helper in place

Local skill layer:
- `advanced-output-setup`
- `deck-control-and-inspection`
- `festival-recovery-fast`
- `output-routing-festival`
- `output-warp-alignment`
- `playback-prep-and-busking`
- `show-recovery-and-triage`

Internal docs:
- `docs/GETTING-STARTED.md`
- `docs/LIVE-VALIDATION.md`
- `docs/SESSION-HANDOVER.md`
