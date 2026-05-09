# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# AiR - AI Code Reviewer

CI/CD 流水线中的自动代码审查工具，使用 `claude-agent-sdk` 对 GitLab push 中的 commit 进行 Code Review，并将结果推送到钉钉 Webhook。

## 开发命令

```bash
# 安装依赖（Python >= 3.13）
uv sync

# 运行（需先配置环境变量，参考 .env.example）
uv run air --commit <SHA>
uv run air --commit <SHA> --debug
uv run air --commit <SHA> --work-dir /path/to/repo

# CI 模式（自动检测 push 范围，需设置 CI_COMMIT_BEFORE_SHA 和 CI_COMMIT_SHA）
uv run air

# Docker 镜像内使用全局入口
air --commit <SHA>
air                          # CI 模式，自动检测

# 类型检查
pyright

# Docker 开发
docker compose run --rm air bash   # 交互式调试

# 快捷测试（Docker 构建 + 审查最新 commit + 推送钉钉）
docker compose build && docker compose run --rm air sh -lc 'air --commit "${COMMIT_SHA:-HEAD}" --debug'
```

## 项目架构

项目只保留 CI Code Review 流程：CLI、目标模型、Agent、结果模型、Prompt 和该流程专属输出放在 `air/flows/code_review/`；公共配置和 prompt 加载器放在 `air/shared/`。

### Code Review 流程

入口为 `air.flows.code_review.cli:main`：

1. `cli.py:main()` 解析命令行参数，构建 `ReviewTarget` 和 `AppConfig`
   - `--commit SHA`：手动指定单个 commit
   - 无参数：CI 模式，从 `CI_COMMIT_BEFORE_SHA..CI_COMMIT_SHA` 自动检测 commit 范围
2. `ReviewTarget` 包含 commit 列表，根据数量选择审查策略：
   - 正常（≤ max_commits）：传 commit 列表给 Claude，Claude 自行 git 逐个查看
   - 降级（> max_commits）：传整体 diff 范围（before_sha..after_sha）
3. 若配置了 Jira MCP，`CodeReviewer` 将 `mcp-atlassian` 以只读方式注入 Claude Agent，并在 prompt 中要求结合 Jira 工单上下文审查
   - 未配置 `JIRA_URL` 和认证信息时，不注入 MCP，也不追加 Jira prompt 指令
4. `CodeReviewer.review(target)` 调用 Claude 审查
5. 审查结果经 `DingtalkChannel.send()` 推送到钉钉；如果 LLM 返回 `should_notify=false`，则跳过推送

### 关键模块

| 模块 | 职责 |
|------|------|
| `air/flows/code_review/cli.py` | `air` 命令入口，解析参数并编排代码审查 |
| `air/flows/code_review/target.py` | `CommitInfo`、`ReviewTarget` 及 Git commit 范围解析 |
| `air/flows/code_review/reviewer.py` | `CodeReviewer`，根据 commit 数量选择审查 prompt 并调用 Claude |
| `air/flows/code_review/result.py` | `ReviewResult`，承载 code review Markdown 正文与是否通知 |
| `air/flows/code_review/dingtalk.py` | `DingtalkChannel`，补充项目、提交信息和 @mention 后发送钉钉 |
| `air/flows/code_review/contacts.py` | 联系人解析和提交人 @mention 匹配 |
| `air/flows/code_review/prompts/` | code review prompt 模板 |
| `air/shared/config.py` | `AppConfig`，统一加载环境变量、Claude CLI 路径和项目名称 |
| `air/shared/prompts.py` | `load_prompt(name)`，从 code review `prompts/` 目录加载模板 |

### 扩展指引

- **新增 code review 推送渠道**：优先放在 `air/flows/code_review/`；只有多个流程共享时再提升到 `air/shared/`。

### 安全权限说明

`CodeReviewer` 使用 `permission_mode="bypassPermissions"` 与 `allowed_tools=["*"]`，原因：
- AiR 仅运行在 CI 容器或本地受控环境，对仓库已经有完整 checkout 权限。
- 如配置 Jira MCP，仅注入只读 Jira 工具；未配置 Jira 环境变量时不会注入。
- Code Review 需要 git/grep/读文件等几乎全集工具，逐项白名单维护成本远大于收益。
- Agent 的工作目录被 `cwd=work_dir` 限定，Jira 访问由显式环境变量控制。
若未来引入写操作或在生产宿主机直接执行，需要重新评估这一权限。

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_BASE_URL` | ✅ | API 地址（自动映射到 `ANTHROPIC_BASE_URL`） |
| `OPENAI_API_KEY` | ✅ | API 密钥（自动映射到 `ANTHROPIC_AUTH_TOKEN`） |
| `OPENAI_MODEL` | ✅ | 模型名称（同时设置所有 Claude 模型别名） |
| `DINGTALK_WEBHOOK_URL` | ✅ | 钉钉机器人 Webhook 地址 |
| `DINGTALK_WEBHOOK_SECRET` | — | 钉钉机器人加签密钥 |
| `AIR_CONTACTS` | — | 联系人配置（JSON），用于钉钉 @mention，根据 regex 匹配提交人，未匹配则 @maintainer |
| `AIR_PROJECT_NAME` | — | 钉钉消息中展示的项目名称；未设置时优先使用 `CI_PROJECT_PATH` / `CI_PROJECT_NAME`，再回退到工作目录名 |
| `AIR_WORK_DIR` | — | 代码仓库路径，CI 中设为 `$CI_PROJECT_DIR`（命令行 `--work-dir` 优先） |
| `AIR_MAX_COMMITS` | — | commit 数量上限，超过时降级为整体 diff 审查，默认 10 |
| `AIR_JIRA_MCP_ENABLED` | — | 是否启用 Jira MCP；未设置时，只有检测到 `JIRA_URL` 和认证信息才自动启用 |
| `AIR_JIRA_MCP_COMMAND` | — | Jira MCP 启动命令，默认 `uv` |
| `AIR_JIRA_MCP_ARGS` | — | Jira MCP 启动参数，默认 `tool run mcp-atlassian` |
| `AIR_JIRA_MCP_READ_ONLY` | — | Jira MCP 是否只读，默认 `true` |
| `AIR_JIRA_MCP_TOOLSETS` | — | mcp-atlassian toolsets，默认 `default` |
| `JIRA_URL` | — | Jira 实例地址；未设置时不会注入 Jira MCP |
| `JIRA_PERSONAL_TOKEN` | — | Jira Server/Data Center Personal Access Token |
| `JIRA_USERNAME` | — | Jira Cloud 用户名；仅在不用 PAT 时配合 `JIRA_API_TOKEN` 使用 |
| `JIRA_API_TOKEN` | — | Jira Cloud API Token；仅在不用 PAT 时配合 `JIRA_USERNAME` 使用 |
| `JIRA_SSL_VERIFY` | — | Jira SSL 校验开关，透传给 mcp-atlassian |
| `JIRA_PROJECTS_FILTER` | — | 限制可访问的 Jira 项目 Key，逗号分隔 |
| `CLAUDE_CLI_PATH` | — | Claude Code CLI 路径，默认使用 bundled 版本（Docker 镜像中固定为 `/usr/local/bin/claude`） |
| `CLAUDE_MAX_TURNS` | — | Claude 最大对话轮数，默认 10 |
| `CI_COMMIT_SHA` | — | GitLab 自动注入，CI 模式必需 |
| `CI_COMMIT_BEFORE_SHA` | — | GitLab 自动注入，用于确定 push 范围 |

> 也可直接使用 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`，`OPENAI_*` 是兼容别名。

## 技术要点

- 整体异步架构（`async/await`），入口通过 `asyncio.run()` 驱动
- Claude 集成使用 `claude_agent_sdk.query()` + Pydantic JSON Schema 结构化输出；结果包含 `body` 和 `should_notify`，由 LLM 判断是否值得推送钉钉，过滤 `LGTM` 等无需人工关注的噪音；若 SDK 返回最终 `ResultMessage` 但缺少 `structured_output`，降级使用 `result` 文本，避免尾部 reader 错误覆盖已收到的结果
- 统一使用 git 命令获取 diff 和仓库上下文；可选 Jira 工单上下文仅通过 MCP 只读获取
- Jira 工单上下文通过 Claude Agent 的 `mcp_servers` 运行时注入；只有 Jira 环境变量完整时启用，默认 `READ_ONLY_MODE=true`
- 构建后端为 `hatchling`，CLI 入口点定义在 `pyproject.toml` 的 `[project.scripts]`
- CI/CD 通过 GitHub Actions（`.github/workflows/release.yml`）：在推送 Git Tag 时触发，构建并推送 `<tag>` 与 `latest` 两个 GHCR 镜像标签，同时自动发布 GitHub Release；Release 说明关联 GHCR Package，不上传镜像 tar 包
- Dependabot 使用 `groups` 将 `uv` 依赖按周聚合到单个 PR（配置见 `.github/dependabot.yml`）
- Docker 镜像基于 `node:24-slim`（因为需要 Claude Code CLI），包含 Java 25 + jdtls 支持；开发与生产共用同一个 `docker/Dockerfile`

## 开发规范

- 所有代码注释和文档使用中文
- 每次变更功能都需要更新 README.md
- 每次变更功能都需要更新 CLAUDE.md
- 每次变更功能都需要更新 .env.example
