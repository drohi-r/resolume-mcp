---
name: strauss-fleet
description: Use when connecting to, discovering, or calling strauss-visuals fleet MCP servers from this repository — regenerating the committed .mcp.json, finding a fleet node's tool functions, checking a node's boundary before calling it, or troubleshooting a sibling MCP connection.
---

# Strauss Fleet Connect

GENERATED from `strauss-mcp/registry/fleet.json` (syntagma 1.1, registry generated 2026-07-17). Do not hand-edit; regenerate from the strauss-mcp checkout:

```bash
python -m strauss_mcp_tools skill --repo-dir ../<this-repo>
```

## Connecting this repo to the fleet

The committed `.mcp.json` at this repo's root is generated from the canonical registry, with portable sibling-relative paths (`cwd: "../<root>"`). It works on any machine whose fleet checkouts share one parent directory; nodes whose sibling checkout is absent simply fail to spawn there (fail-closed by omission). To refresh it:

```bash
# from the strauss-mcp checkout
python -m strauss_mcp_tools preflight --check   # validate registry first
python -m strauss_mcp_tools connect --relative --out ../<this-repo>/.mcp.json
```

If this repo declares its own non-fleet MCP servers in `.mcp.json` (a local server of its own, or external connectors), preserve those entries when refreshing — merge, never clobber.

## Workflow

1. **Find the function.** Look it up in the node table below, or ask the gateway: `fleet_search_tools` (name/description + boundary filter) or `fleet_describe_app` for one node's full surface.
2. **Check its boundary** (table below, or `fleet_get_call_spec` for the exact schema). `read_only` / `local_verify` / `generated_evidence` are safe to call directly. Anything `local_write` or more permissive is plan-only — confirm with a human before calling; never infer consent from an unrelated earlier approval.
3. **Call it through the namespaced `<node>__<tool>` name.** That's what keeps gateway policy, approval, audit, and circuit-breaker enforcement in the loop — never call a fleet-registered sibling's server directly, bypassing the gateway.
4. **Unsure the node is actually reachable?** Don't assume the registry's `enabled` status is still accurate — verify it first (next section).

## Verifying a node before you rely on it

A live node's real `tools/list`/`describe_node` can drift from what `registry/fleet.json` records — a sibling repo ships a new tool, renames one, or changes a boundary, and the registry goes stale until someone re-verifies it against the running server.

```bash
python -m strauss_mcp_tools preflight --live --node NAME --timeout 30
```

Bounded and read-only: `initialize`, paginated `tools/list`, `describe_node` only. Never call a business tool to "test" a node.

Read the resulting `live_reason_code`:

- `ok` — the live server matches the registry; safe to rely on.
- `contract_mismatch` — the live tool list, identity, or boundary disagrees with the registry's `expectedCapabilities`/`boundary`. Fix it by updating the registry entry to match what the **live server** actually reports, never the reverse — the live server is ground truth, the registry is its record. Re-run the same probe to confirm `ok` before trusting the node again.
- `startup_failure` — the node's process didn't start cleanly on this machine (missing dependency, broken entry point). Not necessarily a registry problem; check the node's own install instructions first.

## Enabled fleet nodes and their functions

Only `enabled` nodes are connectable. Never launch or promote `planned`, `blocked_missing_dependencies`, `retired`, or `external` nodes merely because their checkout exists — enabling requires the bounded live preflight evidence recorded in the registry.

| node | repo | boundary | functions |
|---|---|---|---|
| `neurosymbol` | strauss-visuals/neurosymbol | `read_only` | `encode`, `decode`, `describe_unicode_baseline`, `hash_debug_string`, `hash_debug_json`, `audit_security`, `omega_reference`, `describe_node` |
| `strauss-workspace` | strauss-visuals/neurosymbol | `read_only` | `list_projects`, `get_project_git_status`, `list_mcp_readiness`, `describe_node` |
| `neurovizard` | strauss-visuals/neurovizard | `generated_evidence` | `describe_node`, `encode_text`, `compile_text`, `plan_text`, `compile_intent`, `plan_for_driver`, `semantic_trace`, `console_panels`, `run_conformance`, `run_benchmark`, `run_evolution`, `describe_grammar`, `list_corpus` |
| `hermes` | strauss-visuals/HERMES | `live_system` | `acknowledge_hermes_recovery`, `auto_run_hermes_burst`, `auto_step_hermes`, `describe_node`, `disable_hermes_autonomy`, `get_hermes_durable_history`, `get_hermes_history`, `get_hermes_state`, `get_hermes_trends`, `list_hermes_vessels`, `persist_hermes_vessel`, `preview_theurgical_resonance`, `step_hermes` |
| `strauss-communication-hub` | strauss-visuals/communicator | `local_verify` | `list_projects`, `project_status`, `project_context`, `project_verify`, `project_action`, `external_boundary_status`, `plan_external_action`, `audit_log_query`, `describe_node` |
| `co-mmunicator-local-gated` | strauss-visuals/communicator | `local_write` | `verify_sqlite_integrity`, `describe_node`, `query_vector_memory`, `submit_orchestration_payload`, `submit_gem_control_proposal`, `list_approved_codex_handoffs` |
| `uss` | strauss-visuals/uss | `local_write` | `describe_unicode_baseline`, `lookup_glyph`, `parse_expression`, `validate_registry`, `run_precedence_gate`, `run_golden_vector_tests`, `lint_scope`, `run_scope_lint_selftest`, `run_render_gate`, `verify_font_build`, `generate_render_goldens`, `build_font`, `describe_node` |
| `cos-constitution-audit` | strauss-visuals/cos | `read_only` | `run_constitutional_audit`, `list_constitutional_laws`, `describe_node` |
| `pixelwall` | strauss-visuals/pixelwall | `local_write` | `check_environment`, `build_bridge`, `run_test_pattern`, `install_config`, `describe_node` |
| `sase-integrations` | strauss-visuals/sase | `generated_evidence` | `sequence_images`, `resequence_images`, `render_sequence_video`, `list_video_engines`, `generate_keyframe_video`, `repair_seam_media`, `repair_seam_sequence`, `repair_seam_video`, `run_media_pipeline`, `check_integrations`, `describe_node` |
| `aristhorne-c2pa-seal` | strauss-visuals/aristhorne-cast-node-01 | `local_write` | `seal_asset`, `queue_seal_asset`, `process_batch_jobs`, `list_batch_jobs`, `describe_node` |
| `image-sequencer-pro` | strauss-visuals/image-sequencer-pro | `local_write` | `sequence_images`, `resequence_images`, `generate_keyframe_video`, `check_output_quality`, `check_fleet`, `describe_node` |
| `seamfix` | strauss-visuals/seamfix | `local_write` | `repair_image`, `repair_sequence`, `repair_video`, `check_environment`, `check_fleet`, `describe_node` |
| `horizon360` | strauss-visuals/horizon360 | `local_write` | `project_image`, `outpaint_image`, `render_video`, `motion_report`, `analyze_equirect`, `suggest_prompt`, `check_environment`, `check_integrations`, `check_fleet`, `repair_seam_media`, `sequence_frames`, `check_sequence_quality`, `describe_node` |
| `render-fleet` | strauss-visuals/render-fleet-coordinator | `venue_hardware` | `check_coordinator`, `coordinator_health`, `describe_node`, `host_bluetooth_connect`, `host_bluetooth_disconnect`, `host_bluetooth_power`, `host_set_brightness`, `host_set_mute`, `host_set_volume`, `host_snapshot` |
| `strauss-controller` | strauss-visuals/controller | `local_write` | `controller_state`, `describe_node`, `list_intents`, `submit_intent` |
| `codex-local-research-consolidation` | strauss-visuals/codex-local-research-consolidation | `local_write` | `pre_merge_clean`, `topic_scan`, `notebooklm_sync_plan`, `folder_pipeline`, `score_batch_manifest`, `improve_and_score_batch_manifest`, `diagnose`, `deep_research_check`, `investigate_blocker`, `describe_node` |
| `evidencer` | strauss-visuals/evidencer | `local_write` | `describe_node`, `get_evidence_channel_status`, `list_projects`, `list_gates`, `get_gate_status`, `list_evidence_requests`, `get_evidence_request`, `list_evidence_results`, `get_evidence_result`, `list_evidence_observations`, `submit_evidence_request`, `submit_evidence_observation` |
| `wikid` | strauss-visuals/Wikid | `read_only` | `get_wiki_status`, `list_projects`, `get_project_context`, `search_wiki`, `describe_node` |

## Fleet discovery functions (gateway)

The unified gateway exposes a read-only control plane for finding fleet functions before calling them:

- `fleet_list_apps` — list configured internal applications and their redacted availability.
- `fleet_describe_app` — describe one application and its currently callable tools.
- `fleet_search_tools` — search available tool names/descriptions with app and boundary filters.
- `fleet_get_call_spec` — return the exact schema and boundary for one namespaced tool.
- `fleet_list_boundaries` — list the full boundary vocabulary and whether each mode executes, plans, or is refused.
- `fleet_get_dependency_graph` — return recorded sibling-call edges for one app or the whole fleet.
- `gateway_status` — report ready/degraded mount counts without exposing secrets.

These perform discovery only. Invoke application behavior through the namespaced `<node>__<tool>` names so every call continues through gateway policy, approval, audit, and circuit-breaker enforcement.

## Boundary policy (fail closed)

Every tool call is classified by the canonical 9-value boundary vocabulary. Unknown or unlisted boundaries are blocked.

| boundary | mode |
|---|---|
| `read_only` | allowed |
| `local_verify` | allowed |
| `generated_evidence` | allowed |
| `local_write` | plan_only |
| `connector_write` | plan_only |
| `package_release` | plan_only |
| `live_system` | plan_only |
| `venue_hardware` | plan_only |
| `destructive` | blocked |

## Rules

- Cloud/credentialed calls never bypass the cost gates in each repo's CLI/service layer — a fleet call has no interactive cost-confirmation step, which is why MCP generation tools accept local backends only.
- Registry changes go to `strauss-mcp/registry/fleet.json` only, in the same PR that changes a node's tool surface. Never resurrect a per-repo registry.
- Never expose or commit credentials; required env vars appear in generated configs as `<SET_ME:VAR>` placeholders for a human or secrets manager to fill in.
