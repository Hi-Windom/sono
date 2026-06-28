# .ide/Dockerfile
FROM cnbcool/default-dev-env:latest

USER root

# 安装 Python3 和 pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 确保 pip 是最新版本
RUN python3 -m pip install --upgrade pip

# 创建 python 软链接
RUN ln -sf /usr/bin/python3 /usr/local/bin/python

# 预装常用的 Python 包（可选）
RUN python3 -m pip install numpy scipy fastapi pytest httpx

# 切换到非root用户（如果基础镜像支持）
USER 1000:1000

WORKDIR /workspace