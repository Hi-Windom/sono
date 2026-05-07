#!/data/data/com.termux/files/usr/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Sono 完整打包部署（含前端产物清理）${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

echo -e "${YELLOW}[1/6] 彻底清理前端旧产物...${NC}"
echo "  🗑️  删除 backend/dist..."
rm -rf backend/dist
echo "  🗑️  删除 node_modules/.vite..."
rm -rf node_modules/.vite
echo "  🗑️  删除 node_modules/.cache..."
rm -rf node_modules/.cache
echo "  🗑️  删除 dist..."
rm -rf dist
echo "  ✅  前端旧产物已清理。"

echo ""
echo -e "${YELLOW}[2/6] 构建前端...${NC}"
npm run build
echo "  ✅  前端构建完成。"

echo ""
echo -e "${YELLOW}[3/6] 部署前端到后端...${NC}"
rm -rf backend/dist
cp -r dist backend/
echo "  ✅  前端已部署到 backend/dist。"

echo ""
echo -e "${YELLOW}[4/6] 验证部署文件...${NC}"
if [ -d "backend/dist" ] && [ -f "backend/dist/index.html" ]; then
    echo "  ✅  index.html 存在"
    if ls backend/dist/assets/* 2>/dev/null 1>&2; then
        echo "  ✅  assets 目录有文件"
    else
        echo "  ⚠️  assets 目录可能为空"
    fi
    echo "  📊  dist 目录大小: $(du -sh backend/dist)"
else
    echo -e "${RED}❌  部署失败！${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}[5/6] 清理浏览器缓存提示...${NC}"
echo "  ⚠️  请确保在手机浏览器中："
echo "  1. 清除缓存和Cookie"
echo "  2. 或使用无痕模式"
echo "  3. 或强制刷新（Ctrl+Shift+R/Android: 菜单->刷新）"

echo ""
echo -e "${YELLOW}[6/6] 重启后端服务（如需要）...${NC}"
if pgrep -f "python main.py" >/dev/null 2>&1; then
    echo "  📌  检测到后端正在运行，需要重启以重新加载静态文件！"
    read -p "是否现在重启后端？(y/n, 默认y): " restart_now
    restart_now=${restart_now:-y}
    if [ "$restart_now" = "y" ] || [ "$restart_now" = "Y" ]; then
        echo "  🔄  正在停止后端..."
        pkill -f "python main.py" || true
        sleep 2
        echo "  ✅  已停止，请手动运行 ./start_android.sh 重启"
    fi
else
    echo "  ✅  后端未运行，可以直接启动"
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  ✅  完整打包部署完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "部署完成！请："
echo "1. 清除浏览器缓存或使用无痕模式"
echo "2. 重启后端服务"
echo "3. 访问 http://localhost:8000"
echo ""
