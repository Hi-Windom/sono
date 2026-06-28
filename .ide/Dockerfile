# .ide/Dockerfile
FROM debian:12.7

# 切换到 root 用户进行系统配置
USER root

# 配置腾讯云镜像源
RUN sed -Ei "s@https?://deb.debian.org/debian@https://mirrors.cloud.tencent.com/debian@g" /etc/apt/sources.list.d/debian.sources

# 安装基础工具和 Python 环境
RUN apt-get -o Acquire::https::Verify-Peer=false update && \
    apt-get -o Acquire::https::Verify-Peer=false install -y ca-certificates && \
    apt-get update && \
    apt-get install -y \
        git \
        curl \
        wget \
        # Python3 和相关工具
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        # 构建工具（可能需要编译 Python 包）
        build-essential \
        # Node.js 安装工具
        gnupg \
        lsb-release \
    && rm -rf /var/lib/apt/lists/*

# 确保 pip 是最新版本并配置 pip 镜像源
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple/ && \
    python3 -m pip config set global.trusted-host mirrors.cloud.tencent.com

# 创建 python 软链接，确保 python 命令可用
RUN ln -sf /usr/bin/python3 /usr/local/bin/python

# 安装 Node.js (使用 NodeSource 仓库获取较新版本)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# 配置 npm 镜像源
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/

# 预装常用的 Python 数据科学包（根据您的需求）
RUN python3 -m pip install --break-system-packages \
    numpy \
    scipy \
    fastapi \
    uvicorn \
    pytest \
    httpx \
    pyright

# 创建非root用户（重要：很多开发工具不建议用 root 运行）
RUN useradd -m -s /bin/bash developer || true

# 切换到开发用户
USER developer
WORKDIR /workspace

# 设置默认的环境变量
ENV NODE_ENV=development \
    PYTHONPATH=/workspace/backend:$PYTHONPATH

# 验证安装的软件
RUN echo "环境验证:" && \
    python3 --version && \
    python --version && \
    node --version && \
    npm --version && \
    git --version