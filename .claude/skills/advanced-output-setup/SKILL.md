---
name: advanced-output-setup
description: Use when setting up, normalizing, or auditing Resolume Advanced Output screens and slices for a live show. Applies to screen enablement, slice opacity/bypass normalization, screen audits, slice routing, and fast output-readiness checks.
---

# Advanced Output Setup

Use this skill when the task is about getting Resolume Advanced Output into a usable live state quickly and safely.

## Workflow

1. Inspect first.
   Start with `get_output_overview`, `get_output_screen_snapshot`, or `audit_all_output_screens`.

2. If the user needs a go/no-go summary, run:
   - `audit_output_screen`
   - `audit_all_output_screens`
   - `audit_show_readiness`

3. If the user needs normalization before routing:
   - `prepare_output_screen`
   - `prepare_multiple_output_screens`

4. For direct screen and slice control, prefer:
   - `set_output_screen_enabled`
   - `set_output_slice_bypassed`
   - `set_output_slice_opacity`
   - `set_output_screen_parameter`
   - `set_output_slice_parameter`

5. For multi-slice work, prefer:
   - `batch_set_output_slice_parameter`
   - `batch_set_output_slice_opacity`
   - `batch_set_output_slice_bypassed`

6. For routing:
   - `set_output_slice_input` for one slice
   - `route_output_slices` for multiple slices

## Preferred order

- Audit first
- Normalize second
- Route third
- Apply transforms or corners last

## Common patterns

For quick readiness:
- `audit_show_readiness`
- `audit_all_output_screens`

For one-screen prep:
- `prepare_output_screen`
- `get_output_screen_snapshot`

For full-screen batch prep:
- `prepare_multiple_output_screens`

For warp-style alignment:
- `set_output_slice_transform`
- `set_output_slice_corners`
- `set_output_screen_transform`

## Guardrails

- Do not guess slice topology if the snapshot/audit output is ambiguous.
- Use the snapshot readers before batch writes if the current routing is unclear.
- Prefer the named output helpers over hand-built long parameter paths when they cover the task.
- Fall back to `websocket_*` or `rest_*` only when the named tools do not cover the needed path cleanly.
