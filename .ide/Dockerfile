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
    && rm -rf /var/lib/apt/lists/*

# 安装 uv (现代化的 Python 包管理器)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# 确保 uv 在 PATH 中
ENV PATH="/root/.local/bin:$PATH"

# 验证 uv 安装
RUN uv --version

# 使用 uv 安装 Python 并设置环境
# uv 会自动管理 Python 版本，这里我们让它使用系统 Python 或安装指定版本
RUN uv python install 3.11 || uv python install 3.12 || echo "使用系统 Python"

# 创建 python 软链接 (确保 python 命令可用)
RUN ln -sf /usr/bin/python3 /usr/local/bin/python || \
    ln -sf $(uv python find 3.11 2>/dev/null || uv python find 3.12 2>/dev/null) /usr/local/bin/python || \
    echo "python 软链接创建跳过"

# 配置 uv 使用腾讯云镜像源
RUN mkdir -p /root/.config/uv && \
    echo '[registry]' > /root/.config/uv/uv.toml && \
    echo 'url = "https://mirrors.cloud.tencent.com/pypi/simple/"' >> /root/.config/uv/uv.toml && \
    echo 'verify-ssl = true' >> /root/.config/uv/uv.toml

# 使用 uv 安装 Python 包 (比 pip 快很多)
RUN uv pip install --system \
    numpy \
    scipy \
    fastapi \
    uvicorn \
    pytest \
    httpx \
    pyright

# 配置 npm 镜像源
RUN npm config set registry https://mirrors.cloud.tencent.com/npm/ || true

USER 1000:1000

WORKDIR /workspace

ENV NODE_ENV=development \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# 验证环境
RUN echo "=== 环境验证 ===" && \
    (python3 --version || python --version) && \
    node --version && \
    npm --version && \
    uv --version && \
    echo "=== Python 包验证 ===" && \
    python3 -c "import numpy, scipy, fastapi; print('✅ 后端依赖正常')" 2>/dev/null || \
    python -c "import numpy, scipy, fastapi; print('✅ 后端依赖正常')" && \
    echo "=== uv 包管理验证 ===" && \
    uv pip list --system 2>/dev/null || pip list 2>/dev/null || echo "包列表获取跳过"