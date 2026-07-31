---
name: project-handoff
description: Create or refresh a comprehensive HANDOFF.md so a long-running project can be resumed in a new AI conversation without prior chat access. Use when the user asks to hand off, archive, pause, resume elsewhere, switch conversations or models, summarize project state, preserve project memory, or says the conversation is too long or the AI is forgetting earlier decisions. Also use proactively to briefly recommend a handoff when a substantial project is nearing a context reset, has accumulated many decisions and files, will be paused, or is about to move to another task; do not repeatedly interrupt ordinary short work.
---

# Project Handoff

Create an evidence-based project memory document that lets a new AI continue the work safely.

## Choose the action

- If the user explicitly requests a handoff, create or refresh `HANDOFF.md`.
- If the user only shows a likely need, briefly suggest using `$project-handoff` and explain why in one sentence. Continue the current work unless the user asks to generate it.
- If a current `HANDOFF.md` exists, inspect it and update it instead of discarding useful verified context. Preserve user-authored details unless current evidence contradicts them.
- Do not recommend this skill merely because a conversation has several messages. Recommend it only when continuity risk is material.

## Gather evidence

Use the current conversation plus read-only workspace inspection. Prefer facts that can be verified from:

1. User instructions and explicitly approved decisions.
2. Current files, configuration, tests, generated deliverables, and version-control state.
3. Existing project documentation and prior handoff files.
4. Clearly labelled inference when direct evidence is unavailable.

Inspect only what is relevant. Check the workspace root, important source and output directories, `git status`, recent relevant commits, and available verification results when applicable. Never expose credentials, tokens, personal secrets, or irrelevant private data.

Distinguish clearly among completed, partially completed, planned, blocked, and unverified work. Do not turn proposals into decisions or claim that a command, test, delivery, or deployment succeeded without evidence.

## Write `HANDOFF.md`

Write for an AI that has zero access to previous chats and may resume the project months later. Keep the opening summary readable in under two minutes, followed by operational detail.

Use the following structure, omitting only sections that truly do not apply:

```markdown
# Project Handoff

## Memory snapshot
Project identity, purpose, current stage, most important state, and immediate next action.

## Project overview
Name, goals, scope, definition of success, and relevant user or business context.

## Current workspace
Absolute project path, important files/directories and their purpose, runtime or environment facts, and version-control state.

## Current status
Completed work, partial work, verified deliverables, and verification evidence.

## Approved decisions
Product, design, technical, naming, workflow, and other decisions with rationale when known.

## Constraints and preferences
User preferences, non-negotiable requirements, compatibility needs, and boundaries.

## Technical and design system
Architecture, frameworks, dependencies, APIs, integrations, hosting, typography, colors, layout, components, and media rules as applicable.

## Known issues and risks
Bugs, limitations, missing permissions or inputs, uncertain facts, and likely failure modes.

## Open tasks
Prioritized unfinished work with status and dependencies.

## Next recommended actions
Concrete ordered steps, including how to validate completion.

## Do not do
Specific regressions, rejected approaches, destructive actions, or assumptions the next AI must avoid.

## Key conversation insights
Discoveries and decision rationale that cannot be reconstructed from files alone.

## Resume instructions
Exact starting point, commands if verified, files to read first, and questions that still require the user.
```

Use exact dates, paths, filenames, commands, and versions where they matter. Mark time-sensitive facts with the date verified. Keep commands copyable and avoid speculative commands.

## Validate before delivery

- Confirm `HANDOFF.md` exists in the intended project root and is readable.
- Check that paths and named deliverables exist where claimed.
- Reconcile completed work against open tasks so the same item is not listed inconsistently.
- Search for accidental secrets before finishing.
- State what was created or updated and give the user a clickable file link.
- Provide this copyable continuation prompt: `请先完整阅读 HANDOFF.md，然后从“Next recommended actions”继续；不要假设你能访问以前的聊天记录。`

If evidence is incomplete, still produce a useful handoff but label gaps explicitly rather than inventing details.
