# Live Validation Notes

## Context

These notes come from validating the repo against the local Resolume instance running on this laptop on `2026-04-02`.

Scope note:

- This validation was performed on a macOS machine.
- Your intended production targets are Windows media servers, so filesystem-backed findings in this document should be treated as macOS-specific unless revalidated on Windows.

## Confirmed

- REST webserver reachable on `http://127.0.0.1:8080`
- WebSocket endpoint reachable on `ws://127.0.0.1:8080/api/v1`
- Composition REST endpoint works:
  - `/api/v1/composition`
- Layer REST endpoint works:
  - `/api/v1/composition/layers/1`
- Column REST endpoint works:
  - `/api/v1/composition/columns/1`
- Deck REST endpoint works:
  - `/api/v1/composition/decks/1`
- Deck list is embedded inside `/api/v1/composition`
- Layer groups are exposed as `layergroups` in the REST API, not `groups`
- Selected-object read endpoints confirmed on this machine:
  - `/api/v1/composition/layers/selected`
  - `/api/v1/composition/clips/selected`
- The following binary-visible paths returned `404` on this machine during safe live reads:
  - `/api/v1/composition/layergroups/selected`
  - `/api/v1/composition/layers/1/clips/active`
- Advanced Output candidate HTTP paths probed on this machine returned `404`, including:
  - `/api/v1/advancedoutput`
  - `/api/v1/advancedoutput/screens`
  - `/api/v1/output`
  - `/api/v1/screens`

## Important websocket behavior

- On connect, Resolume sends an initial bootstrap stream before action-specific responses.
- The client now drains that bootstrap before waiting for the action response.
- Parameter websocket actions are valid against `/parameter/by-id/{id}`.
- Using websocket `get` or `subscribe` directly on paths like `/composition/tempocontroller/tempo` returned:
  - `{"path":"...","error":"Invalid parameter path"}`
- The named composition, layer, clip, and deck parameter helpers now resolve IDs from the REST payload first, then use `/parameter/by-id/{id}` for websocket actions.

## Important action-path behavior

- Trigger-style websocket actions use REST-like action endpoints.
- Example patterns observed in Resolume's own bundled example app:
  - `/composition/columns/by-id/{id}/connect`
  - `/composition/columns/by-id/{id}/select`
  - `/composition/decks/by-id/{id}/select`
  - `/composition/layers/by-id/{id}/select`
  - `/composition/clips/by-id/{id}/connect`

## Advanced Output status on this local build

- Advanced Output endpoints were not present in the exposed REST spec on the validated local build.
- The current repo's Advanced Output wrappers therefore remain experimental until verified against a build that exposes those surfaces, or against a different control method.
- Advanced Output is persisted locally on this machine as XML:
  - `/Users/Drohi/Documents/Resolume Arena/Preferences/AdvancedOutput.xml`
  - `/Users/Drohi/Documents/Resolume Arena/Preferences/slices.xml`
- Those exact filesystem paths are macOS-local findings, not assumed Windows defaults.
- The repo now has read-only XML tools for:
  - summary
  - screen inspection
  - slice inspection
  - backup
  - diff

## Practical implication for the repo

- REST is the safest current source of truth for composition, layers, columns, decks, clips, and layer groups.
- The validated deck schema currently exposes `selected` and `scrollx`, but not deck transport fields.
- WebSocket is confirmed for:
  - bootstrap state stream
  - parameter-by-id actions
  - trigger-style action endpoints
- Any named websocket helper that assumes arbitrary parameter paths should be treated carefully until it is converted to parameter-id resolution or verified live.
