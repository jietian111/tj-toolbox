# Database and persistence reference

Read this reference before schema-sensitive changes, replace/merge/delete, or JSON import.

## Storage

The default data root is `Path.home() / ".image-prompt-manager"` and contains:

```text
prompts.db
settings.json
backups/
exports/
```

`--data-dir` overrides the root for tests or isolated libraries. SQLite uses foreign keys, WAL mode, busy timeout, explicit transactions, and the standard-library online backup API. Important mutations create a timestamped `.db` backup; rotation keeps the newest `backup_keep` files (default 25).

## Tables

`prompts` stores stable IDs (`P001`, `P002`, …), current content, cached aggregate counters, rating, preference, flags, current version, provenance, optional `deleted_at`, and V3 legacy baselines. JSON-list fields are UTF-8 JSON `TEXT`. Prompt and Run IDs use monotonic counters and are never reused.

`prompt_versions` stores immutable `(prompt_id, version)` snapshots: exact `prompt_text`, effect-relevant metadata JSON, change note, and creation time. New/imported/promoted Prompts get v1. Only a real prompt-text or execution-strategy change creates a new version. Restoring an old version creates another new version.

`runs` is the V3 fact ledger. Each `R000001` row stores the formal Prompt/version or temporary ID, concise image context JSON, exact submitted prompt snapshot, executor/model when known, running/success/failed/cancelled state, optional result reference/path/error, timestamps, and one editable feedback value. Only transition to `success` increments usage.

`history` is append-only for normal operation. It records `prompt_id`, event type/value, optional JSON context, and timestamp. Foreign keys use `ON DELETE SET NULL`, so permanent deletion retains the audit trail. Temporary events have a null `prompt_id` and store `temp_id` in context. Undoing use writes a compensating `use_undo` event and links to the original event; it does not erase history. A real formal `use` also produces a rotating backup; browsing, search, and recommendation display do not.

`temporary_prompts` uses independent `T001` IDs. V3 temporary executions also create Runs. Promotion creates formal v1, marks provenance as `temporary_generated`, and relinks those Runs without losing snapshots or feedback.

## Migration to schema v3

Opening a V2 database creates an online `before-schema-v3` backup, adds provenance/deletion/legacy columns, creates `prompt_versions` and `runs`, and sets `PRAGMA user_version=3`. Every existing Prompt becomes current v1 using its current content. Existing aggregate counts are copied to `legacy_*` baselines and remain unchanged; no historical Runs are invented. V3 expected aggregates are `legacy baseline + successful Runs`.

## Mutation rules

- Add: deterministic duplicate screening narrows candidates by category, tags, and text similarity. A score at or above 0.85 returns `duplicate_found` unless `--duplicate-action add|merge|replace` is explicit.
- Replace: preserve ID, counters, rating, preference and creation time; replace descriptive content, increment version, and append history.
- Merge: target survives. Counters are summed, rating is use-weighted when both exist, strongest preference wins by absolute magnitude, list metadata is unioned, source text is preserved in target notes/history, source history is reassigned, and source is deleted inside one transaction.
- Natural deletion uses `trash` and sets `deleted_at`; trashed rows are excluded from ordinary list/search/candidates/recommendation. `trash-purge` and `trash-clean` require `--confirm` and create backups. Permanent purge cascades versions/Runs and keeps history with a null Prompt reference.
- Disable prevents recommendation candidates. `feedback ... never` also disables recommendation without deleting content.
- `run-complete` is the V3 operation that increments `use_count`; V2-compatible `use` creates and completes a Run. Failed Runs never increment it. `undo-use` cancels the latest successful Run and compensates counters.
- `recommend` never mutates data. Model-supplied image-fit scores are combined only with database-read metadata; normal results exclude disabled, avoid-conflicting, and `<65%` entries.
- `temporary-create` does not allocate a P ID. V2-compatible `temporary-use` creates a successful temporary Run. `temporary-save` atomically allocates/merges/replaces, transfers statistics, creates or updates a version, relinks Runs, writes history, and backs up.

## Import/export

Exports are readable JSON objects with `prompts`, `history`, `prompt_versions`, and `runs`. Import validates before mutation, backs up first, defaults to `--conflict skip`, marks imported Prompts as `imported`, and creates a snapshot. `remap` assigns fresh IDs; `replace` must be explicit. The transaction rolls back on failure.
