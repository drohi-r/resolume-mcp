---
name: deck-control-and-inspection
description: Use when working with Resolume decks as the primary control surface. Applies to deck snapshots, deck audits, deck parameter control, and deck preparation before playback.
---

# Deck Control And Inspection

Use this skill when the task is centered on Resolume decks rather than composition layers or Advanced Output.

## Workflow

1. Inspect first.
   - `list_decks`
   - `get_deck`
   - `get_deck_snapshot`
   - `audit_deck`

2. If the task is parameter-specific:
   - `get_deck_parameter`
   - `set_deck_parameter`
   - `trigger_deck_action`
   - `reset_deck_parameter`

3. If the task is operational/live:
   - `prepare_deck`

4. Re-check the deck after writes.

## Common patterns

For a quick deck health check:
- `audit_deck`

For direct parameter work:
- `get_deck_parameter`
- `set_deck_parameter`

For live normalization:
- `prepare_deck`

## Guardrails

- Use deck snapshots or deck audits before assuming transport state.
- Keep deck operations separate from output routing changes unless the operator explicitly wants both in one pass.
