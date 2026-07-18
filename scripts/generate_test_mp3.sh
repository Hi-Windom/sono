#!/usr/bin/env bash
# 生成测试用的10MB MP3文件
# 使用 ffmpeg 生成指定时长、采样率的正弦波MP3

set -e

OUTPUT_DIR="${1:-public}"
OUTPUT_FILE="$OUTPUT_DIR/test_10mb.mp3"
TARGET_SIZE_MB=10

mkdir -p "$OUTPUT_DIR"

if command -v ffmpeg &> /dev/null; then
  echo "使用 ffmpeg 生成测试音频..."
  
  # 先生成一个足够长的WAV，再转MP3
  # 对于10MB的MP3，大约需要6-8分钟的音频（128kbps）
  DURATION_SECONDS=420
  
  ffmpeg -y \
    -f lavfi \
    -i "sine=frequency=440:duration=$DURATION_SECONDS:sample_rate=44100" \
    -ac 2 \
    -codec:a libmp3lame \
    -b:a 192k \
    "$OUTPUT_FILE" 2>&1 | tail -5
  
  ACTUAL_SIZE=$(stat -c%s "$OUTPUT_FILE" 2>/dev/null || stat -f%z "$OUTPUT_FILE" 2>/dev/null)
  ACTUAL_SIZE_MB=$(echo "scale=2; $ACTUAL_SIZE / 1024 / 1024" | bc)
  echo "生成完成: $OUTPUT_FILE ($ACTUAL_SIZE_MB MB)"
  
else
  echo "ffmpeg 未安装，使用 Python 生成占位测试文件..."
  python3 -c "
import struct
import os

target_size = 10 * 1024 * 1024  # 10MB
output = '$OUTPUT_FILE'

# 生成一个有效的MP3文件头 + 填充数据
# MP3帧头: 11位同步字 + MPEG1 Layer3 + 128kbps + 44100Hz + 立体声
frame_header = struct.pack('>I', 0xFFFB9000)
frame_size = 417  # 128kbps, 44100Hz的帧大小约为417字节

with open(output, 'wb') as f:
    # 写ID3v2头（简化版）
    f.write(b'ID3')
    f.write(b'\\x03\\x00')  # version 3.0
    f.write(b'\\x00')  # flags
    f.write(b'\\x00\\x00\\x00\\x00')  # size (0 = no tags)
    
    # 写入足够的MP3帧达到目标大小
    written = 10
    frame_data = frame_header + b'\\x00' * (frame_size - 4)
    while written < target_size:
        f.write(frame_data)
        written += frame_size

size_mb = os.path.getsize(output) / 1024 / 1024
print(f'生成完成: {output} ({size_mb:.2f} MB)')
"
fi

echo "测试文件已生成: $OUTPUT_FILE"
ls -lh "$OUTPUT_FILE"
