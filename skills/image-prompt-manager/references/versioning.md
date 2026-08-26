# Versioning and provenance reference

Read this reference for Prompt updates, version history/diff/restore, source questions, temporary promotion, or derived Prompts.

## Version rules

Every formal Prompt has an immutable v1 snapshot. Changing `prompt_text` or another core execution strategy creates the next integer version and should include a concise `--change-note`. Renaming, notes, typo-level tag cleanup, ratings, preference, favorite, disabled, and trash state do not create a version.

- `version-list P011` lists snapshots with successful Run/feedback totals.
- `version-get P011 1` returns exact text and metadata.
- `version-diff P011 1 3` uses Python `difflib` and reports metadata changes.
- `version-restore P011 1` copies v1 into a new current version; it never overwrites history.

Run rows retain both `prompt_version` and the exact `prompt_snapshot`, so later Prompt changes cannot rewrite historical execution facts.

## Provenance

Allowed source types are `manual`, `chat_capture`, `temporary_generated`, `derived`, `imported`, and `unknown`. Use `source_ref` and `source_note` only when a real reference is available.

Txxx promotion records `temporary_generated` and `origin_temporary_id`. A derived Prompt is added with `--parent-prompt-id` and optional `--parent-prompt-version`; the script validates that version and records `derived`. `provenance Pxxx` displays the source and parent. Migrated V2 data is `unknown`; do not infer a source retroactively.

## Recycle bin

Natural deletion calls `trash Pxxx`. The row, versions, Runs, history, and provenance remain intact but the Prompt is hidden from ordinary browsing, search, candidates, and recommendation. `trash-restore` reverses this.

Permanent operations require explicit confirmation: `trash-purge Pxxx --confirm` or `trash-clean --days 30 --confirm`. They create backups first. Permanent purge removes the Prompt with its versions and Runs; history remains as an audit entry with a null Prompt reference.
