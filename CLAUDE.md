# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# AiR - AI Code Reviewer

CI/CD 流水线中的自动代码审查工具，使用 `claude-agent-sdk` 对 GitLab commit 进行 Code Review，并将结果推送到钉钉 Webhook。

## 开发命令

```bash
# 安装依赖（Python >= 3.13）
uv sync
uv sync --group dev          # 包含 pyinstaller 等开发依赖

# 运行（需先配置环境变量，参考 .env.example）
uv run python -m air --commit <SHA>
uv run python -m air --commit <SHA> --debug

# 或使用安装后的命令
air --commit <SHA>
air --mr <IID>   # 预留，暂未实现

# 类型检查
pyright

# 编译二进制
uv run pyinstaller air.spec --distpath dist/

# Docker 开发
docker compose run --rm air bash   # 交互式调试
```

## 项目架构

整体流程由 `air/air.py:main()` 编排：

1. 根据 `AppConfig.is_ci`（由 `CI_JOB_TOKEN` 是否存在判断）选择运行模式
2. **CI 模式**：`CodeReviewer.review_in_ci()` — 让 Claude 在 git 仓库中直接用 git 命令获取 diff
3. **本地模式**：`CodeReviewer.review_in_local()` — 通过 `GitLabSource` 调 GitLab API 拉取 diff，再交给 Claude 审查
4. 审查结果经 `DingtalkChannel.send()` 推送到钉钉

### 关键模块

| 模块 | 职责 |
|------|------|
| `air/config/__init__.py` | `AppConfig` dataclass，从环境变量加载所有配置；`OPENAI_*` 变量会自动映射为 `ANTHROPIC_*` |
| `air/agent/code_reviewer.py` | `CodeReviewer` — 调用 `claude_agent_sdk.query()`，要求 Claude 以 JSON Schema 格式返回 `ReviewResult` |
| `air/data/review_result.py` | Pydantic 模型：`ReviewResult`（含 `summary` 和 `issues` 列表）、`ReviewIssue`（`file_path`, `line`, `severity`, `message`） |
| `air/source/gitlab_source.py` | `GitLabSource` — 本地模式下调 GitLab API 获取 commit diff |
| `air/channel/base.py` | `Channel` 抽象基类，`send(result) -> bool` |
| `air/channel/dingtalk.py` | `DingtalkChannel` — 将结果格式化为 Markdown 后 POST 到钉钉 Webhook，支持加签 |
| `air/target.py` | `ReviewTarget` dataclass，`kind: "commit"|"mr"` + `ref: str` |

### 扩展指引

- **新增数据源**：在 `air/source/` 中实现，参考 `GitLabSource`
- **新增推送渠道**：在 `air/channel/` 中继承 `Channel` 抽象类

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_BASE_URL` | ✅ | API 地址（自动映射到 `ANTHROPIC_BASE_URL`） |
| `OPENAI_API_KEY` | ✅ | API 密钥（自动映射到 `ANTHROPIC_API_KEY`） |
| `OPENAI_MODEL` | ✅ | 模型名称（同时设置所有 Claude 模型别名） |
| `DINGTALK_WEBHOOK_URL` | ✅ | 钉钉机器人 Webhook 地址 |
| `DINGTALK_WEBHOOK_SECRET` | — | 钉钉机器人加签密钥 |
| `CLAUDE_WORK_DIR` | — | 代码仓库路径，CI 中设为 `$CI_PROJECT_DIR` |
| `CI_JOB_TOKEN` | — | GitLab 自动注入，有值时进入 CI 模式 |
| `CI_PROJECT_ID` | — | GitLab 自动注入 |
| `GITLAB_URL` | — | 本地模式下的 GitLab 地址 |
| `GITLAB_PRIVATE_TOKEN` | — | 本地模式下的 GitLab 认证 token |

> 也可直接使用 `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL`，`OPENAI_*` 是兼容别名。

## 技术要点

- 整体异步架构（`async/await`），入口通过 `asyncio.run()` 驱动
- Claude 集成使用 `claude_agent_sdk.query()` + Pydantic JSON Schema 结构化输出
- 构建后端为 `hatchling`，CLI 入口点定义在 `pyproject.toml` 的 `[project.scripts]`
- CI/CD 通过 GitHub Actions（`.github/workflows/release.yml`）：PyInstaller 编译 → Docker 镜像推送到 GHCR
- 生产 Docker 镜像基于 `node:24-slim`（因为需要 Claude Code CLI），包含 Java 25 + jdtls 支持

## 开发规范

- 所有代码注释和文档使用中文
- 每次变更功能都需要更新 README.md