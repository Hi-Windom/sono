#!/bin/bash
# 构建 WASM DSP 核心模块
# 需要安装 clang 和 wasm-ld (LLVM)
#
# 用法:
#   bash build_wasm.sh          # 构建所有模块
#   bash build_wasm.sh clean    # 清理构建产物

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLES_DIR="$SCRIPT_DIR/examples"
OUTPUT_DIR="$SCRIPT_DIR/modules"

mkdir -p "$OUTPUT_DIR"

if [ "$1" = "clean" ]; then
  echo "清理构建产物..."
  rm -f "$OUTPUT_DIR"/*.wasm
  echo "完成"
  exit 0
fi

echo "=== 构建 WASM DSP 模块 ==="
echo

if ! command -v clang &> /dev/null; then
  echo "错误: clang 未安装"
  echo "请安装 LLVM/Clang: apt install clang lld"
  exit 1
fi

CFLAGS=(
  --target=wasm32
  -O3
  -nostdlib
  -Wl,--no-entry
  -Wl,--export-all
  -Wl,--allow-undefined
  -Wl,--initial-memory=8388608
  -Wno-unused-function
  -Wall
)

build_module() {
  local name="$1"
  local src="$2"
  local out="$OUTPUT_DIR/${name}.wasm"
  
  echo "构建 $name..."
  clang "${CFLAGS[@]}" -o "$out" "$src"
  
  local size=$(stat -c%s "$out" 2>/dev/null || stat -f%z "$out" 2>/dev/null || echo "?")
  echo "  ✓ $out ($size bytes)"
}

echo "使用 clang: $(clang --version | head -1)"
echo "输出目录: $OUTPUT_DIR"
echo

# 构建核心 DSP 模块
if [ -f "$EXAMPLES_DIR/dsp_core.c" ]; then
  build_module "dsp_core" "$EXAMPLES_DIR/dsp_core.c"
fi

echo
echo "=== 构建完成 ==="
ls -lh "$OUTPUT_DIR"/*.wasm 2>/dev/null || echo "无产物"
