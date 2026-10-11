---
name: output-routing-festival
description: Use when adapting Resolume output routing quickly for festivals, guest rigs, or changed screen/slice layouts. Applies to slice input remapping, screen prep, output audits, and fast routing recovery under time pressure.
---

# Output Routing Festival

Use this skill for fast routing changes when the venue or output layout is not what the show expected.

## Requirements

The tools below drive Advanced Output over REST/WebSocket, which Arena 7.23 does not expose (every path returns `404` on the validated macOS and Windows builds). They are registered only when the server runs with `RESOLUME_EXPERIMENTAL_TOOLS=1`. Without it, work on the local XML instead: `get_advanced_output_preferences_summary`, `get_advanced_output_screen_xml` and `get_advanced_output_slice_xml` to inspect, `backup_advanced_output_preferences` first, then `set_advanced_output_slice_input_rect_xml` to re-point a slice and `set_advanced_output_screen_output_device_xml` to change its output device. Resolume may need a restart to pick the file up.

## Workflow

1. Read the current state.
   - `get_output_overview`
   - `get_output_screen_snapshot`
   - `get_output_slice_snapshot`

2. Identify broken or missing assignments.
   - `audit_output_screen`
   - `audit_all_output_screens`

3. Normalize screens before rerouting if needed.
   - `prepare_output_screen`
   - `prepare_multiple_output_screens`

4. Apply routing.
   - `set_output_slice_input` for one-off fixes
   - `route_output_slices` for multi-slice remaps

5. Re-check after changes.
   - `get_output_screen_snapshot`
   - `audit_output_screen`

## Recommended strategy

- Fix one screen at a time unless the user explicitly wants a bulk change.
- Keep routing changes separate from transform/corner changes when troubleshooting.
- If a screen is disabled or slices are bypassed, normalize that first so routing errors are not masked.

## Useful tool groups

Audit:
- `audit_output_screen`
- `audit_all_output_screens`
- `audit_show_readiness`

Prep:
- `prepare_output_screen`
- `prepare_multiple_output_screens`

Routing:
- `set_output_slice_input`
- `route_output_slices`

Fine control:
- `set_output_slice_parameter`
- `set_output_screen_parameter`

## Guardrails

- Do not overwrite multiple screens blindly if only one screen is affected.
- If the user does not specify the desired mapping, inspect first and report what exists.
- Treat screen enablement, bypass state, routing, and transform as separate layers of failure.
