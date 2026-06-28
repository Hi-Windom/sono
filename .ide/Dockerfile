# .ide/Dockerfile
FROM cnbcool/default-dev-env:latest

USER root

# 配置腾讯云 Debian 镜像源
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.cloud.tencent.com/debian|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org/debian-security|https://mirrors.cloud.tencent.com/debian-security|g' /etc/apt/sources.list || true

# 安装基础系统依赖
RUN apt-get update && \
    apt-get install -y \
        curl wget git build-essential ca-certificates \
        libsndfile1 libsndfile1-dev portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# uv 托管 Python 收敛到 /opt/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PYTHON_BIN_DIR=/opt/uv/bin

# 安装 Python 3.11（唯一指定版本，避免 base 镜像的 3.14 干扰）
RUN uv python install 3.11

# 配置腾讯云镜像源
ENV UV_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    UV_TRUSTED_HOST=mirrors.cloud.tencent.com

# 配置 npm 镜像源
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

# 切换到非 root 用户
USER 1000:1000

WORKDIR /workspace

# 创建项目虚拟环境（指定 Python 3.11，放在 /opt/uv/venv 供全局使用）
RUN uv venv /opt/uv/venv --python 3.11 && \
    /opt/uv/venv/bin/python --version

ENV PATH="/opt/uv/venv/bin:/opt/uv/bin:/root/.local/bin:$PATH" \
    VIRTUAL_ENV="/opt/uv/venv" \
    NODE_ENV=development \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

# 最终验证
RUN echo "=== 最终环境验证 ===" && \
    python3 --version && \
    uv --version && \
    node --version && \
    echo "✅ 基础环境准备完成"
