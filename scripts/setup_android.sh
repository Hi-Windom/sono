#!/data/data/com.termux/files/usr/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

TERMUX_MIRROR_URL="https://mirrors.tuna.tsinghua.edu.cn/termux"
PYPI_MIRROR_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
PYPI_MIRROR_HOST="pypi.tuna.tsinghua.edu.cn"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Sono Android (Termux) 一键部署脚本${NC}"
echo -e "${GREEN}============================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${YELLOW}[1/7] 检查 Termux 环境...${NC}"
if [ ! -d "/data/data/com.termux" ]; then
    echo -e "${RED}错误: 未检测到 Termux 环境，此脚本仅适用于 Termux。${NC}"
    exit 1
fi
echo "  Termux 环境确认。"

echo -e "${YELLOW}[2/7] 配置 Termux 软件源镜像...${NC}"
if ! grep -q "$TERMUX_MIRROR_URL" $PREFIX/etc/apt/sources.list 2>/dev/null; then
    sed -i "s@^\(deb.*stable main\)\$@#\1\ndeb ${TERMUX_MIRROR_URL}/apt/termux-main stable main@" $PREFIX/etc/apt/sources.list
    echo "  已切换到清华镜像源。"
else
    echo "  镜像源已配置。"
fi
pkg update -y 2>/dev/null || true

echo -e "${YELLOW}[3/7] 安装系统依赖（含预编译 C/Rust 扩展包）...${NC}"
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

echo -e "${YELLOW}[4/7] 安装 Python 构建工具...${NC}"
pip install setuptools maturin -i "$PYPI_MIRROR_URL" --trusted-host "$PYPI_MIRROR_HOST" 2>/dev/null || \
    pip install setuptools maturin

echo -e "${YELLOW}[5/7] 安装 Python 依赖...${NC}"
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

echo "  安装 librosa（跳过 scikit-learn 依赖）..."
if ! pip install --no-build-isolation --no-deps librosa -i "$PYPI_MIRROR_URL" --trusted-host "$PYPI_MIRROR_HOST"; then
    pip install --no-build-isolation --no-deps librosa
fi

echo "  创建 soxr stub 模块（让 librosa 能导入但不使用 soxr）..."
SOXR_STUB="$SCRIPT_DIR/backend/soxr.py"
cat > "$SOXR_STUB" << 'STUBEOF'
import numpy as np
from scipy.signal import resample_poly

def resample(x, in_rate, out_rate, quality="HQ"):
    if x.ndim == 1:
        return resample_poly(x, out_rate, in_rate).astype(x.dtype)
    elif x.ndim == 2:
        out = np.zeros((x.shape[0], int(x.shape[1] * out_rate / in_rate)), dtype=x.dtype)
        for ch in range(x.shape[0]):
            out[ch] = resample_poly(x[ch], out_rate, in_rate).astype(x.dtype)
        return out
    return resample_poly(x, out_rate, in_rate).astype(x.dtype)
STUBEOF

cd ..

echo -e "${YELLOW}[6/7] 验证关键依赖...${NC}"
cd backend
python -c "import numpy; print(f'  numpy {numpy.__version__} OK')" 2>/dev/null || echo -e "${RED}  numpy 未安装！${NC}"
python -c "import scipy; print(f'  scipy {scipy.__version__} OK')" 2>/dev/null || echo -e "${RED}  scipy 未安装！${NC}"
python -c "import pydantic; print(f'  pydantic {pydantic.__version__} OK')" 2>/dev/null || echo -e "${RED}  pydantic 未安装！${NC}"
python -c "import fastapi; print(f'  fastapi {fastapi.__version__} OK')" 2>/dev/null || echo -e "${RED}  fastapi 未安装！${NC}"
python -c "import soxr; print(f'  soxr (stub) OK')" 2>/dev/null || echo -e "${RED}  soxr stub 未创建！${NC}"
python -c "import librosa; print(f'  librosa {librosa.__version__} OK')" 2>/dev/null || echo -e "${RED}  librosa 未安装！${NC}"
cd ..

echo -e "${YELLOW}[7/7] 生成启动脚本 start_android.sh...${NC}"
cat > start_android.sh << 'STARTEOF'
#!/data/data/com.termux/files/usr/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/backend"

export SERVE_STATIC=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OMP_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Sono - AI Audio Repair (Android/Termux)   ║"
echo "║   http://localhost:8000                      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "请在手机浏览器中访问 http://localhost:8000"
echo "按 Ctrl+C 或关闭 Termux 可停止服务。"
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
echo ""

read -p "是否现在启动服务？(y/n, 默认n): " start_now
start_now=${start_now:-n}
if [ "$start_now" = "y" ] || [ "$start_now" = "Y" ]; then
    ./start_android.sh
fi
