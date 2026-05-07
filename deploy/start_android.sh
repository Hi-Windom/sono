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
