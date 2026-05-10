#!/data/data/com.termux/files/usr/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PYPI_MIRROR_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
PYPI_MIRROR_HOST="pypi.tuna.tsinghua.edu.cn"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Sono Android (Termux) 一键部署脚本${NC}"
echo -e "${GREEN}============================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${YELLOW}[1/5] 清理缓存文件...${NC}"
if [ -d "backend/__pycache__" ]; then
    echo "  清理 Python 缓存..."
    rm -rf backend/__pycache__
    rm -rf backend/api/__pycache__
    rm -rf backend/services/__pycache__
fi
rm -f backend/numba.py backend/soxr.py
echo "  清理完成。"

echo -e "${YELLOW}[2/5] 检查 Termux 环境...${NC}"
if [ ! -d "/data/data/com.termux" ]; then
    echo -e "${RED}错误: 未检测到 Termux 环境，此脚本仅适用于 Termux。${NC}"
    exit 1
fi
echo "  Termux 环境确认。"

echo -e "${YELLOW}[3/5] 安装系统依赖（含预编译 C/Rust 扩展包）...${NC}"
pkg update -y 2>/dev/null || true

MISSING_PKGS=""
for pkg in python clang make pkg-config libc++ libffi openssl curl ca-certificates \
    python-numpy python-scipy rust; do
    if ! dpkg -s "$pkg" &>/dev/null 2>&1; then
        MISSING_PKGS="$MISSING_PKGS $pkg"
    fi
done

if [ -n "$MISSING_PKGS" ]; then
    echo "  需要安装:$MISSING_PKGS"
    echo -e "${YELLOW}  注意: rust 包较大，安装可能需要几分钟...${NC}"
    pkg install -y $MISSING_PKGS
else
    echo "  系统包已满足。"
fi

echo -e "${YELLOW}[4/5] 安装 Python 依赖...${NC}"
cd backend

export TMPDIR="$HOME/.tmp"
mkdir -p "$TMPDIR"
export CARGO_TARGET_DIR="$HOME/.cargo-target"
mkdir -p "$CARGO_TARGET_DIR"

echo "  numpy/scipy 已通过 pkg 预编译安装。"
echo "  使用 --no-build-isolation 避免重复编译 C 扩展..."
echo "  TMPDIR=$TMPDIR (避免 Text file busy 错误)"

if ! pip install --no-build-isolation -r requirements_android.txt -i "$PYPI_MIRROR_URL" --trusted-host "$PYPI_MIRROR_HOST"; then
    echo -e "${YELLOW}  镜像源安装失败，回退到官方 PyPI...${NC}"
    pip install --no-build-isolation -r requirements_android.txt
fi

cd ..

echo -e "${YELLOW}[5/5] 验证关键依赖...${NC}"
cd backend
python -c "import numpy; print(f'  numpy {numpy.__version__} OK')" 2>/dev/null || echo -e "${RED}  numpy 未安装！${NC}"
python -c "import scipy; print(f'  scipy {scipy.__version__} OK')" 2>/dev/null || echo -e "${RED}  scipy 未安装！${NC}"
python -c "import pydantic; print(f'  pydantic {pydantic.__version__} OK')" 2>/dev/null || echo -e "${RED}  pydantic 未安装！${NC}"
python -c "import fastapi; print(f'  fastapi {fastapi.__version__} OK')" 2>/dev/null || echo -e "${RED}  fastapi 未安装！${NC}"
python -c "import miniaudio; print(f'  miniaudio {miniaudio.__version__} OK')" 2>/dev/null || echo -e "${RED}  miniaudio 未安装！音频加载将不可用${NC}"
python -c "import soundfile; print(f'  soundfile {soundfile.__version__} OK')" 2>/dev/null || echo -e "${RED}  soundfile 未安装！${NC}"
python -c "import pytest; print(f'  pytest {pytest.__version__} OK')" 2>/dev/null || echo -e "${RED}  pytest 未安装！质量测试将不可用${NC}"

echo -e "${YELLOW}  编译 DSP 原生加速库...${NC}"
if [ -d "services/dsp_native" ] && command -v make &>/dev/null && command -v gcc &>/dev/null; then
    cd services/dsp_native
    if make 2>/dev/null; then
        cp libdsp_native.so ../repair/repair_v2_2/ 2>/dev/null || true
        echo -e "${GREEN}  DSP 原生库编译成功 (ARM NEON 加速)${NC}"
    else
        echo -e "${YELLOW}  DSP 原生库编译失败，将使用 numpy 回退${NC}"
    fi
    cd ../..
else
    echo -e "${YELLOW}  缺少 gcc/make，跳过 DSP 原生库编译${NC}"
fi

cd ..

cat > start_android.sh << 'STARTEOF'
#!/data/data/com.termux/files/usr/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/backend"

export SERVE_STATIC=1
export MOBILE_MODE=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OMP_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

if [ "$1" = "--clean" ]; then
  echo ""
  echo "🧹 清理旧数据..."
  rm -rf storage/uploads/* storage/outputs/*
  if [ -f storage/tasks.db ]; then
    rm -f storage/tasks.db
    echo "  数据库已删除"
  fi
  echo "  清理完成。"
  echo ""
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Sono - AI Audio Repair (Android/Termux)   ║"
echo "║   http://localhost:8000                      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "请在手机浏览器中访问 http://localhost:8000"
echo "按 Ctrl+C 或关闭 Termux 可停止服务。"
echo "提示: 使用 ./start_android.sh --clean 可清理旧数据后启动"
echo ""

python main.py
STARTEOF

chmod +x start_android.sh

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}  以后只需在 Termux 里执行：${NC}"
echo -e "${GREEN}    cd $SCRIPT_DIR && ./start_android.sh${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${YELLOW}提示:${NC}"
echo -e "${YELLOW}  - 建议关闭 Termux 的电池优化，防止息屏后服务被杀。${NC}"
echo -e "${YELLOW}  - noisereduce 未安装（Termux 不支持 scikit-learn 编译），降噪将使用内置频谱算法。${NC}"
echo -e "${YELLOW}  - pedalboard 未安装（C++ 扩展），v1.1/v1.2 将使用 scipy 降级算法（低通/带通/压缩）。${NC}"
echo -e "${YELLOW}  - 覆盖部署时建议清理旧数据库: ./start_android.sh --clean${NC}"
echo ""

read -p "是否清理旧数据(数据库+缓存)？(y/n, 默认n): " clean_data
clean_data=${clean_data:-n}
if [ "$clean_data" = "y" ] || [ "$clean_data" = "Y" ]; then
  echo -e "${YELLOW}[清理] 删除旧数据...${NC}"
  rm -rf storage/uploads/* storage/outputs/*
  if [ -f storage/tasks.db ]; then
    rm -f storage/tasks.db
    echo -e "${GREEN}  数据库已删除${NC}"
  fi
  echo -e "${GREEN}  清理完成${NC}"
fi
echo ""

read -p "是否现在启动服务？(y/n, 默认n): " start_now
start_now=${start_now:-n}
if [ "$start_now" = "y" ] || [ "$start_now" = "Y" ]; then
    ./start_android.sh
fi
