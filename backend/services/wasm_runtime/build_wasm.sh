#!/bin/bash
# 构建 WASM DSP 模块
# 需要安装 clang 和 wasm-ld (LLVM)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLES_DIR="$SCRIPT_DIR/examples"
OUTPUT_DIR="$SCRIPT_DIR/modules"

mkdir -p "$OUTPUT_DIR"

echo "构建 WASM DSP 示例模块..."

if command -v clang &> /dev/null; then
  echo "使用 clang 构建..."
  
  clang \
    --target=wasm32 \
    -O3 \
    -nostdlib \
    -Wl,--no-entry \
    -Wl,--export-all \
    -Wl,--allow-undefined \
    -Wl,--initial-memory=655360 \
    -o "$OUTPUT_DIR/dsp_example.wasm" \
    "$EXAMPLES_DIR/dsp_example.c"
  
  echo "构建完成: $OUTPUT_DIR/dsp_example.wasm"
  ls -lh "$OUTPUT_DIR/dsp_example.wasm"
  
else
  echo "警告: clang 未安装，无法构建 WASM 模块"
  echo "请安装 LLVM/Clang 后重试: apt install clang lld"
  echo "或者使用预编译的 WASM 模块"
fi
