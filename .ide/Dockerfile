# 探测用的 Dockerfile，运行一次就知道镜像构成
FROM cnbcool/default-dev-env:latest

RUN echo "=== 系统信息 ===" && \
    cat /etc/os-release && \
    echo "=== 已安装软件 ===" && \
    which python python3 node npm 2>/dev/null || echo "部分软件未找到" && \
    echo "=== Python 情况 ===" && \
    python3 --version 2>/dev/null || echo "无 python3" && \
    echo "=== Node 情况 ===" && \
    node --version 2>/dev/null || echo "无 node"