# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# AiR - AI Code Reviewer

CI/CD 流水线中的自动代码审查工具，使用 `claude-agent-sdk` 对 GitLab push 中的 commit 进行 Code Review，并将结果推送到钉钉 Webhook。

## 开发命令

```bash
# 安装依赖（Python >= 3.13）
uv sync

# 运行（需先配置环境变量，参考 .env.example）
uv run python -m air --commit <SHA>
uv run python -m air --commit <SHA> --debug
uv run python -m air --commit <SHA> --work-dir /path/to/repo

# CI 模式（自动检测 push 范围，需设置 CI_COMMIT_BEFORE_SHA 和 CI_COMMIT_SHA）
uv run python -m air

# 或使用安装后的命令
air --commit <SHA>
air                          # CI 模式，自动检测

# 类型检查
pyright

# Docker 开发
docker compose run --rm air bash   # 交互式调试

# 快捷测试（Docker 构建 + 审查最新 commit + 推送钉钉）
docker compose build && docker compose run --rm air air --commit HEAD --debug
```

## 项目架构

整体流程由 `air/air.py:main()` 编排：

1. `__main__.py` 解析命令行参数，构建 `ReviewTarget` 和 `AppConfig`，传入 `main()`
   - `--commit SHA`：手动指定单个 commit
   - 无参数：CI 模式，从 `CI_COMMIT_BEFORE_SHA..CI_COMMIT_SHA` 自动检测 commit 范围
2. `ReviewTarget` 包含 commit 列表，根据数量选择审查策略：
   - 正常（≤ max_commits）：传 commit 列表给 Claude，Claude 自行 git 逐个查看
   - 降级（> max_commits）：传整体 diff 范围（before_sha..after_sha）
3. `CodeReviewer.review(target)` 统一入口，调用 Claude 审查
4. 审查结果经 `DingtalkChannel.send()` 推送到钉钉

### 关键模块

| 模块 | 职责 |
|------|------|
| `air/target.py` | `CommitInfo` dataclass（sha、short_sha、author、date、subject）；`ReviewTarget` dataclass，含 `commits` 列表、`before_sha`、`after_sha`、`commit_infos`；工厂方法 `from_gitlab_ci()` 从 CI 环境变量构建、`from_commit(sha)` 从单个 commit 构建 |
| `air/config/__init__.py` | `AppConfig` dataclass；从环境变量加载配置，`OPENAI_*` 自动映射为 `ANTHROPIC_*` |
| `air/agent/code_reviewer.py` | `CodeReviewer` — 调用 `claude_agent_sdk.query()`，统一 `review(target)` 方法，根据 commit 数量选择 prompt 模板 |
| `air/data/review_result.py` | Pydantic 模型：`ReviewResult`（含 `summary` 和 `issues` 列表）、`ReviewIssue`（`file_path`, `start_line`, `end_line`, `severity`, `message`, `original_code`, `suggested_code`） |
| `air/prompts/` | Prompt 模板目录，`load_prompt(name)` 加载 `.md` 模板文件；包含 `review_commits.md` 和 `review_diff.md` |
| `air/channel/base.py` | `Channel` 抽象基类，`send(result) -> bool` |
| `air/channel/dingtalk.py` | `DingtalkChannel` — 将结果格式化为 Markdown（含提交信息、总结、问题列表）后 POST 到钉钉 Webhook，支持加签 |

### 扩展指引

- **新增推送渠道**：在 `air/channel/` 中继承 `Channel` 抽象类

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_BASE_URL` | ✅ | API 地址（自动映射到 `ANTHROPIC_BASE_URL`） |
| `OPENAI_API_KEY` | ✅ | API 密钥（自动映射到 `ANTHROPIC_AUTH_TOKEN`） |
| `OPENAI_MODEL` | ✅ | 模型名称（同时设置所有 Claude 模型别名） |
| `DINGTALK_WEBHOOK_URL` | ✅ | 钉钉机器人 Webhook 地址 |
| `DINGTALK_WEBHOOK_SECRET` | — | 钉钉机器人加签密钥 |
| `AIR_WORK_DIR` | — | 代码仓库路径，CI 中设为 `$CI_PROJECT_DIR`（命令行 `--work-dir` 优先） |
| `AIR_MAX_COMMITS` | — | commit 数量上限，超过时降级为整体 diff 审查，默认 10 |
| `CLAUDE_MAX_TURNS` | — | Claude 最大对话轮数，默认 10 |
| `CI_COMMIT_SHA` | — | GitLab 自动注入，CI 模式必需 |
| `CI_COMMIT_BEFORE_SHA` | — | GitLab 自动注入，用于确定 push 范围 |

> 也可直接使用 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`，`OPENAI_*` 是兼容别名。

## 技术要点

- 整体异步架构（`async/await`），入口通过 `asyncio.run()` 驱动
- Claude 集成使用 `claude_agent_sdk.query()` + Pydantic JSON Schema 结构化输出
- 统一使用 git 命令获取 diff 和上下文，不依赖外部 API
- 构建后端为 `hatchling`，CLI 入口点定义在 `pyproject.toml` 的 `[project.scripts]`
- CI/CD 通过 GitHub Actions（`.github/workflows/release.yml`）：直接构建 Docker 镜像推送到 GHCR（无需 PyInstaller 编译步骤）
- Docker 镜像基于 `node:24-slim`（因为需要 Claude Code CLI），包含 Java 25 + jdtls 支持；开发与生产共用同一个 `docker/Dockerfile`

## 开发规范

- 所有代码注释和文档使用中文
- 每次变更功能都需要更新 README.md
- 每次变更功能都需要更新 CLAUDE.md
