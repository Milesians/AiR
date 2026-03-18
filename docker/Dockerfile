FROM node:24-slim

# 设置时区为东八区
ENV TZ=Asia/Shanghai
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" >/etc/timezone

# 安装系统依赖，完成后清理仅安装时需要的包
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       wget apt-transport-https gpg ca-certificates \
    && mkdir -p /etc/apt/keyrings \
    && wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public \
       | gpg --dearmor -o /etc/apt/keyrings/adoptium.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb bookworm main" \
       > /etc/apt/sources.list.d/adoptium.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       tzdata git curl bash jq openssl gettext-base \
       temurin-25-jdk \
    && apt-get purge -y --auto-remove wget apt-transport-https gpg \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN ln -s "$(dirname $(dirname $(readlink -f /usr/bin/java)))" /usr/lib/jvm/default-jdk
ENV JAVA_HOME=/usr/lib/jvm/default-jdk

# 安装 jdtls (Eclipse JDT Language Server)
RUN curl -fsSL "https://download.eclipse.org/jdtls/snapshots/jdt-language-server-latest.tar.gz" \
    -o /tmp/jdtls.tar.gz \
    && mkdir -p /opt/jdtls \
    && tar -xzf /tmp/jdtls.tar.gz -C /opt/jdtls \
    && rm /tmp/jdtls.tar.gz \
    && chmod +x /opt/jdtls/bin/jdtls
ENV PATH="/opt/jdtls/bin:${PATH}"

# 安装 Claude Code（需 root 写入 /usr/local/lib/node_modules）
RUN npm install -g @anthropic-ai/claude-code

# 创建非 root 用户，避免 claude --dangerously-skip-permissions 拒绝 root 执行
RUN useradd -m -s /bin/bash air

USER air
WORKDIR /home/air/app

# 初始化 Claude Code 用户配置
RUN claude install

# 将 preset 目录下的 skills/commands/agents 合并到用户目录供 Claude Code 识别
COPY --chown=air:air prese[t]/ /home/air/.claude/

# 复制项目源码并安装依赖（含项目本身，生成 .venv/bin/air 入口）
COPY --chown=air:air pyproject.toml uv.lock /home/air/app/
COPY --chown=air:air air/ /home/air/app/air/
RUN uv sync

ENV PATH="/home/air/app/.venv/bin:${PATH}"
ENV CLAUDE_CLI_PATH=/usr/local/bin/claude
