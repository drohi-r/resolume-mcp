---
name: playback-prep-and-busking
description: Use when preparing Resolume playback for a live run, busking session, or operator handoff. Applies to transport prep, layer normalization, clip triggering, clip disconnects, and fast playback checks.
---

# Playback Prep And Busking

Use this skill when the task is about getting playback into a clean live-ready state quickly.

## Workflow

1. Read the current playback state first.
   - `audit_composition`
   - `get_composition_overview`
   - `get_layer_snapshot`
   - `get_clip_snapshot`

2. Normalize playback state if needed.
   - `prepare_playback`
   - `prepare_layer`
   - `prepare_multiple_layers`

3. Trigger or disconnect playback content.
   - `trigger_clip`
   - `trigger_clips`
   - `disconnect_clip`
   - `disconnect_clips`
   - `trigger_column`
   - `disconnect_column`

4. Re-check the affected layer or clip after major changes.

## Common patterns

For a fast live-ready pass:
- `audit_composition`
- `prepare_playback`

For a single-layer correction:
- `audit_layer`
- `prepare_layer`

For batch cleanup:
- `prepare_multiple_layers`
- `clear_layers`

For targeted clip diagnosis:
- `audit_clip`
- `get_clip_snapshot`

## Guardrails

- Audit before clearing or batch-disconnecting if the current state is unclear.
- Prefer layer prep before clip triggering when opacity or bypass state may be the real problem.
- Keep composition transport changes separate from clip-routing or output changes unless the failure chain is already obvious.
