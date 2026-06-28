# .ide/Dockerfile
FROM debian:12.7

USER root

# 配置腾讯云镜像源
RUN sed -Ei "s@https?://deb.debian.org/debian@https://mirrors.cloud.tencent.com/debian@g" /etc/apt/sources.list.d/debian.sources

# 安装基础工具
RUN apt-get -o Acquire::https::Verify-Peer=false update && \
    apt-get -o Acquire::https::Verify-Peer=false install -y ca-certificates && \
    apt-get update && \
    apt-get install -y \
        git \
        curl \
        wget \
        python3 \
        python3-pip \
        python3-venv \
        build-essential \
        gnupg \
        lsb-release \
    && rm -rf /var/lib/apt/lists/*

# 关键：绕过 PEP 668 保护（在容器环境中是可以接受的）
RUN echo "export PIP_BREAK_SYSTEM_PACKAGES=1" >> /etc/bash.bashrc

# 升级 pip 并安装基础包
RUN export PIP_BREAK_SYSTEM_PACKAGES=1 && \
    python3 -m pip install --upgrade pip && \
    python3 -m pip install \
        numpy \
        scipy \
        fastapi \
        uvicorn \
        pytest \
        httpx \
        pyright

# 安装 Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# 创建 python 软链接
RUN ln -sf /usr/bin/python3 /usr/local/bin/python

# 创建非root用户
RUN useradd -m -s /bin/bash developer || true

USER developer
WORKDIR /workspace

ENV NODE_ENV=development \
    PIP_BREAK_SYSTEM_PACKAGES=1

# 验证环境
RUN python3 --version && node --version && npm --version