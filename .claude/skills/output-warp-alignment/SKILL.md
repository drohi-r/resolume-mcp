---
name: output-warp-alignment
description: Use when aligning, warping, or refining Resolume Advanced Output screen and slice geometry. Applies to transform updates, corner adjustments, screen transforms, and post-change verification.
---

# Output Warp Alignment

Use this skill when the task is geometric alignment rather than routing or playback.

## Requirements

The tools below drive Advanced Output over REST/WebSocket, which Arena 7.23 does not expose (every path returns `404` on the validated macOS and Windows builds). They are registered only when the server runs with `RESOLUME_EXPERIMENTAL_TOOLS=1`. Without it, work on the local XML instead: `get_advanced_output_preferences_summary`, `get_advanced_output_screen_xml` and `get_advanced_output_slice_xml` to inspect, `backup_advanced_output_preferences` first, then `set_advanced_output_slice_output_rect_xml` for position and size and `set_advanced_output_slice_homography_dst_xml` for corner-pin warps. Resolume may need a restart to pick the file up.

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
