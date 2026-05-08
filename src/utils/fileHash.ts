/**
 * 文件哈希计算工具
 * 使用分块增量计算（前1MB + 后1MB）优化大文件性能
 */

const CHUNK_SIZE = 1024 * 1024; // 1MB

/**
 * 计算文件哈希（分块增量）
 * 对于大文件，只读取前1MB和后1MB，避免读取整个文件
 */
export async function computeFileHash(file: File): Promise<string> {
  const startTime = performance.now();

  let buffer: ArrayBuffer;

  if (file.size <= CHUNK_SIZE * 2) {
    // 小文件：直接读取全部
    buffer = await file.arrayBuffer();
  } else {
    // 大文件：只读取前1MB和后1MB
    const headChunk = file.slice(0, CHUNK_SIZE);
    const tailChunk = file.slice(file.size - CHUNK_SIZE);

    const [headBuf, tailBuf] = await Promise.all([
      headChunk.arrayBuffer(),
      tailChunk.arrayBuffer(),
    ]);

    // 合并前1MB + 文件大小 + 后1MB
    const combined = new Uint8Array(CHUNK_SIZE * 2 + 8);
    combined.set(new Uint8Array(headBuf), 0);
    // 中间插入文件大小（8字节大端序）
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

/**
 * 快速哈希（用于缓存键等不需要强碰撞抵抗的场景）
 * 使用文件大小 + 前4KB + 后4KB的字符串拼接
 */
export async function computeQuickHash(file: File): Promise<string> {
  const startTime = performance.now();

  let prefix: string;

  if (file.size <= 8192) {
    const buf = await file.arrayBuffer();
    prefix = btoa(String.fromCharCode(...new Uint8Array(buf)));
  } else {
    const headChunk = file.slice(0, 4096);
    const tailChunk = file.slice(file.size - 4096);

    const [headBuf, tailBuf] = await Promise.all([
      headChunk.arrayBuffer(),
      tailChunk.arrayBuffer(),
    ]);

    prefix = `${file.size}-${btoa(String.fromCharCode(...new Uint8Array(headBuf)))}-${btoa(String.fromCharCode(...new Uint8Array(tailBuf)))}`;
  }

  const hashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(prefix));
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

  const elapsed = performance.now() - startTime;
  console.log(`[fileHash] 快速哈希: size=${file.size}, hash=${hash.slice(0, 16)}..., time=${elapsed.toFixed(1)}ms`);

  return hash;
}
