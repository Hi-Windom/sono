#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BACKEND_PID=""

# 清理函数：优雅关闭后端
cleanup() {
    echo ""
    echo -e "${YELLOW}正在关闭服务...${NC}"
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "  停止后端 (PID: $BACKEND_PID)"
        kill "$BACKEND_PID" 2>/dev/null
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    echo -e "${GREEN}服务已关闭${NC}"
    exit 0
}

trap cleanup INT TERM EXIT

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Sono 开发环境启动脚本${NC}"
echo -e "${GREEN}============================================${NC}"

# 1. 检查并安装前端依赖
echo -e "${YELLOW}[1/5] 检查前端依赖...${NC}"
if [ ! -d "node_modules" ] || [ ! -f "node_modules/.package-lock.json" ]; then
    echo "  安装前端依赖..."
    npm install
else
    echo "  前端依赖已安装"
fi

# 2. 检查并安装后端依赖
echo -e "${YELLOW}[2/5] 检查后端依赖...${NC}"
cd backend
python check_deps.py
cd ..

# 3. 启动后端
echo -e "${YELLOW}[3/5] 启动后端服务...${NC}"
cd backend
python main.py &
BACKEND_PID=$!
cd ..
echo "  后端已启动 (PID: $BACKEND_PID)"

# 4. 等待后端健康检查
echo -e "${YELLOW}[4/5] 等待后端就绪...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/health >/dev/null 2>&1; then
        echo -e "  ${GREEN}后端就绪！${NC}"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  等待后端启动... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 1
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}错误: 后端启动超时${NC}"
    exit 1
fi

# 5. 启动前端
echo -e "${YELLOW}[5/5] 启动前端开发服务器...${NC}"
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  开发环境已启动！${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "  前端: ${BLUE}http://localhost:5173${NC}"
echo -e "  后端: ${BLUE}http://localhost:8000${NC}"
echo -e "  API文档: ${BLUE}http://localhost:8000/docs${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "按 Ctrl+C 关闭所有服务"
echo ""

npm run dev
