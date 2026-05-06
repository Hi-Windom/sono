#!/bin/bash

# AI Audio Repair - 开发环境启动脚本
# 一键启动/重启前后端服务

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 工作目录
WORKSPACE_DIR="/workspace"
BACKEND_DIR="$WORKSPACE_DIR/backend"

# 函数：打印带颜色的信息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 函数：检查端口是否被占用
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 函数：杀死占用端口的进程
kill_port() {
    local port=$1
    local pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null | head -1)
    if [ -n "$pid" ]; then
        print_warning "端口 $port 被进程 $pid 占用，正在终止..."
        kill -9 $pid 2>/dev/null || true
        sleep 1
    fi
}

# 函数：启动服务
start_services() {
    print_info "正在启动 AI Audio Repair 开发环境..."
    
    # 清理现有进程
    print_info "清理现有进程..."
    pm2 delete ai-audio-backend ai-audio-frontend 2>/dev/null || true
    
    # 确保端口可用
    kill_port 8000
    kill_port 5173
    
    # 等待端口释放
    sleep 1
    
    # 启动 PM2 服务
    print_info "启动后端服务 (Python FastAPI)..."
    cd $BACKEND_DIR
    
    # 先检查依赖
    print_info "检查 Python 依赖..."
    python3 -c "import librosa, soundfile, fastapi, uvicorn" 2>/dev/null || {
        print_warning "安装 Python 依赖..."
        pip install -r requirements.txt -q
    }
    
    # 启动后端
    pm2 start $WORKSPACE_DIR/ecosystem.config.cjs --only ai-audio-backend
    
    # 等待后端健康检查通过
    print_info "等待后端服务就绪..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if curl -s --max-time 2 http://localhost:8000/health >/dev/null 2>&1; then
            print_success "后端服务已就绪"
            break
        fi
        retries=$((retries - 1))
        sleep 1
    done
    
    if [ $retries -eq 0 ]; then
        print_error "后端服务启动超时"
        pm2 logs ai-audio-backend --lines 20
        exit 1
    fi
    
    # 启动前端
    print_info "启动前端服务 (Vite)..."
    cd $WORKSPACE_DIR
    pm2 start $WORKSPACE_DIR/ecosystem.config.cjs --only ai-audio-frontend
    
    # 等待前端启动
    print_info "等待前端服务就绪..."
    sleep 3
    
    # 显示状态
    print_success "所有服务已启动！"
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  🎵 AI Audio Repair 开发环境${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "  ${BLUE}前端:${NC} http://localhost:5173"
    echo -e "  ${BLUE}后端:${NC} http://localhost:8000"
    echo -e "  ${BLUE}API文档:${NC} http://localhost:8000/docs"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo ""
    
    # 显示 PM2 状态
    pm2 status
    
    echo ""
    print_info "常用命令："
    echo "  pm2 logs              # 查看所有日志"
    echo "  pm2 logs backend      # 查看后端日志"
    echo "  pm2 logs frontend     # 查看前端日志"
    echo "  pm2 restart all       # 重启所有服务"
    echo "  pm2 stop all          # 停止所有服务"
    echo "  ./dev.sh restart      # 快速重启"
    echo "  ./dev.sh status       # 查看状态"
}

# 函数：重启服务
restart_services() {
    print_info "正在重启服务..."
    
    # 重启后端
    print_info "重启后端..."
    pm2 restart ai-audio-backend
    
    # 等待后端就绪
    local retries=30
    while [ $retries -gt 0 ]; do
        if curl -s --max-time 2 http://localhost:8000/health >/dev/null 2>&1; then
            print_success "后端服务已就绪"
            break
        fi
        retries=$((retries - 1))
        sleep 1
    done
    
    # 重启前端
    print_info "重启前端..."
    pm2 restart ai-audio-frontend
    
    print_success "重启完成！"
    pm2 status
}

# 函数：停止服务
stop_services() {
    print_info "正在停止服务..."
    pm2 stop all
    print_success "服务已停止"
}

# 函数：查看状态
show_status() {
    pm2 status
    echo ""
    print_info "服务健康检查："
    if curl -s --max-time 2 http://localhost:8000/health >/dev/null 2>&1; then
        print_success "后端 (http://localhost:8000) - 正常"
    else
        print_error "后端 (http://localhost:8000) - 异常"
    fi
}

# 函数：查看日志
show_logs() {
    local service=$1
    if [ -n "$service" ]; then
        pm2 logs $service
    else
        pm2 logs
    fi
}

# 主逻辑
case "${1:-start}" in
    start)
        start_services
        ;;
    restart)
        restart_services
        ;;
    stop)
        stop_services
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs $2
        ;;
    *)
        echo "用法: $0 {start|restart|stop|status|logs [service]}"
        echo ""
        echo "命令说明："
        echo "  start   - 启动所有服务（默认）"
        echo "  restart - 重启所有服务"
        echo "  stop    - 停止所有服务"
        echo "  status  - 查看服务状态"
        echo "  logs    - 查看日志（可指定服务名如 backend/frontend）"
        exit 1
        ;;
esac
