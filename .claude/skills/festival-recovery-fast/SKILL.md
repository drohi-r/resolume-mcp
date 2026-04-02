---
name: festival-recovery-fast
description: Use when a Resolume show must be recovered quickly under venue or festival pressure. Applies to show-readiness audits, playback prep, output prep, rerouting, and narrowing failures to transport, layer, clip, or output state.
---

# Festival Recovery Fast

Use this skill when time pressure matters more than elegant sequencing and the goal is a fast stable show state.

## Workflow

1. Start broad.
   - `audit_show_readiness`

2. Split the failure:
   - Playback side: `audit_composition`, `audit_layer`, `audit_clip`
   - Output side: `audit_all_output_screens`, `audit_output_screen`

3. Normalize the failing side first.
   - Playback: `prepare_playback`, `prepare_layer`, `prepare_multiple_layers`
   - Output: `prepare_output_screen`, `prepare_multiple_output_screens`

4. If routing is the issue:
   - `route_output_slices`
   - `set_output_slice_input`

5. Re-audit before moving to the next failure layer.

## Practical order

- Is transport running?
- Are the critical layers unbypassed and visible?
- Are the needed clips connected?
- Are the screens enabled?
- Are slices unbypassed and routed?
- Are transforms the actual problem after routing is fixed?

## Guardrails

- Do not jump into warp/alignment changes before confirming routing and enable/bypass state.
- Keep playback prep and output prep logically separate in the terminal output.
- Re-run `audit_show_readiness` after a recovery pass to confirm the remaining issues actually narrowed.
