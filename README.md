# AI Workflow

可安装、可复用、由 Git 管理的个人 AI 工作流技能。每个技能独立放在 `skills/<name>/` 下，包含 `SKILL.md`、必要资源和工具脚本。

## 当前技能

| 技能 | 用途 | 显式调用 |
| --- | --- | --- |
| HIL · Human Interface Language | 面向人类理解与判断组织复杂回答，按需生成有分层、折叠、图表与悬浮目录的 HTML 文档 | Codex：`$human-interface-language` |
| Cognitive Settlement | 将问题、依据、暂时判断、边界、行动与回看条件整理成可确认的认知结算单 | `cognitive-settlement` |

HIL 固定阅读控件，校验结构完整性，保留内容与布局的选择空间。目录默认在右下角展开，悬浮球始终可见，点击同一个球切换展开与收起。结构错误阻止生成；长段落或自定义版式只给提示。

## 安装

需要 Python **3.10 或更高版本**。安装与静态检查只依赖标准库，不需要 Node、构建服务或网络。HTML 中的 Mermaid 图表按需从固定版本 CDN 加载。

在克隆或下载仓库后，进入仓库根目录运行：

```sh
# Codex：$CODEX_HOME/skills；未设置时为 ~/.codex/skills
python3 scripts/install.py --agent codex

# Claude Code：~/.claude/skills
python3 scripts/install.py --agent claude

# 支持 SKILL.md 的其他工具：指定其实际技能父目录
python3 scripts/install.py --dest /path/to/agent/skills
```

脚本默认安装 `human-interface-language`。将来增加其他技能后，可以把技能名作为位置参数传入。脚本复制整个技能目录，并不将仓库与已安装副本绑定。

- `--dry-run` 只检查并显示计划，不创建文件。
- 已有相同内容时跳过；已有不同内容时默认拒绝覆盖。
- 审阅差异后，用 `--replace` 更新。旧版备份到目标 skills 父目录旁的 `ai-workflow-backups/`，例如 `~/.codex/ai-workflow-backups/`，避免被当成另一个技能加载。
- 安装后在宿主中重新加载技能或开启新的对话；具体发现与自动调用行为由宿主决定。

```sh
python3 scripts/install.py --agent codex --dry-run
python3 scripts/install.py --agent codex --replace
```

### Codex 从 GitHub 安装

仓库发布到 GitHub 后，可让 Codex 的 `$skill-installer` 从实际仓库的 `skills/human-interface-language` 路径安装。例如向 Codex 提出：

> 使用 skill-installer，从我的 ai-workflow GitHub 仓库安装 skills/human-interface-language。

需要提供真实仓库 URL。此本地项目没有预设远程地址，也不会自动创建 GitHub 仓库、提交或推送。

### 兼容范围

`SKILL.md` 和相对资源路径是技能主体，`agents/openai.yaml` 是 Codex 元数据。Claude Code 及其他工具是否支持自动发现、调用语法、预览和 Python 执行，以各自宿主为准；本项目提供目录安装能力，不承诺所有工具体验相同。未配置专属插件 manifest、MCP 或市场注册；使用标准技能目录安装。

## 使用 HIL

Codex 中可以直接说：

> 请使用 $human-interface-language 比较这些方案，保留关键依据、适用条件和不确定性，并在有助于阅读时生成 HTML。

短答保持在对话中；复杂内容才考虑 HTML。生成后交付简短结论与文件入口。新事实或方案调整更新原文档，不为每次追问制造新版本。

生成器也可以独立使用：

```sh
python3 skills/human-interface-language/scripts/hil.py render \
  --content examples/hil-body.html \
  --title 'HIL · 阅读示例' \
  --summary '固定阅读控件，保留灵活的内容表达。' \
  --output outputs/hil-demo.html

python3 skills/human-interface-language/scripts/hil.py check outputs/hil-demo.html
```

直接在浏览器打开生成的 HTML。更多参数与检查边界见 [生成与检查说明](skills/human-interface-language/references/generation.md)。示例正文用于演示，不包含真实项目数据。

## 开发与验证

```sh
python3 scripts/check.py
```

该入口运行 HIL 行为测试、安装器测试、技能元数据与相对资源检查，并在临时目录生成示例。GitHub Actions 运行相同入口。自动检查不证明内容事实正确，也不替代布局或交互变更后的浏览器验证。

```text
skills/human-interface-language/   技能源代码与资源
scripts/install.py                复制安装、预演与带备份的更新
scripts/check.py                  项目验证入口
examples/hil-body.html             可复用示例正文
tests/                           项目级测试
```

后续以本仓库的技能目录为修改来源：修改 → 检查 → review → commit（由用户明确指示）→ 重新安装。直接修改已安装副本不会回写仓库。

仓库尚未声明开源许可证；如需公开分发，请先确定许可方式。
