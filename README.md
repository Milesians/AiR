# AiR — AI Code Reviewer

在 GitLab CI/CD 流水线中自动进行代码审查，使用 Claude Code (claude-agent-sdk) 对每次 push 中的所有 commit 进行分析，并将结果推送到钉钉。

---

## 快速接入 GitLab CI

### 第一步：配置 CI/CD 变量

在 GitLab 项目或 Group 的 **Settings → CI/CD → Variables** 中添加以下变量：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `OPENAI_BASE_URL` | Claude/OpenAI 兼容 API 地址 | `https://api.example.com/v1` |
| `OPENAI_API_KEY` | API 密钥 | `sk-xxx` |
| `OPENAI_MODEL` | 使用的模型名称 | `claude-sonnet-4-6` |
| `DINGTALK_WEBHOOK_URL` | 钉钉机器人 Webhook 地址 | `https://oapi.dingtalk.com/robot/send?access_token=xxx` |
| `DINGTALK_WEBHOOK_SECRET` | 钉钉机器人签名密钥（可选） | `SEC...` |

> `CI_COMMIT_SHA`、`CI_COMMIT_BEFORE_SHA` 由 GitLab 自动注入，无需手动配置。

---

### 第二步：在 `.gitlab-ci.yml` 中添加审查 Job

#### 方式一：自动审查 push 中的所有 commit（推荐）

```yaml
ai-code-review:
  stage: review
  image: ghcr.io/milesians/air/air:latest-snapshot
  variables:
    AIR_WORK_DIR: $CI_PROJECT_DIR
  script:
    - air
  rules:
    - if: $CI_PIPELINE_SOURCE == "push"
  allow_failure: true  # 审查失败不阻断流水线
```

#### 方式二：只审查指定 commit

```yaml
ai-code-review:
  stage: review
  image: ghcr.io/milesians/air/air:latest-snapshot
  variables:
    AIR_WORK_DIR: $CI_PROJECT_DIR
  script:
    - air --commit $CI_COMMIT_SHA
  rules:
    - if: $CI_PIPELINE_SOURCE == "push"
  allow_failure: true
```

---

## 工作原理

```
GitLab Push
    │
    ▼
CI Job 启动（挂载代码仓库）
    │
    ▼
air [--commit <SHA>]
    │
    ├─ 无参数（CI 模式）
    │   ├─ 正常 push: git log $CI_COMMIT_BEFORE_SHA..$CI_COMMIT_SHA 获取 commit 列表
    │   └─ 首次/force push: 降级为只审查 $CI_COMMIT_SHA
    │
    └─ --commit <SHA>（手动模式）
        └─ 审查指定的单个 commit
    │
    ▼
commit 数量 ≤ 上限？
    ├─ 是: Claude 逐个 git show 审查每个 commit
    └─ 否: Claude 审查 before..after 整体 diff
    │
    ▼
结构化审查结果（`body` Markdown 正文；结构化输出缺失时降级使用 Agent 文本结果）
    │
    ▼
推送钉钉 Webhook
```

---

## 环境变量完整参考

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `OPENAI_BASE_URL` | ✅ | API 地址（会映射到 `ANTHROPIC_BASE_URL`） |
| `OPENAI_API_KEY` | ✅ | API 密钥（会映射到 `ANTHROPIC_AUTH_TOKEN`） |
| `OPENAI_MODEL` | ✅ | 模型名称，同时设置所有 Claude 模型别名 |
| `DINGTALK_WEBHOOK_URL` | ✅ | 钉钉机器人 Webhook |
| `DINGTALK_WEBHOOK_SECRET` | — | 钉钉机器人加签密钥 |
| `AIR_CONTACTS` | — | 联系人配置（JSON），用于钉钉 @mention，详见下方说明 |
| `AIR_PROJECT_NAME` | — | 钉钉消息中展示的项目名称；未设置时优先使用 `CI_PROJECT_PATH` / `CI_PROJECT_NAME`，再回退到 `AIR_WORK_DIR` 目录名 |
| `AIR_WORK_DIR` | — | 代码仓库路径，CI 中设为 `$CI_PROJECT_DIR`（命令行 `--work-dir` 优先） |
| `AIR_MAX_COMMITS` | — | commit 数量上限，超过时降级为整体 diff 审查，默认 10 |
| `CLAUDE_MAX_TURNS` | — | Claude 最大对话轮数，默认 10 |
| `CI_COMMIT_SHA` | — | GitLab 自动注入，CI 模式必需 |
| `CI_COMMIT_BEFORE_SHA` | — | GitLab 自动注入，用于确定 push 范围 |

> 也可以直接使用 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`，`OPENAI_*` 变量是兼容别名。

---

## 命令行参数

```
air                                    # CI 模式，自动检测 push 中的 commit 范围
air --commit <SHA>                     # 审查指定的单个 commit
air --commit <SHA> --work-dir /path    # 指定工作目录
air --debug                            # 开启 Debug 日志
```

---

## 钉钉机器人配置

1. 在钉钉群中添加「自定义机器人」
2. 安全设置选择「加签」，记录 Secret
3. 将 Webhook 地址填入 `DINGTALK_WEBHOOK_URL`，Secret 填入 `DINGTALK_WEBHOOK_SECRET`

审查结果将以 Markdown 格式发送：
- 程序固定补充项目名称、涉及的提交信息（提交哈希、提交人、提交时间）与 @mention
- Agent 仅返回一个 `body` 字段，其值会直接作为钉钉正文透传，标题也会优先从正文首行提取，结构不再由程序写死

### 联系人 @mention 配置

通过 `AIR_CONTACTS` 环境变量传入 JSON 格式的联系人列表，钉钉通知会根据提交信息自动 @mention 相关人员：

```json
{
    "users": [
        {
            "name": "张三",
            "email": "zhangsan@example.com",
            "phone": "13800138000",
            "regex": "zhangsan|张三",
            "role": "maintainer"
        },
        {
            "name": "李四",
            "email": "lisi@example.com",
            "phone": "13900139000",
            "regex": "lisi",
            "role": "developer"
        }
    ]
}
```

**匹配规则：**
- 用每个联系人的 `regex` 正则表达式匹配提交标题、提交人、提交人邮箱
- 匹配到则 @mention 该联系人的手机号
- 没有匹配到任何人时，@mention 所有 `role` 为 `maintainer` 的联系人
- 未配置 `AIR_CONTACTS` 时输出 warn 日志，不 @mention 任何人

---

## 本地开发

### 环境要求

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器
- Docker & Docker Compose（可选，用于容器化调试）

### 安装与运行

```bash
# 克隆项目
git clone git@github.com:Milesians/AiR.git
cd AiR

# 安装依赖
uv sync

# 复制环境变量模板并填写配置
cp .env.example .env
# 编辑 .env，填入 API 地址、密钥等

# 本地运行
uv run air --commit <SHA>
uv run air --commit <SHA> --debug
```

### Docker 环境调试

项目提供了基于 `docker-compose.yml` 的开发环境，使用与生产相同的 `docker/Dockerfile` 镜像，方便在容器内模拟 CI 环境进行调试。

#### 准备工作

1. 复制 `.env.example` 为 `.env` 并填写配置
2. 准备待审查的代码仓库路径，设置 `REPO_PATH`：

```bash
# .env 中设置
REPO_PATH=/path/to/your/repo    # 待审查的 git 仓库路径
```

#### 快捷测试

```bash
# 构建镜像 + 审查最新 commit + 推送钉钉（含 debug 日志）
docker compose build && docker compose run --rm air air --commit HEAD --debug
```

#### 审查单个 commit

```bash
# 默认命令：审查指定 commit
docker compose up --build

# 或指定 commit SHA
COMMIT_SHA=abc1234 docker compose up --build
```

#### 模拟 CI push（多 commit 审查）

```bash
# 设置 CI 环境变量，模拟一次 push 中包含多个 commit
CI_COMMIT_BEFORE_SHA=<push前SHA> CI_COMMIT_SHA=<push后SHA> \
  docker compose run --rm air air

# 模拟首次 push（before_sha 为全零，降级为单 commit）
CI_COMMIT_BEFORE_SHA=0000000000000000000000000000000000000000 \
  CI_COMMIT_SHA=abc1234 \
  docker compose run --rm air air
```

#### 交互式调试

```bash
# 进入容器 bash，手动执行命令
docker compose run --rm air bash

# 容器内可直接运行
air --commit <SHA> --debug
air   # 需设置 CI_COMMIT_SHA / CI_COMMIT_BEFORE_SHA
```

#### Docker 开发镜像说明

- 基于 `node:24-slim`（因为依赖 Claude Code CLI）
- 包含 Java 25 + jdtls（Eclipse JDT Language Server，用于 Claude Code 分析 Java 项目）
- 通过 `volumes` 将本地代码仓库只读挂载到 `/workspace`
- 环境变量从 `.env` 文件自动加载

### 类型检查

```bash
pyright
```

---

## CI/CD

项目通过 GitHub Actions 自动构建和发布（`.github/workflows/release.yml`）：

1. **触发条件**：向仓库推送 Git Tag 时触发（例如在分支上执行 `git tag v1.0.0 && git push origin v1.0.0`）
2. **build-docker**：直接从源码构建 Docker 镜像（使用 uv 安装依赖），推送到 GitHub Container Registry（`ghcr.io`）
3. **release**：基于该 Tag 自动发布 GitHub Release（自动生成发布说明），并附带镜像离线包 `air-<tag>-linux-amd64.tar.gz` 与对应的 `.sha256` 校验文件

镜像标签格式：`ghcr.io/milesians/air/air:<tag>`（例如 `ghcr.io/milesians/air/air:v1.0.0`）。
离线镜像可通过 `docker load -i air-<tag>-linux-amd64.tar.gz` 导入。

### 依赖升级策略（Dependabot）

- `.github/dependabot.yml` 对 `uv` 生态配置了 `groups`，每轮检查会将匹配到的依赖升级聚合在同一个 PR 中，而不是按依赖分别创建多个 PR。
