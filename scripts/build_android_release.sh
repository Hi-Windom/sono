#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Sono Android Release 打包脚本${NC}"
echo -e "${GREEN}============================================${NC}"

echo -e "${YELLOW}[1/4] 清理旧的前端构建产物...${NC}"
# 注意：此脚本构建的 dist 仅用于 Android 打包和桌面生产部署
# 桌面开发预览应使用 `npm run dev` 启动 Vite 热重载服务器，不依赖此 dist
if [ -d "dist" ]; then
    echo "  清理旧的 dist/ 目录..."
    rm -rf dist
fi
if [ -d "backend/dist" ]; then
    echo "  清理旧的 backend/dist/ 目录..."
    rm -rf backend/dist
fi

echo -e "${YELLOW}[2/4] 重新构建前端...${NC}"
if [ ! -f "package.json" ]; then
    echo -e "${RED}错误: package.json 不存在。${NC}"
    exit 1
fi
echo "  运行 npm run build..."
npm run build
if [ ! -d "dist" ] || [ ! -f "dist/index.html" ]; then
    echo -e "${RED}错误: 前端构建失败，dist/ 目录不存在或不完整。${NC}"
    exit 1
fi
echo "  前端构建成功"

echo -e "${YELLOW}[3/4] 检查后端代码...${NC}"
if [ ! -d "backend" ] || [ ! -f "backend/main.py" ]; then
    echo -e "${RED}错误: backend/ 目录不存在或不完整。${NC}"
    exit 1
fi
echo "  后端代码确认: backend/"

echo -e "${YELLOW}[4/4] 打包 release_android.tar.gz...${NC}"

TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

PKG_DIR="$TMP_DIR/sono-android"
mkdir -p "$PKG_DIR"

cp -r backend "$PKG_DIR/"
cp -r dist "$PKG_DIR/backend/dist"
cp deploy/setup_android.sh "$PKG_DIR/"

rm -rf "$PKG_DIR/backend/__pycache__"
rm -rf "$PKG_DIR/backend/api/__pycache__"
rm -rf "$PKG_DIR/backend/services/__pycache__"
rm -rf "$PKG_DIR/backend/storage"
rm -rf "$PKG_DIR/backend/training"
rm -f "$PKG_DIR/backend/server.log"
rm -f "$PKG_DIR/backend/watchdog.log"
rm -f "$PKG_DIR/backend/.venv"

OUTPUT_FILE="$PROJECT_ROOT/release_android.tar.gz"
tar -czf "$OUTPUT_FILE" -C "$TMP_DIR" sono-android

SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  打包完成！${NC}"
echo -e "${GREEN}  产物: $OUTPUT_FILE ($SIZE)${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "用户操作："
echo "  1. 将 release_android.tar.gz 传输到手机"
echo "  2. 在 Termux 中执行："
echo "     tar -xzf release_android.tar.gz && cd sono-android && bash setup_android.sh"
