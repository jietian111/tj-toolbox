# TJ Toolbox｜Windows 工具与 Codex Skills

这个仓库集中提供可以直接安装或运行的 Windows 小工具与 Codex Skills，主要解决 Obsidian 知识整理、长期项目交接和桌面图标整理等实际需求。

## 快速入口

| 工具 | 用途 | 最短用法 |
| --- | --- | --- |
| [`organize-obsidian-inbox`](skills/organize-obsidian-inbox/) | 把当前对话、附件、网页和收件箱资料整理成 Obsidian 笔记 | 附上资料或讨论完成后说 `存入 Obsidian` |
| [`image-prompt-manager`](skills/image-prompt-manager/) | 维护个人图片处理方案库，按当前图片推荐、执行并记录版本、结果和反馈 | 附图后说 `处理一下这个图片` |
| [`project-handoff`](skills/project-handoff/) | 生成或更新 `HANDOFF.md`，让新任务在没有旧聊天记录时继续长期项目 | `使用 project-handoff，生成 HANDOFF.md` |
| [`codex-proxy-launcher`](skills/codex-proxy-launcher/) | 为 Windows 生成强制使用本地 HTTP 代理、可适配 App 更新的 Codex 桌面快捷方式 | `使用 codex-proxy-launcher，帮我生成代理启动器` |
| [一键整理桌面](#windows-工具一键整理桌面) | 按类型重新排列 Windows 桌面图标，不移动或删除文件 | 从 [Releases](https://github.com/jietian111/tj-toolbox/releases) 下载运行 |

### 推荐：把资料自动存入 Obsidian

安装 [`organize-obsidian-inbox`](skills/organize-obsidian-inbox/) 并完成一次默认知识库设置后，可以在同一台电脑的任意 Codex 任务中使用：

```text
存入 Obsidian
```

Skill 会优先读取同一条消息或紧邻的唯一附件/网址。资料完整、分类明确且没有冲突时，它会自动创建结构化笔记、更新索引和处理记录，并在验证后归档。如果独立发送该口令且没有资料目标，Skill 会先预览当前任务中可访问的对话摘要，确认后再保存知识笔记和对话快照。原始外部附件不会被修改。

## 仓库内容

### Windows 工具：一键整理桌面

一键整理桌面会重新排列 Windows 桌面图标，但不会移动、删除或重命名桌面上的文件。

当前公开版本为 V2.1.1。双击程序会打开轻量主窗口，由用户选择开始整理、预览或撤销，不会在启动后立即移动图标。

#### 主要功能

- 按“从上到下、再从左到右”的固定规则稳定排列，第二次运行不会重复改变坐标
- 保留屏幕右侧三分之一区域，并对其他显示器上的普通图标采取保守保护
- 整理前自动保存布局，可使用稳定的 Windows Shell 身份撤销
- 预览分类统计但不移动图标；高级选项可导出不含完整路径的诊断信息
- 支持 Per-monitor DPI、Windows 实际图标网格间距和中文/英文区域排序
- V2.1.1 使用内容驱动的中文排版与动态窗口高度，Ready、Preview、Success、Info 和 Error 长文字均可完整显示

布局备份和诊断文件保存在 `%LOCALAPPDATA%\DesktopOrganizer\`。

#### 系统要求

- Windows 10 或 Windows 11
- 使用标准 Windows Explorer 桌面；不支持 macOS、Linux 或替代桌面 Shell
- 直接运行 Release 中的成品不需要安装开发工具
- 从源码构建需要 Windows PowerShell 5.1 或更高版本，以及系统中的 .NET Framework 4.x C# 编译器

程序使用当前用户的 Windows 桌面、注册表和 Explorer 进程，不包含用户名或固定磁盘路径。点击“开始整理”时会将“此电脑”“回收站”和“控制面板”设置为在桌面显示，然后重新排列图标；点击“预览整理”不会移动任何图标。

#### 下载并运行

从仓库的 [Releases](https://github.com/jietian111/tj-toolbox/releases) 页面下载 `DesktopOrganizer.exe`，然后双击运行。Windows 首次运行下载的程序时可能显示安全提醒；请核对发布来源和 Release 中提供的 SHA-256 后再运行。

#### 排列规则

图标按照“从上到下、再从左到右”的顺序排列：

1. 此电脑、回收站、控制面板
2. 其他应用程序
3. 实体文件夹
4. 指向其他位置的文件夹快捷方式
5. 压缩文件（`.zip`、`.rar`、`.7z` 等）
6. 文字文档、PDF、演示文稿、表格、图片、视频、音频、设计文件及其他文件

每个分组内部按照中文拼音或英文首字母排序。放在屏幕右侧三分之一区域的图标会保留原位置，不参与整理；此电脑、回收站和控制面板除外。左侧可整理区域必须至少留有一个空位，程序才能可靠交换图标位置。

#### 从源码构建

源码位于 [`OrganizeDesktop.cs`](OrganizeDesktop.cs)。在仓库根目录打开 PowerShell，然后运行：

```powershell
.\build.ps1
```

脚本会自动选择当前系统可用的 64 位或 32 位 .NET Framework 编译器，并将成品生成到：

```text
dist\DesktopOrganizer.exe
```

也可以指定输出目录：

```powershell
.\build.ps1 -OutputDirectory 'D:\BuildOutput'
```

### Codex Skill：image-prompt-manager

[`image-prompt-manager`](skills/image-prompt-manager/) 使用本地 SQLite 保存个人图片处理 Prompt、不可变版本、实际执行 Run、结果引用和反馈。附图后说“处理一下这个图片”，Skill 会先分析当前图片并展示带编号的个人库候选或临时方案；只有用户选定后才调用图片工具和记录使用，浏览与推荐本身不会增加使用次数。

安装后的个人库默认是空的，这是正常状态：仓库不会把维护者或其他用户的 Prompt、偏好与使用记录自动写入你的数据库。这样升级 Skill 时不会覆盖个人数据，新用户的推荐统计也只来自自己的真实选择。完整的空库说明、首次使用流程和收藏方式见 [`image-prompt-manager/README.md`](skills/image-prompt-manager/README.md)。

#### 安装

把下面整段内容发送给 Codex，即可使用官方 `skill-installer` 安装并验证：

```text
请使用 skill-installer，把下面 GitHub 目录中的 image-prompt-manager Skill 安装到我的 Codex 默认 Skills 目录，并在安装后验证 SKILL.md、agents/openai.yaml、references、scripts 和 tests。如果目标目录已经存在，请先检查并告诉我，不要直接覆盖。请直接执行安装，不要只提供操作步骤：

https://github.com/jietian111/tj-toolbox/tree/main/skills/image-prompt-manager
```

安装完成后打开一个新的 Codex 任务，附上一张图片并发送：

```text
处理一下这个图片
```

首次调用时，如果个人库仍为空，Codex 会说明当前没有正式方案，并提醒你怎样收集第一条 Prompt。最直接的方法是粘贴完整内容：

```text
把下面这段提示词收进图片库：
<粘贴完整提示词>
```

也可以上传包含 Prompt 的清晰截图并说：

```text
识别这张截图里的图片处理提示词，先核对完整文字，再收进图片库。
```

或者在一次图片处理效果满意后说：

```text
把刚才这个效果收进图片库。
```

空库时附图说“处理一下这个图片”，Codex 可以先生成一个临时 `Txxx` 方案作为编号选项，但仍会停下来等你选择，不会因为库为空就擅自执行。

Skill 的源码和可安装内容位于仓库；变化中的个人数据库保存在用户主目录的 `.image-prompt-manager` 中，不会写入 Skill 目录或提交到 GitHub。所有确定性读写均通过 `scripts/library.py` 完成，不需要云端数据库。

### Codex Skill：codex-proxy-launcher

[`codex-proxy-launcher`](skills/codex-proxy-launcher/) 用于解决 Windows Codex/ChatGPT App 因网络环境反复显示 `reconnecting` 的问题。Skill 会先询问本地 HTTP 代理端口，再在桌面创建完整的代理启动器和 `Codex.lnk` 快捷方式。

#### 安装

把下面整段内容发送给 Codex，即可使用官方 `skill-installer` 安装并验证：

```text
请使用 skill-installer，把下面 GitHub 目录中的 codex-proxy-launcher Skill 安装到我的 Codex 默认 Skills 目录，并在安装后验证 SKILL.md、agents/openai.yaml、assets 和 scripts 目录。如果目标目录已经存在，请先检查并告诉我，不要直接覆盖。请直接执行安装，不要只提供操作步骤：

https://github.com/jietian111/tj-toolbox/tree/main/skills/codex-proxy-launcher
```

安装完成后打开一个新的 Codex 对话，然后发送：

```text
使用 codex-proxy-launcher，帮我在桌面生成 Codex 代理启动器。
```

Codex 会询问本地 HTTP 代理端口，只需回复数字，例如 `7897`。默认代理地址为 `http://127.0.0.1:<端口>`。

#### 生成内容与功能

Skill 默认生成：

```text
桌面\Codex Proxy Launcher\CodexProxyLauncher.cmd
桌面\Codex Proxy Launcher\Resolve-CodexApp.ps1
桌面\Codex.lnk
```

启动器会设置 `HTTP_PROXY`、`HTTPS_PROXY` 和 `ALL_PROXY`，并向 Codex/ChatGPT App 传入 Chromium 的 `--proxy-server` 参数。它还会从 AppX 包及 `AppxManifest.xml` 动态识别当前入口，兼容 `ChatGPT.exe` 和 `Codex.exe`；App 更新后再次启动时，会重新解析程序路径并刷新快捷方式图标。

启动器同时保留 Codex 子进程常用的 Git、Node.js、npm 和 ripgrep 路径修复，并提供 `--check` 和 `--env-check` 两个检查入口。前者显示代理端口状态、当前 App 路径、代理地址和快捷方式位置；后者额外显示这些命令行工具的实际路径及版本。

代理端口关闭时仍可生成启动器，但使用前需要先启动本地代理软件。本 Skill 当前面向 Windows 10/11，不负责安装或配置代理软件，也不会修改系统级代理。修复时只覆盖它自己生成的启动器文件和 `Codex.lnk`，不会删除其他桌面内容。

### Codex Skill：project-handoff

[`project-handoff`](skills/project-handoff/) 用于保存、核验和恢复长期项目的 `HANDOFF.md`。它会记录当前状态、已确认决定、重要文件、风险、验证结果和下一步操作；新对话接手时还会比较交接时间、Git 状态和实际文件，先判断交接是否过期，再继续工作。

#### 安装到另一台电脑

推荐直接把下面整段内容发送给 Codex，让它自动安装并验证：

```text
请使用 skill-installer，把下面 GitHub 目录中的 project-handoff Skill 安装到我的 Codex 默认 Skills 目录，并在安装后验证 SKILL.md 和 agents/openai.yaml。如果目标目录已经存在，请先检查并告诉我，不要直接覆盖。请直接执行安装，不要只提供操作步骤：

https://github.com/jietian111/tj-toolbox/tree/main/skills/project-handoff
```

安装完成后，在下一轮对话中即可使用。该仓库是公开仓库，不需要登录 GitHub 账号。

如果希望手动安装，请先安装 [Git](https://git-scm.com/)，然后在 PowerShell 中运行：

```powershell
git clone https://github.com/jietian111/tj-toolbox.git

$skillSource = Join-Path (Get-Location) 'tj-toolbox\skills\project-handoff'
$skillDestination = Join-Path $env:USERPROFILE '.codex\skills\project-handoff'
New-Item -ItemType Directory -Force -Path $skillDestination | Out-Null
Copy-Item -Path (Join-Path $skillSource '*') -Destination $skillDestination -Recurse -Force
```

手动安装后打开一个新的 Codex 对话，使 Skill 列表重新加载。

#### 使用方式

```text
存个档。
接着上次继续，先读 HANDOFF.md 并核对当前项目。
看看上次做到哪里了，只汇报状态，先不要修改。
```

也可以使用 `$project-handoff` 明确触发。Skill 会根据表达自动选择 Save、Resume 或 Status 模式；在项目对话过长、准备暂停、需要切换对话或存在上下文遗失风险时，也会简短建议生成交接文档。

### Codex Skill：organize-obsidian-inbox

[`organize-obsidian-inbox`](skills/organize-obsidian-inbox/) 用于把当前任务对话、网页、聊天附件以及 Obsidian 收件箱中的 Markdown、TXT、PDF、DOCX、PPT/PPTX 和图片整理成结构化笔记。资料完整、分类明确且无冲突时会自动生成、更新索引和处理记录，并在验证后归档；独立口令触发的对话整理始终先预览，确认后才写入。

#### 安装

推荐把下面整段内容发送给 Codex，让它使用官方 `skill-installer` 安装并验证：

```text
请使用 skill-installer，把下面 GitHub 目录中的 organize-obsidian-inbox Skill 安装到我的 Codex 默认 Skills 目录，并在安装后验证 SKILL.md、agents/openai.yaml 和 scripts 目录。如果目标目录已经存在，请先检查并告诉我，不要直接覆盖。请直接执行安装，不要只提供操作步骤：

https://github.com/jietian111/tj-toolbox/tree/main/skills/organize-obsidian-inbox
```

安装完成后，请打开一个新的 Codex 对话，使 Skill 列表重新加载。

#### 首次设置

Codex Skill 目前没有“安装完成后立即自动弹窗”的安装钩子。因此，本 Skill 会在首次调用时显示简短用法，并要求设置默认 Obsidian Vault。

首次调用：

```text
使用 $organize-obsidian-inbox，开始设置默认知识库
```

按照提示提供一个已经存在、且包含 `.obsidian` 的知识库绝对路径。Skill 会把默认路径保存到用户自己的 Codex 配置目录，不会把个人路径写回本仓库。首次设置还会以“只创建缺失项、不覆盖已有内容”的方式准备收件箱、分类、归档、模板和处理记录。

当前版本以 Windows Codex 为主要支持环境；在 macOS 或 Linux 使用时，需要系统能够调用 PowerShell 7。

#### 使用方式

设置完成后，可以在同一台电脑的任意 Codex 任务中附上文件或粘贴网址，然后只说：

```text
存入 Obsidian
```

如果 Codex 客户端把一次发送中的附件和“存入 Obsidian”显示成两个相邻气泡，Skill 仍会匹配紧邻的唯一附件或网址。若有多个候选、来源已处理、被其他请求隔开或指代不清，Skill 会先询问，不会向前广泛猜测或扫描整个收件箱。旧口令“整理了”仍可作为兼容别名，但不再是推荐入口。

如果当前消息和紧邻消息都没有附件、网址或指定文件，独立发送“存入 Obsidian”会进入当前任务对话模式。Skill 只使用此刻实际可访问的用户与 Codex 消息，先展示标题、分类、标签、摘要、结构、正式笔记路径和对话快照路径；用户回复“确认整理并归档”后才写入。快照保存在 `98-原始资料/<YYYY-MM>/对话`。隐藏指令、内部推理和工具日志不会保存；早期消息已经压缩或不可访问时会明确提示不完整。

无空格的“存入obsidian”以及仅有英文字母大小写差异的形式与“存入 Obsidian”等价。

其他常用口令：

```text
先预览，存入 Obsidian
把当前对话存入 Obsidian
确认整理并归档
整理收件箱
查看默认知识库
更换默认知识库路径
```

默认配置文件位于用户配置目录：Windows 为 `%USERPROFILE%\.codex\organize-obsidian-inbox\settings.json`，其他系统使用用户主目录下的同等位置。配置文件不包含账号、令牌或其他凭据。

## 目录结构

```text
tj-toolbox/
├─ assets/                         # 桌面整理工具的图标等资源
├─ skills/
│  ├─ codex-proxy-launcher/
│  │  ├─ agents/openai.yaml        # Codex 界面元数据
│  │  ├─ assets/                   # CMD 模板和动态 App 入口解析器
│  │  ├─ scripts/                  # 桌面启动器安装脚本
│  │  └─ SKILL.md                  # 代理端口收集、生成与验收流程
│  ├─ image-prompt-manager/
│  │  ├─ README.md                 # 空库说明、首次使用与 Prompt 收集指南
│  │  ├─ agents/openai.yaml        # Codex 界面元数据
│  │  ├─ references/               # 推荐、版本、Run 与数据库规则
│  │  ├─ scripts/                  # SQLite Prompt 库 CLI
│  │  ├─ tests/                    # V2 回归与 V3 测试
│  │  └─ SKILL.md                  # 自然语言触发与先推荐后执行流程
│  ├─ project-handoff/
│  │  ├─ agents/openai.yaml        # Codex 界面元数据
│  │  └─ SKILL.md                  # Skill 触发条件与工作流程
│  └─ organize-obsidian-inbox/
│     ├─ agents/openai.yaml         # 首次设置入口和界面元数据
│     ├─ scripts/                   # 配置、扫描和 PPTX 提取脚本
│     └─ SKILL.md                   # 默认 Vault 与自动整理工作流
├─ OrganizeDesktop.cs              # 一键整理桌面源码
├─ build.ps1                       # 自动查找编译器并构建 EXE
├─ .gitignore
├─ LICENSE                         # MIT 开源许可证
└─ README.md
```

以后新增内容时，建议继续按用途分类：

- `skills/`：Codex Skills
- `projects/`：相对独立的小工具或实验项目
- `documents/`：需要版本管理的说明文档
- 各项目自己的 `assets/`：图标、图片和模板等资源

## 安全提示

不要把密码、API Key、访问令牌、私钥、个人隐私文件或其他敏感信息提交到仓库。无论仓库公开还是私有，都应使用环境变量或本机配置文件保存凭据，并通过 `.gitignore` 排除这些文件。

## 开源许可证

本仓库使用 [MIT License](LICENSE)。你可以使用、复制、修改和分发其中的代码，但需要保留原始版权及许可声明。软件按现状提供，不附带任何担保。
