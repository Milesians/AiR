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
       tzdata git curl bash jq openssl gettext-base python3 \
       temurin-25-jdk \
    && apt-get purge -y --auto-remove wget apt-transport-https gpg \
    && rm -rf /var/lib/apt/lists/*

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

# 安装 Claude Code
RUN npm install -g @anthropic-ai/claude-code
RUN claude install
# 复制预编译的二进制（由 CI 编译后放入 dist/）
COPY dist/air /usr/local/bin/air
RUN chmod +x /usr/local/bin/air


# 创建非 root 用户，避免 claude --dangerously-skip-permissions 拒绝 root 执行
RUN useradd -m -s /bin/bash air

# 将基础镜像中 root 的 claude 配置（含 plugin）复制到 air 用户目录
RUN cp -r /root/.claude /home/air/.claude 2>/dev/null || true

# 将 preset 目录下的 skills/commands/agents 合并到用户目录供 Claude Code 识别
COPY prese[t]/ /home/air/.claude/
RUN chown -R air:air /home/air/.claude

# 创建 Claude Code 所需的配置文件
RUN test -f /home/air/.claude.json || echo '{}' > /home/air/.claude.json; chown air:air /home/air/.claude.json

USER air
WORKDIR /home/air
RUN claude plugin marketplace add https://github.com/anthropics/claude-plugins-official --scope user
RUN claude plugin install jdtls-lsp@claude-plugins-official --scope user
