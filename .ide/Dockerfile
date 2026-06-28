# .ide/Dockerfile

# ==========================================
# 0. 统一版本号管理
# ==========================================
ARG PYTHON_VERSION=3.11
ARG BUN_VERSION=v1.2.15
ARG G_VERSION=1.8.0
ARG GO_VERSION=1.25.1

FROM cnbcool/default-dev-env:latest

ARG PYTHON_VERSION
ARG BUN_VERSION
ARG G_VERSION
ARG GO_VERSION

# ==========================================
# 1. 基础系统与镜像源配置
# ==========================================
USER root

RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.cloud.tencent.com/debian|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org/debian-security|https://mirrors.cloud.tencent.com/debian-security|g' /etc/apt/sources.list || true

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl wget git build-essential ca-certificates \
        libsndfile1 libsndfile1-dev portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# 2. 开发工具链安装 (在 root 下进行)
# ==========================================
# 2.1 安装 uv (Python 包管理器)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# 2.2 安装 Bun
ENV BUN_INSTALL=/opt/bun
RUN curl -fsSL https://bun.sh/install | bash -s "bun-${BUN_VERSION}" && \
    chown -R 1000:1000 /opt/bun

# 2.3 安装 g (Go 版本管理器)
RUN curl -sSL "https://github.com/voidint/g/releases/download/v${G_VERSION}/g${G_VERSION}.linux-amd64.tar.gz" | tar -xz -C /usr/local/bin/

# 2.4 npm 镜像源配置
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

# ==========================================
# 3. 目录预创建与权限分配
# ==========================================
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PYTHON_BIN_DIR=/opt/uv/bin

RUN mkdir -p /opt/uv /root/.g /home/user/.g /root/.cache/uv /home/user/.cache/uv && \
    chown -R 1000:1000 /opt/uv /home/user

# ==========================================
# 4. 注入全局 Shell 配置 (防止 PATH 被覆盖)
# ==========================================
# 创建全局 profile 脚本，无论 root 还是普通用户都会加载
RUN echo '#!/bin/sh' > /etc/profile.d/custom_tools.sh && \
    echo 'export PATH="/opt/uv/venv/bin:/opt/uv/bin:/opt/bun/bin:$HOME/.g/bin:$HOME/.g/go/bin:/usr/local/bin:/root/.local/bin:$PATH"' >> /etc/profile.d/custom_tools.sh && \
    echo 'export VIRTUAL_ENV="/opt/uv/venv"' >> /etc/profile.d/custom_tools.sh && \
    echo 'export UV_INDEX_URL="https://mirrors.cloud.tencent.com/pypi/simple/"' >> /etc/profile.d/custom_tools.sh && \
    echo 'export G_MIRROR="https://golang.google.cn/dl/"' >> /etc/profile.d/custom_tools.sh && \
    chmod +x /etc/profile.d/custom_tools.sh

# 针对 zsh 的特殊处理 (因为 /etc/profile.d 有时不被非交互式 zsh 加载)
RUN echo '[ -f /etc/profile.d/custom_tools.sh ] && source /etc/profile.d/custom_tools.sh' >> /etc/zsh/zshenv && \
    echo '[ -f /etc/profile.d/custom_tools.sh ] && source /etc/profile.d/custom_tools.sh' >> /root/.zshrc

# ==========================================
# 5. 切换至开发用户 (虽然云环境可能强制 root，但保留规范)
# ==========================================
USER 1000:1000
WORKDIR /workspace

ENV HOME=/home/user \
    UV_CACHE_DIR=/home/user/.cache/uv \
    UV_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    UV_TRUSTED_HOST=mirrors.cloud.tencent.com \
    G_MIRROR=https://golang.google.cn/dl/ \
    PATH="/opt/uv/venv/bin:/opt/uv/bin:/opt/bun/bin:/home/user/.g/bin:/home/user/.g/go/bin:/usr/local/bin:/root/.local/bin:$PATH" \
    VIRTUAL_ENV="/opt/uv/venv" \
    NODE_ENV=development \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    GOPATH="/home/user/go"

# ==========================================
# 6. 初始化运行时环境 (使用绝对路径执行，不依赖此时 PATH)
# ==========================================
RUN /root/.local/bin/uv venv /opt/uv/venv --python ${PYTHON_VERSION} && \
    /opt/uv/venv/bin/python --version

# 用 g 安装 Go 时，使用绝对路径并指定到用户目录
# 如果实际以 root 运行，会装到 /root/.g；如果以非 root 运行，会装到 /home/user/.g
RUN /usr/local/bin/g install ${GO_VERSION} && /usr/local/bin/g use ${GO_VERSION}

# ==========================================
# 7. 最终环境验收
# ==========================================
RUN echo "=== 最终环境验证 ===" && \
    python3 --version && \
    /root/.local/bin/uv --version && \
    node --version && \
    bun --version && \
    /usr/local/bin/g --version && \
    go version && \
    echo "✅ 基础环境准备完成"
