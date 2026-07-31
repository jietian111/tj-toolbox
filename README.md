# 个人工具与 Codex Skills

这个仓库用于集中保存个人 Windows 工具、Codex Skills 和小型实验项目。不同内容按目录分类，便于备份、维护和在其他电脑上重新使用。

## 仓库内容

### Windows 工具：一键整理桌面

一键整理桌面会重新排列 Windows 桌面图标，但不会移动、删除或重命名桌面上的文件。

#### 系统要求

- Windows 10 或 Windows 11
- 使用标准 Windows Explorer 桌面；不支持 macOS、Linux 或替代桌面 Shell
- 直接运行 Release 中的成品不需要安装开发工具
- 从源码构建需要 Windows PowerShell 5.1 或更高版本，以及系统中的 .NET Framework 4.x C# 编译器

程序使用当前用户的 Windows 桌面、注册表和 Explorer 进程，不包含用户名或固定磁盘路径。运行时会将“此电脑”“回收站”和“控制面板”设置为在桌面显示，然后重新排列图标。建议首次使用前记录当前图标布局。

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

### Codex Skill：project-handoff

[`project-handoff`](skills/project-handoff/) 用于为长期项目生成或更新 `HANDOFF.md`。交接文档会记录项目目标、当前状态、已经确认的决定、重要文件、限制、风险、待办事项和下一步操作，让一个无法访问旧聊天记录的新 AI 对话继续工作。

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
使用 project-handoff，帮我整理当前项目并生成 HANDOFF.md。
```

也可以使用 `$project-handoff` 明确触发。该 Skill 还会在项目对话过长、准备暂停、需要切换对话或存在上下文遗失风险时建议生成交接文档。

## 目录结构

```text
tj-toolbox/
├─ assets/                         # 桌面整理工具的图标等资源
├─ skills/
│  └─ project-handoff/
│     ├─ agents/openai.yaml        # Codex 界面元数据
│     └─ SKILL.md                  # Skill 触发条件与工作流程
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
