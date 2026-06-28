FROM cnbcool/default-dev-env:latest

USER root

# 腾讯云 Debian 镜像源
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.cloud.tencent.com/debian|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org/debian-security|https://mirrors.cloud.tencent.com/debian-security|g' /etc/apt/sources.list || true

# 基础系统依赖
RUN apt-get update && \
    apt-get install -y \
        curl wget git build-essential ca-certificates \
        libsndfile1 libsndfile1-dev portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# 腾讯云镜像源 + uv 目录配置
ENV UV_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    UV_TRUSTED_HOST=mirrors.cloud.tencent.com \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PYTHON_BIN_DIR=/opt/uv/bin

# npm 镜像源
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

# 预创建目录并赋权，确保非 root 用户可写
RUN mkdir -p /opt/uv /home/user/.cache/uv && \
    chown -R 1000:1000 /opt/uv /home/user

USER 1000:1000
WORKDIR /workspace

# 设置 HOME 和缓存目录，解决权限问题
ENV HOME=/home/user \
    UV_CACHE_DIR=/home/user/.cache/uv \
    PATH="/opt/uv/venv/bin:/opt/uv/bin:/root/.local/bin:$PATH" \
    VIRTUAL_ENV="/opt/uv/venv" \
    NODE_ENV=development \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

# 一条命令搞定：创建 venv，自动下载 Python 3.11
RUN uv venv /opt/uv/venv --python 3.11 && \
    /opt/uv/venv/bin/python --version

RUN python3 --version && uv --version && node --version && \
    echo "✅ 环境准备完成"
