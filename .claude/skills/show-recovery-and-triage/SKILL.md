---
name: show-recovery-and-triage
description: Use when Resolume is not behaving correctly during setup or live playback and the task is to diagnose readiness, transport state, output state, or layer/clip issues quickly. Applies to composition audits, layer audits, output audits, and snapshot-driven recovery.
---

# Show Recovery And Triage

Use this skill when the operator needs a fast diagnosis rather than an immediate blind write.

## Workflow

1. Start with the broadest useful audit.
   - `audit_show_readiness`
   - `audit_composition`
   - `audit_all_output_screens`

2. Narrow to the failing area.
   - Output problem: `audit_output_screen`, `get_output_screen_snapshot`, `get_output_slice_snapshot`
   - Playback problem: `get_composition_overview`, `get_layer_snapshot`, `get_clip_snapshot`
   - Layer problem: `audit_layer`, `get_layer_snapshot`

3. If the issue is clearly operational, use the smallest write that resolves it.
   - `set_composition_playing`
   - `set_composition_bpm`
   - `set_layer_opacity`
   - `bypass_layer`
   - `bypass_clip`
   - `prepare_output_screen`

4. Re-read the affected state after every meaningful write.

## Practical triage order

- Is composition transport stopped?
- Is BPM unset or wrong?
- Is the layer bypassed?
- Is opacity at zero?
- Is the clip disconnected?
- Is the output screen disabled?
- Are slices bypassed or unrouted?

## Preferred tools

Broad checks:
- `audit_show_readiness`
- `audit_composition`
- `audit_all_output_screens`

Detail checks:
- `get_layer_snapshot`
- `get_clip_snapshot`
- `get_output_screen_snapshot`
- `get_output_slice_snapshot`

Recovery writes:
- `set_composition_playing`
- `set_layer_opacity`
- `bypass_layer`
- `bypass_clip`
- `prepare_output_screen`

## Guardrails

- Audit before changing multiple surfaces at once.
- Avoid mixing playback fixes and output fixes in the same step unless the failure chain is already clear.
- Use `prepare_output_screen` only when its normalization behavior matches the recovery goal.
