# .ide/Dockerfile
FROM cnbcool/default-dev-env:latest

USER root

# 预装常用的 Python 包
RUN python -m pip install numpy scipy fastapi pytest httpx

# 切换到非root用户（如果基础镜像支持）
USER 1000:1000

WORKDIR /workspace