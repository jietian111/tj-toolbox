# Run history reference

Read this reference when executing an image Prompt, recording results, browsing use history, handling feedback, or reconciling counters.

## Execution lifecycle

1. Retrieve the selected Pxxx or Txxx and determine the exact submitted Prompt.
2. Call `run-start` immediately before invoking the available image executor. Supply a short JSON image context, actual executor name, and model only when known. The returned stable ID is `R000001`, `R000002`, and so on.
3. On a returned artifact, call `run-complete`; `result_ref` and `result_path` are optional. This is the only successful transition and increments the relevant usage count once.
4. On tool failure, call `run-fail --error`; it records the failure without incrementing usage. Do not invent a model, path, or result reference.

`prompt_snapshot` is the exact text submitted to the tool and never changes later. A formal Run records the current Prompt version at start. A temporary Run is relinked to formal v1 when the draft is promoted.

## Feedback

`feedback-last` binds natural feedback to the latest successful Run. `run-feedback Rxxxxxx positive|neutral|negative|never` targets an explicit Run. One Run has at most one current feedback value; changing positive to negative subtracts the old aggregate effect before adding the new one. `never` also disables a formal Prompt from recommendation but does not delete it.

## History and diagnostics

- `run-list [--prompt Pxxx] [--status ...]` returns compact history.
- `run-get Rxxxxxx` returns the full immutable execution facts.
- `version-list` derives per-version use and feedback counts from successful Runs.
- `stats-check [Pxxx]` compares cached Prompt aggregates with `legacy_* + successful Runs`.
- `stats-rebuild Pxxx` repairs cached counts from those sources and creates a backup.

V3 migration retains old aggregate counts as `legacy_*`. They are legitimate totals without per-execution detail; never fabricate Runs to explain them.
