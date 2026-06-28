# .ide/Dockerfile
FROM cnbcool/default-dev-env:latest

USER root

# 配置腾讯云 Debian 镜像源（Debian 13 使用 deb822 格式）
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.cloud.tencent.com/debian|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org/debian-security|https://mirrors.cloud.tencent.com/debian-security|g' /etc/apt/sources.list || true

# 更新并安装 Python3 环境
RUN apt-get update && \
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        curl \
        wget \
    && rm -rf /var/lib/apt/lists/*

# 配置 pip 镜像源并安装 Python 包
RUN python3 -m pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple/ && \
    python3 -m pip config set global.trusted-host mirrors.cloud.tencent.com && \
    python3 -m pip install --break-system-packages \
        numpy \
        scipy \
        fastapi \
        uvicorn \
        pytest \
        httpx \
        pyright

# 创建 python 软链接
RUN ln -sf /usr/bin/python3 /usr/local/bin/python

# 配置 npm 镜像源
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

USER 1000:1000

WORKDIR /workspace

ENV NODE_ENV=development \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

# 验证环境
RUN echo "=== 环境验证 ===" && \
    python3 --version && \
    python --version && \
    node --version && \
    npm --version && \
    echo "=== Python 包验证 ===" && \
    python3 -c "import numpy, scipy, fastapi; print('✅ 后端依赖正常')"