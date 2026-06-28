# .ide/Dockerfile
FROM cnbcool/default-dev-env:latest

USER root

# 配置腾讯云镜像源
RUN sed -Ei "s@https?://deb.debian.org/debian@https://mirrors.cloud.tencent.com/debian@g" /etc/apt/sources.list.d/debian.sources

# 只安装必要的系统包，不碰 Python 环境
RUN apt-get -o Acquire::https::Verify-Peer=false update && \
    apt-get -o Acquire::https::Verify-Peer=false install -y ca-certificates && \
    apt-get update && \
    apt-get install -y \
        build-essential \
        curl \
        wget \
    && rm -rf /var/lib/apt/lists/*

# 直接使用系统自带的 pip，不升级，只配置镜像源
RUN python3 -m pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple/ || true && \
    python3 -m pip config set global.trusted-host mirrors.cloud.tencent.com || true

# 安装 Python 包，使用 --break-system-packages 但不升级 pip
RUN python3 -m pip install --break-system-packages \
    numpy \
    scipy \
    fastapi \
    uvicorn \
    pytest \
    httpx \
    pyright || true

# 创建 python 软链接
RUN ln -sf /usr/bin/python3 /usr/local/bin/python || true

# 配置 npm 镜像源
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

USER 1000:1000
WORKDIR /workspace

ENV NODE_ENV=development \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

# 验证环境
RUN python3 --version && node --version && npm --version