---
name: output-warp-alignment
description: Use when aligning, warping, or refining Resolume Advanced Output screen and slice geometry. Applies to transform updates, corner adjustments, screen transforms, and post-change verification.
---

# Output Warp Alignment

Use this skill when the task is geometric alignment rather than routing or playback.

## Workflow

1. Inspect the current target.
   - `get_output_screen_snapshot`
   - `get_output_slice_snapshot`

2. Decide whether the change belongs at screen or slice level.
   - Screen-wide move/scale/rotation: `set_output_screen_transform`
   - Slice-specific move/scale/rotation: `set_output_slice_transform`
   - Corner-pin style adjustment: `set_output_slice_corners`

3. Apply the smallest useful change set.

4. Re-read the target after each meaningful transform pass.

## Preferred tools

- `set_output_screen_transform`
- `set_output_slice_transform`
- `set_output_slice_corners`
- `get_output_screen_snapshot`
- `get_output_slice_snapshot`

## Guardrails

- Do not mix routing changes with transform changes during troubleshooting.
- Prefer incremental changes over large multi-parameter jumps.
- Use the snapshot readers after adjustments so the operator has a clean before/after record.
