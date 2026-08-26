---
name: project-handoff
description: Save, inspect, or resume durable project context through HANDOFF.md so work can continue in a new AI conversation without prior chat access. Use for handoffs, pauses, context or model switches, status recovery, and plain-language requests such as "存个档", "记一下进度", "保存或压缩上下文", "我要开新对话继续", "接着上次继续", "先读交接文件", or "看看上次做到哪里了". Briefly recommend it when a substantial project faces real continuity risk, but do not interrupt ordinary short work.
---

# Project Handoff

Maintain a compact, evidence-based continuation point for an AI with no access to earlier chats.

## Select the mode

- **Save**: Create or refresh `HANDOFF.md` when the user asks to save, archive, summarize, pause, switch conversations or models, or preserve context.
- **Resume**: Read and verify `HANDOFF.md` when the user asks to continue, take over, read the handoff, or resume previous work. Report material drift before changing files, then continue if the requested next action is clear and authorized.
- **Status**: Read and compare the handoff with the current project when the user asks where work stopped or what remains. Report only; do not implement changes unless asked.
- **Suggest**: If continuity risk is material but the user has not requested a handoff, recommend it once in one sentence and continue the current work.

Treat natural Chinese requests as direct mode selections without requiring the skill name. Do not trigger merely because a conversation has several messages.

## Resolve the project and evidence

Resolve the intended project root from the user's named path, the current Git root, or the current workspace. If more than one plausible project would materially change the result, ask before writing.

Prefer facts in this order:

1. Explicit user instructions and approved decisions.
2. Current files, configuration, deliverables, tests, and version-control state.
3. Existing project documentation and the prior handoff.
4. Clearly labelled inference when direct evidence is unavailable.

Inspect only relevant material. Check the project root, important files, `git status`, current branch and commit, recent relevant commits, and available verification results when applicable. Never include credentials, secret values, private transcripts, caches, or irrelevant personal data. Record environment-variable names only; redact their values.

Distinguish completed, in progress, planned, blocked, failed, and unverified work. Never turn proposals into approved decisions or claim a command, test, delivery, or deployment succeeded without evidence.

## Save a handoff

If `HANDOFF.md` exists, preserve still-valid user-authored facts and reconcile stale status instead of blindly replacing it. Do not auto-commit or push the handoff.

Write the following structure, omitting sections that truly do not apply:

```markdown
# Project Handoff

## Memory snapshot
Project identity, current objective and stage, most important state, and the first next action. Keep this readable in under two minutes.

## Handoff metadata
- Generated at: exact local date, time, and UTC offset
- Intended receiver: next session, named agent, or either
- Project root: portable project identity or repository root
- Current machine path: absolute path, explicitly marked machine-specific
- Git state: remote, branch, commit, and clean/dirty/not applicable

## Project overview
Goals, scope, definition of success, and essential user or business context.

## Current status
Completed, in-progress, blocked, and unverified work; verified deliverables and evidence.

## Approved decisions and constraints
Decisions with rationale when known; user preferences, compatibility needs, and must/must-not boundaries.

## Key files and durable references
Project-relative paths first, why each matters, and links to existing README, specs, plans, architecture, or design documents.

## Known issues, risks, and failed attempts
Bugs, limitations, uncertainties, and only those failed approaches whose result or retry condition will prevent repeated work.

## Open tasks
Prioritized unfinished work with dependencies and observable acceptance criteria.

## Next recommended actions
Concrete ordered steps, real commands when verified, and how to validate completion.

## Resume instructions
What to read first, the exact starting point, machine or transport requirements, and unresolved questions that need the user.
```

Keep the handoff compact. Link to durable project documents instead of repeating their contents. Include only conversation insights that cannot be reconstructed from files. Front-load the next action, use project-relative paths where possible, label absolute paths as machine-specific, and avoid exhaustive directory trees or work logs.

Use exact dates, filenames, commands, versions, and verification results where they matter. Mark time-sensitive facts with the verification date. Never invent commands merely to make the handoff look complete.

### Optional history

Update `HANDOFF.md` in place by default. Archive the previous file only when the user requests history or the prior snapshot has clear audit value. In that case, copy it to `.handoff/archive/HANDOFF-YYYYMMDD-HHMM.md` before updating. Do not use symlinks, prune archives, or create the archive structure for ordinary saves.

## Resume or inspect a handoff

Before trusting the file:

1. Read the handoff and the durable files it directly references.
2. Compare its timestamp, project identity, machine path, branch, commit, working-tree state, and named deliverables with the current project.
3. Classify it as **current**, **partially stale**, or **unreliable**, and state the evidence for any material drift.
4. Reconcile stale facts in the handoff only when the user asked to save or refresh it. In Status mode, do not write.
5. On Resume, give a short grounding summary and begin from the recorded next action only when it remains valid and is within the user's request. Otherwise stop at the concrete discrepancy or required choice.

Do not treat `HANDOFF.md` as authority when current project evidence contradicts it. Do not overwrite `AGENTS.md`, `CLAUDE.md`, README files, specifications, or task trackers; they remain durable sources of truth.

## Validate delivery

For Save:

- Confirm `HANDOFF.md` exists at the intended project root and is readable.
- Verify claimed paths and deliverables, reconcile completed work against open tasks, and scan the file for accidental secrets.
- Report the path, Git state captured, and any unresolved evidence gaps.
- Provide: `请先完整阅读 HANDOFF.md，核对它与当前项目是否一致，然后从“Next recommended actions”继续；不要假设你能访问以前的聊天记录。`

For Resume or Status:

- Report the handoff path, freshness classification, material drift, current objective, and next valid action.
- If evidence is incomplete, label the gap instead of guessing.
