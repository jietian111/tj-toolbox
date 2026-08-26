# Recommendation and feedback rules

Read this reference when analyzing an uploaded image, ranking candidates, or interpreting feedback.

## Recommendation pipeline

1. Analyze the current image: subject class, background, lighting, color, composition, sharpness, clutter, identity-preservation need, likely use, and suitable styles.
2. For a generic trigger such as “处理一下这个照片/图片”, do not choose a treatment style before retrieval. Call `status`, then call `candidates` with objective subject/scene/use signals and omit category/subcategory on the first pass. If the result is empty or clearly off-topic, retry once without category/subcategory and with broader subject, scene, and use terms. Do not load the whole library.
3. Judge each candidate's image/scene fit on a 0–100 scale without using popularity to inflate the score. Pass the mapping to `recommend --scores` with the image analysis in `--context`.
4. Use only the returned `recommended` list for normal display. The command has already excluded disabled entries, `avoid_when` conflicts, and scores below the minimum threshold.

## Selection gate

For the user's designated generic triggers “处理一下这个照片/图片” and “处理一下这张照片/图片”, recommendation and execution are separate turns unless the same message already names a concrete `Pxxx`, `Txxx`, numbered option, or specific effect.

- The recommendation turn may call `status`, `candidates`, `recommend`, `get` for a shortlisted item, and `temporary-create` when coverage is insufficient.
- It must show numbered existing and temporary options, then stop and wait for the user's choice.
- It must not call an image executor, `run-start`, `use`, or `temporary-use` merely because a temporary Prompt was created.
- “直接处理”“现在直接按它执行” is not implied by the generic trigger. Those actions require the user's explicit selection.

Treat the following as guidance rather than a rigid formula:

| Signal | Initial weight |
|---|---:|
| Current image and scene fit | 70% |
| Historical choice preference | 12% |
| User rating and feedback | 8% |
| Use frequency | 5% |
| Explicit preference weight | 5% |

Image fit remains dominant. An `avoid_when` match should strongly reduce rank or exclude the Prompt. Disabled entries never participate. Explicit preference may break close ties but cannot rescue a visibly unsuitable Prompt. High use count alone is never sufficient.

V3 may retrieve a small `run-list --prompt Pxxx` summary for candidates that are already image-relevant. Same-scene successful/negative Runs can modestly refine close choices, but never override poor current-image fit. Do not load the entire Run history or introduce an opaque learned score.

## Quality gates and dynamic count

- High match: `>= 80%`.
- Usable match: `>= 65%` and `< 80%`.
- Low match: `< 65%`; hide from normal recommendations unless the user explicitly asks for every candidate.
- Recommend every genuinely suitable candidate and no others: four good matches means four, one means one, zero means zero.
- If there is no high match, `needs_temporary_prompt` is true. Keep usable existing choices, then generate a temporary new solution. If every score is below 50%, put the temporary solution first and do not normally show existing candidates.

Every formal recommendation must include the sequence number, `Pxxx` ID, name, score, and database-returned use/positive/negative counts. Use “历史：尚未使用” when all are zero. Explain separately:

```text
图片匹配：适合当前蓝天、古建筑和秋叶构图。
历史偏好：使用 4 次｜👍 3｜👎 0
```

Keep the session mapping from number to a formal `Pxxx` or temporary `Txxx`. A numeric reply selects immediately; do not ask for confirmation.

## Temporary solution lifecycle

Generate a concise name plus a complete executable Prompt and structured metadata. Call `temporary-create`; never put a draft directly into `prompts`. Present natural options such as:

```text
1 —— 使用现有 P007
2 —— 使用临时新方案
收藏 —— 将已试用的临时方案加入图片库
打开库 —— 浏览完整提示词库
```

On selection, retrieve the full text and invoke an available image tool. Record `use`/`temporary-use` only after successful rendering. A temporary positive result is recorded with `feedback-last`; invite collection, then call `temporary-save`. Promotion transfers temporary use and feedback counts to the new or explicitly merged/replaced formal Prompt.

## Feedback interpretation

- “很好 / 很适合我 / 不错” → `positive`.
- “一般” → `neutral`, a small preference decrease.
- “不好 / 不适合我 / 少推荐” → `negative`, a moderate decrease.
- “以后别推荐这个” → `never`, a strong decrease and recommendation disablement, never deletion.
- An explicit score such as “P007 给5分” → `rate P007 5`.
- “P007 人像优先推荐” → positive `preference` adjustment. Scope-specific preference can be stored in event context even though the first version keeps one aggregate weight.

Use `feedback-last` for unqualified natural feedback. It resolves the latest successful Run, never a recommendation, browse, search, failed Run, or detail view. A changed opinion updates the same Run feedback and repairs Prompt aggregates. If Run history cannot be read, report failure instead of guessing.

## Tool compatibility

Before recording `use`, inspect the tools actually available in the current environment. If an image edit/generation tool can accept the current image and instruction, call it directly and record use only after it returns a successful artifact. Otherwise return the exact selected Prompt, augmented only with image-specific details that do not contradict it, state that rendering was not performed, and do not increment use. Never claim an image was edited without a returned artifact.
