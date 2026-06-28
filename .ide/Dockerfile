# .ide/Dockerfile
# 基于 CNB 官方开发环境镜像
FROM cnbcool/default-dev-env:latest

USER root

# 配置腾讯云镜像源（Debian 系统）
RUN sed -Ei "s@https?://deb.debian.org/debian@https://mirrors.cloud.tencent.com/debian@g" /etc/apt/sources.list.d/debian.sources

# 更新包管理器并安装 Python 环境
RUN apt-get -o Acquire::https::Verify-Peer=false update && \
    apt-get -o Acquire::https::Verify-Peer=false install -y ca-certificates && \
    apt-get update && \
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-full \
        build-essential \
        curl \
        wget \
    && rm -rf /var/lib/apt/lists/*

# 处理 Debian 12 的 PEP 668 保护机制
RUN echo "export PIP_BREAK_SYSTEM_PACKAGES=1" >> /etc/bash.bashrc

# 升级 pip 并配置腾讯云镜像源
RUN export PIP_BREAK_SYSTEM_PACKAGES=1 && \
    python3 -m pip install --upgrade pip && \
    python3 -m pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple/ && \
    python3 -m pip config set global.trusted-host mirrors.cloud.tencent.com

# 创建 python 软链接
RUN ln -sf /usr/bin/python3 /usr/local/bin/python

# 安装常用的 Python 包
RUN export PIP_BREAK_SYSTEM_PACKAGES=1 && \
    python3 -m pip install \
        numpy \
        scipy \
        fastapi \
        uvicorn \
        pytest \
        httpx \
        pyright

# 配置 npm 镜像源（如果需要）
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

# 确保开发用户权限正确
USER 1000:1000

WORKDIR /workspace

# 设置环境变量
ENV NODE_ENV=development \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

# 验证环境
RUN echo "环境验证:" && \
    python3 --version && \
    python --version && \
    node --version && \
    npm --version && \
    echo "Python 包验证:" && \
    python3 -c "import numpy, scipy, fastapi; print('✅ 后端依赖正常')"