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
# 2. 开发工具链安装 (全部以 root 身份)
# ==========================================
# 2.1 uv → /usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

# 2.2 Bun → /opt/bun + 全局软链
ENV BUN_INSTALL=/opt/bun
RUN curl -fsSL https://bun.sh/install | bash -s "bun-${BUN_VERSION}" && \
    ln -sf /opt/bun/bin/bun /usr/local/bin/bun

# 2.3 g → /usr/local/bin
RUN curl -sSL "https://github.com/voidint/g/releases/download/v${G_VERSION}/g${G_VERSION}.linux-amd64.tar.gz" | tar -xz -C /usr/local/bin/

# 2.4 npm 镜像源
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

# ==========================================
# 3. 目录预创建
# ==========================================
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PYTHON_BIN_DIR=/opt/uv/bin

RUN mkdir -p /opt/uv /root/.g /root/.cache/uv

# ==========================================
# 4. 以 root 初始化运行时环境
# ==========================================
ENV G_MIRROR=https://golang.google.cn/dl/ \
    UV_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    UV_TRUSTED_HOST=mirrors.cloud.tencent.com \
    UV_CACHE_DIR=/root/.cache/uv \
    GOPATH=/root/go

# 4.1 Python 虚拟环境
RUN uv venv /opt/uv/venv --python ${PYTHON_VERSION} && \
    /opt/uv/venv/bin/python --version

# 4.2 Go (装到 /root/.g，与运行时用户一致)
RUN g install ${GO_VERSION} && g use ${GO_VERSION}

# ==========================================
# 5. 注入 Shell 配置 (关键！确保终端启动时加载 PATH)
# ==========================================
# /etc/zsh/zshenv — zsh 最先加载的文件，所有模式都会执行
RUN echo '' >> /etc/zsh/zshenv && \
    echo '# ===== Custom Dev Tools PATH =====' >> /etc/zsh/zshenv && \
    echo 'export PATH="/opt/uv/venv/bin:/opt/uv/bin:/opt/bun/bin:/root/.g/bin:/root/.g/go/bin:/usr/local/bin:$PATH"' >> /etc/zsh/zshenv && \
    echo 'export VIRTUAL_ENV="/opt/uv/venv"' >> /etc/zsh/zshenv && \
    echo 'export UV_INDEX_URL="https://mirrors.cloud.tencent.com/pypi/simple/"' >> /etc/zsh/zshenv && \
    echo 'export UV_TRUSTED_HOST="mirrors.cloud.tencent.com"' >> /etc/zsh/zshenv && \
    echo 'export UV_CACHE_DIR="/root/.cache/uv"' >> /etc/zsh/zshenv && \
    echo 'export G_MIRROR="https://golang.google.cn/dl/"' >> /etc/zsh/zshenv && \
    echo 'export GOPATH="/root/go"' >> /etc/zsh/zshenv && \
    echo '# ===== End Custom Dev Tools =====' >> /etc/zsh/zshenv

# /root/.zshrc — 交互式 zsh 补充加载
RUN echo '' >> /root/.zshrc && \
    echo '[ -f /etc/zsh/zshenv ] && source /etc/zsh/zshenv' >> /root/.zshrc

# /etc/profile.d — 兼容 bash 登录 shell
RUN echo '#!/bin/sh' > /etc/profile.d/custom_tools.sh && \
    echo 'export PATH="/opt/uv/venv/bin:/opt/uv/bin:/opt/bun/bin:/root/.g/bin:/root/.g/go/bin:/usr/local/bin:$PATH"' >> /etc/profile.d/custom_tools.sh && \
    echo 'export VIRTUAL_ENV="/opt/uv/venv"' >> /etc/profile.d/custom_tools.sh && \
    echo 'export G_MIRROR="https://golang.google.cn/dl/"' >> /etc/profile.d/custom_tools.sh && \
    echo 'export GOPATH="/root/go"' >> /etc/profile.d/custom_tools.sh && \
    chmod +x /etc/profile.d/custom_tools.sh

# /root/.bashrc — 兼容 bash 交互式
RUN echo '[ -f /etc/profile.d/custom_tools.sh ] && source /etc/profile.d/custom_tools.sh' >> /root/.bashrc

# ==========================================
# 6. 最终环境验收
# ==========================================
WORKDIR /workspace

RUN echo "====================================" && \
    echo "        最终环境验证" && \
    echo "====================================" && \
    echo "uv:   $(/usr/local/bin/uv --version)" && \
    echo "py:   $(/opt/uv/venv/bin/python --version)" && \
    echo "node: $(node --version)" && \
    echo "bun:  $(/opt/bun/bin/bun --version)" && \
    echo "g:    $(/usr/local/bin/g --version)" && \
    echo "go:   $(/root/.g/go/bin/go version)" && \
    echo "====================================" && \
    echo "✅ 环境准备完成"
