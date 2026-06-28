# .ide/Dockerfile
FROM cnbcool/default-dev-env:latest

USER root

# 配置腾讯云 Debian 镜像源
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.cloud.tencent.com/debian|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org/debian-security|https://mirrors.cloud.tencent.com/debian-security|g' /etc/apt/sources.list || true

# 安装基础系统依赖
RUN apt-get update && \
    apt-get install -y \
        curl \
        wget \
        git \
        build-essential \
        ca-certificates \
        libsndfile1 \
        libsndfile1-dev \
        portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv (现代化的 Python 包管理器)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# 确保 uv 在 PATH 中
ENV PATH="/root/.local/bin:$PATH"

# 验证 uv 安装
RUN uv --version

# 使用 uv 安装 Python 3.11
RUN uv python install 3.11

# 创建 python 软链接指向 uv 安装的 Python
RUN ln -sf $(uv python find 3.11) /usr/local/bin/python && \
    ln -sf $(uv python find 3.11) /usr/local/bin/python3

# 配置 uv 使用腾讯云镜像源
RUN mkdir -p /root/.config/uv && \
    echo 'index-url = "https://mirrors.cloud.tencent.com/pypi/simple/"' > /root/.config/uv/uv.toml && \
    echo 'trusted-host = ["mirrors.cloud.tencent.com"]' >> /root/.config/uv/uv.toml

# 配置 npm 镜像源
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

USER 1000:1000

WORKDIR /workspace

ENV NODE_ENV=development \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

# 注意：实际的依赖安装将在 .cnb.yml 的流水线中进行
# 这里只是准备基础环境（Python + uv + Node.js）
# 依赖安装逻辑已经移动到 .cnb.yml 的 stages 中