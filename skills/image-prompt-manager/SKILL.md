---
name: image-prompt-manager
description: "维护并复用个人图片处理方案。当用户附图并说‘处理一下这个照片/图片’‘处理一下这张照片/图片’，或说‘这张图怎么修’‘帮我挑个适合的效果’‘按我以前喜欢的风格处理’，以及要求收藏、找回、评价、比较、删除修图或生图方案时使用；通用短触发语必须先展示个人库候选或临时方案，用户选定后才执行并记录结果。"
---

# Image Prompt Manager

使用 `scripts/library.py` 完成所有持久化操作；不要直接写 SQL。脚本首次运行会自动在用户 Home 下创建 `~/.image-prompt-manager/`，动态数据不得写入 Skill 目录。命令默认输出人类可读文本；模型调用时优先加全局参数 `--json`。需要隔离测试时加 `--data-dir <目录>`。

## 自然语言触发

用户不需要说 Skill 名称、“Prompt”或“图片提示词库”。以下大白话都应识别为本 Skill 的意图：

- “处理一下这个照片。”“处理一下这个图片。”“处理一下这张照片/图片。”
- “这张照片怎么修会更好？”“帮我挑一个适合这张图的效果。”
- “按我以前喜欢的风格处理一下。”“找一个之前效果不错的方案。”
- “把刚才这个效果记下来。”“以后遇到这种照片就优先用这个。”
- “我上次用的那个效果是什么？”“看看这个方案以前效果怎么样。”
- “刚才这个挺好。”“这个不太行，以后少推荐。”
- “把这个方案改得自然一点。”“看看它有哪些版本。”“这个方案删掉。”

“处理一下这个照片/图片”是本用户指定的明确短触发语：有当前图片时进入个人方案分析与推荐流程；没有图片时请用户上传。这个短语本身不代表“自然精修”或任何具体风格。除非用户同一条消息已经明确点名 `Pxxx`、`Txxx`、编号或具体效果，否则当前轮只能检索并展示方案，严禁直接调用图片工具，严禁调用 `run-start`、`use` 或 `temporary-use`。其他一次性生图或编辑请求若没有使用这些明确短触发语，也没有表达复用个人方案、参考历史效果、收藏或反馈的意图，可直接使用图片工具，不必强行加载个人库。

## 意图与流程

- 收藏、保存或加入图片 Prompt 库：从当前上下文提取完整 Prompt，自动生成中文名称、分类、子类、标签、适用场景、避用场景和优势；先运行 `add`。若返回 `duplicate_found`，结合全文判断是否达到高度重复，再让用户选择新增、合并、替换或取消，绝不静默覆盖。
- 上传图片并要求推荐：先只分析照片中可观察到的主体、背景、光线、色彩、构图、清晰度、杂物、身份保持需求和可能用途；不要在检索前替用户决定“自然精修”“手账”“海报”等处理风格。先运行 `status`，再用这些客观场景信号调用 `candidates` 取得小候选集。对于“处理一下这个照片/图片”这类未指定风格的请求，首轮不要传 `--category` 或 `--subcategory`；如果结果为空或明显偏离，再省略类别并用主体、场景、用途词做一次宽检索。由模型评估候选对当前图片的适配度，再把 `Pxxx → 0..100` 分数传给 `recommend`。脚本负责读取真实统计、过滤 disabled/avoid_when 和低于 65% 的候选。推荐数量服从质量，绝不凑数。
- 每条正式推荐必须显示序号、`Pxxx` ID、名称、匹配度、真实使用/正负反馈和简短原因；将“图片匹配”与“历史偏好”分开说明。所有统计只取自脚本返回；读取失败就说明失败，不猜。
- 若没有 ≥80% 的高匹配，或模型判断现有覆盖不足，生成一条完整可执行的临时 Prompt，并用 `temporary-create` 保存为 `Txxx` 草稿。临时方案未收藏前不进入 `prompts`、不占 `Pxxx`、不迁移统计。按 [推荐规则](references/recommendation-rules.md) 同时给出少量合格现有方案与临时方案；最高低于 50% 时临时方案排第一。创建草稿不等于获准执行，必须把它作为带编号的选项展示给用户。
- 展示候选后立即结束当前轮并等待选择。只有用户回复本轮编号、明确的 `Pxxx`/`Txxx`，或清楚说“直接用某个效果”时，才视为执行授权。正式方案先 `get`，临时方案先 `temporary-get`；随后用 `run-start Pxxx|Txxx` 固化实际 Prompt、版本、简洁图片场景、执行器和可知模型。调用当前可用图片工具后，成功用 `run-complete`，失败用 `run-fail`。只有成功 Run 才增加使用次数；工具不存在时不要创建虚假成功记录。细节见 [Run 历史](references/run-history.md)。
- 自然反馈优先用 `feedback-last`，它绑定最近一次成功 Run；反馈改口会修正同一 Run 和聚合统计，不重复累加。临时方案满意后自然询问是否收藏；`temporary-save Txxx` 会分配正式 ID、创建 v1，并迁移 Run、场景、快照和反馈。若重复检测命中，仍按新增/合并/替换/取消处理。
- 浏览或搜索：先用 `stats`、`list` 或 `search` 返回紧凑目录；只有用户点名 ID 时才用 `get` 展开正文。推荐展示、浏览、搜索都不能调用 `use`。
- 修改 Prompt 正文或核心执行策略时用 `update --change-note` 创建不可变新版本；改名、管理标签、notes、评分、偏好或禁用不创建版本。查看、比较和恢复旧版本时读取 [版本与来源](references/versioning.md)；恢复旧版本总是生成新的当前版本。
- 新 Prompt 要记录轻量来源。Txxx 收藏自动标为 `temporary_generated`；派生 Prompt 用 `--parent-prompt-id` 和可选父版本。来源不确定时不编造。
- `feedback` 保留为 V2 兼容入口；新工作流使用 `run-feedback` 或 `feedback-last`。评分用 `rate`，优先/少推荐用 `preference`；`never` 禁用推荐但不删除。用户说“刚才那个不要算使用次数”时调用 `undo-use`。
- “查看 P007”用 `get`；“刚才那个/刚才使用的”用 `recent-use`；Run 历史用 `run-list`/`run-get`。状态检查显示 Prompt、版本、Run、失败数、回收站和旧汇总说明；`stats-check` 核对旧基线 + 成功 Runs 与缓存统计。
- 用户自然说“删除 P007”时用 `trash P007`，默认移入回收站，不参与浏览、搜索或推荐。恢复用 `trash-restore`；永久清理必须明确确认并使用 `trash-purge --confirm` 或 `trash-clean --confirm`，且脚本自动备份。
- 导入前读取数据库规范；脚本会验证、备份并避免无提示覆盖。导出使用 `export`，不要让用户手工复制 SQLite 文件。

## 命令入口

```text
python scripts/library.py --json init
python scripts/library.py --json add --name "名称" --category "人像" --tags "身份保持,自然精修" --prompt-text "完整 Prompt"
python scripts/library.py --json candidates --category "人像" --tags "身份保持,真实肤质" --query "背景杂乱的日常照片"
python scripts/library.py --json recommend --scores '{"P007":72,"P012":38}' --context "蓝天 古塔 秋叶"
python scripts/library.py --json get P007
python scripts/library.py --json run-start P007 --context '{"scene":"户外古建筑","lighting":"晴天"}' --executor imagegen
python scripts/library.py --json run-complete R000021 --result-ref "returned artifact"
python scripts/library.py --json run-fail R000022 --error "图片工具返回失败"
python scripts/library.py --json feedback-last positive --context "这个效果很好"
python scripts/library.py --json version-list P007
python scripts/library.py --json version-diff P007 1 3
python scripts/library.py --json provenance P007
python scripts/library.py --json trash P007
python scripts/library.py --json temporary-create --name "古建筑旅行自然精修" --category "旅行照片" --prompt-text "完整临时 Prompt"
python scripts/library.py --json temporary-use T001
python scripts/library.py --json temporary-save T001
python scripts/library.py --json search "保持本人长相 稍微小脸"
python scripts/library.py --json status
python scripts/library.py --json export
```

运行 `python scripts/library.py --help` 查看完整参数。涉及字段、事务、重复、合并、删除、导入导出时读取 [数据库规范](references/database-schema.md)；执行与反馈读取 [Run 历史](references/run-history.md)；版本、恢复、来源与派生读取 [版本与来源](references/versioning.md)；图片候选排序读取 [推荐规则](references/recommendation-rules.md)。

空库时自然告知用户：“你的图片提示词库目前还是空的。你可以在得到一个满意的图片处理 Prompt 后直接说：‘把这个提示词收进图片库’。”
