# .ide/Dockerfile
FROM cnbcool/default-dev-env:latest

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

# 2.2 安装 Bun v1.2 (指定安装目录到 /opt/bun)
ENV BUN_INSTALL=/opt/bun
RUN curl -fsSL https://bun.sh/install | bash && \
    chown -R 1000:1000 /opt/bun

# 2.3 安装 g (Go 版本管理器)
#     G_HOME 指定 g 的工作目录，避免散落在 $HOME
#     G_MIRROR 指定国内镜像源加速下载 Go 安装包
ENV G_HOME=/opt/g \
    G_MIRROR=https://golang.google.cn/dl/
RUN curl -sSL https://raw.githubusercontent.com/voidint/g/master/install.sh | bash && \
    chown -R 1000:1000 /opt/g

# 2.4 npm 镜像源配置
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

# ==========================================
# 3. 目录预创建与权限分配
# ==========================================
# uv 托管目录收敛到 /opt/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PYTHON_BIN_DIR=/opt/uv/bin

RUN mkdir -p /opt/uv /home/user/.cache/uv && \
    chown -R 1000:1000 /opt/uv /home/user

# ==========================================
# 4. 切换至开发用户
# ==========================================
USER 1000:1000
WORKDIR /workspace

# 集中配置全局环境变量
ENV HOME=/home/user \
    UV_CACHE_DIR=/home/user/.cache/uv \
    UV_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    UV_TRUSTED_HOST=mirrors.cloud.tencent.com \
    # 工具链 PATH 聚合：
    #   /opt/g/bin      → g 工具本身
    #   /opt/g/go/bin   → g 当前激活的 Go 版本（软链接 ~/.g/go）
    #   /opt/uv/venv/bin → Python 虚拟环境
    #   /opt/uv/bin     → uv 托管 Python 可执行链接
    #   /opt/bun/bin    → Bun
    PATH="/opt/uv/venv/bin:/opt/uv/bin:/opt/bun/bin:/opt/g/bin:/opt/g/go/bin:/root/.local/bin:$PATH" \
    VIRTUAL_ENV="/opt/uv/venv" \
    NODE_ENV=development \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    GOPATH="/home/user/go"

# ==========================================
# 5. 初始化运行时环境
# ==========================================
# 5.1 创建 Python 虚拟环境 (uv 自动下载 Python 3.11)
RUN uv venv /opt/uv/venv --python 3.11 && \
    /opt/uv/venv/bin/python --version

# 5.2 用 g 安装并激活 Go 1.25.1
RUN g install 1.25.1 && g use 1.25.1

# ==========================================
# 6. 最终环境验收
# ==========================================
RUN echo "=== 最终环境验证 ===" && \
    python3 --version && \
    uv --version && \
    node --version && \
    bun --version && \
    g --version && \
    go version && \
    echo "✅ 基础环境准备完成"
