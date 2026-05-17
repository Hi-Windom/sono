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

echo -e "${YELLOW}[3.5/4] 验证 Python 模块导入...${NC}"
PYTHON_CHECK_FAILED=0
cd backend
echo "  安装必要的依赖用于检查..."
pip install -q numpy scipy soundfile 2>/dev/null || echo "  依赖安装警告（将尝试继续检查）"
python -c "
import sys
import os

errors = []

# 检查核心模块导入
modules_to_check = [
    'services.repair.repair_v3_2ap.core',
    'services.repair.repair_v3_2.core',
    'services.repair.repair_v3_2a.core',
]

for module_name in modules_to_check:
    try:
        __import__(module_name)
        print(f'  OK: {module_name}')
    except Exception as e:
        print(f'  ERROR: {module_name}: {e}')
        errors.append((module_name, str(e)))

if errors:
    print('')
    print('模块导入检查失败！')
    for mod, err in errors:
        print(f'  - {mod}: {err}')
    sys.exit(1)
" || PYTHON_CHECK_FAILED=1
cd ..
if [ $PYTHON_CHECK_FAILED -eq 1 ]; then
    echo -e "${RED}错误: Python 模块导入检查失败，请修复后再打包。${NC}"
    exit 1
fi
echo "  模块导入检查通过。"

echo -e "${YELLOW}[4/4] 检查 Termux 不兼容依赖...${NC}"
KNOWN_INCOMPATIBLE="psutil lameenc"
INCOMPATIBLE_FOUND=""
while IFS= read -r line; do
    line="$(echo "$line" | sed 's/#.*//' | xargs)"
    [ -z "$line" ] && continue
    for pkg in $KNOWN_INCOMPATIBLE; do
        if echo "$line" | grep -qi "^${pkg}"; then
            INCOMPATIBLE_FOUND="$INCOMPATIBLE $pkg"
        fi
    done
done < backend/requirements_android.txt

if [ -n "$INCOMPATIBLE_FOUND" ]; then
    echo -e "${RED}错误: requirements_android.txt 包含 Termux 不支持的依赖:${NC}"
    for pkg in $INCOMPATIBLE_FOUND; do
        echo -e "${RED}  - $pkg${NC}"
    done
    echo -e "${RED}请从 requirements_android.txt 中移除后再打包。${NC}"
    exit 1
fi
echo "  依赖检查通过。"

echo "  清理 Python 缓存文件..."
find "$PROJECT_ROOT/backend" -name "*.pyc" -delete
find "$PROJECT_ROOT/backend" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
echo "  Python 缓存已清理。"

echo "  预编译 .pyc 文件..."
python -m compileall -q backend/ 2>/dev/null || echo "  预编译跳过（非关键）"

echo -e "${YELLOW}[4/4] 打包 release_android.tar.gz...${NC}"

TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

PKG_DIR="$TMP_DIR/sono-android"
mkdir -p "$PKG_DIR"

cp -r backend "$PKG_DIR/"
cp -r dist "$PKG_DIR/backend/dist"
cp deploy/setup_android.sh "$PKG_DIR/"

# 删除开发/测试相关文件（设备上不需要）
rm -rf "$PKG_DIR/backend/tests"
# 删除开发数据库（设备上会重新创建）
rm -f "$PKG_DIR/backend/sono.db"
# 删除非必要的开发文件
rm -f "$PKG_DIR/backend/services/dsp_native/Makefile"
rm -f "$PKG_DIR/backend/services/dsp_native/dsp_core.c"
rm -f "$PKG_DIR/backend/services/repair/QUALITY_RULES.md"
rm -f "$PKG_DIR/backend/watchdog.sh"
# 删除运行时不需要的目录和文件
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
