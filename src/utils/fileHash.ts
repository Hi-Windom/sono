/**
 * 文件哈希计算工具
 * 使用分块增量计算（前1MB + 后1MB）优化大文件性能
 */

const CHUNK_SIZE = 1024 * 1024;

export async function computeFileHash(file: File): Promise<string> {
  const startTime = performance.now();

  let buffer: ArrayBuffer;

  if (file.size <= CHUNK_SIZE * 2) {
    buffer = await file.arrayBuffer();
  } else {
    const headChunk = file.slice(0, CHUNK_SIZE);
    const tailChunk = file.slice(file.size - CHUNK_SIZE);

    const [headBuf, tailBuf] = await Promise.all([
      headChunk.arrayBuffer(),
      tailChunk.arrayBuffer(),
    ]);

    const combined = new Uint8Array(CHUNK_SIZE * 2 + 8);
    combined.set(new Uint8Array(headBuf), 0);
    const sizeView = new DataView(combined.buffer, CHUNK_SIZE, 8);
    sizeView.setBigUint64(0, BigInt(file.size), false);
    combined.set(new Uint8Array(tailBuf), CHUNK_SIZE + 8);

    buffer = combined.buffer;
  }

  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

  const elapsed = performance.now() - startTime;
  console.log(`[fileHash] 计算完成: size=${file.size}, hash=${hash.slice(0, 16)}..., time=${elapsed.toFixed(1)}ms`);

  return hash;
}
