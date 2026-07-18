/**
 * 文件哈希计算工具
 * 使用分块增量计算（前1MB + 后1MB）优化大文件性能
 */

const CHUNK_SIZE = 1024 * 1024;

function fnv1aHash(data: Uint8Array, extraSeed = 0): number {
  let hash = 0x811c9dc5 ^ extraSeed;
  for (let i = 0; i < data.length; i++) {
    hash ^= data[i];
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function fallbackHash(buffer: ArrayBuffer, fileSize: number, fileName: string): string {
  const data = new Uint8Array(buffer);
  const h1 = fnv1aHash(data, 0);
  const h2 = fnv1aHash(data, h1);

  let nameHash = 0;
  for (let i = 0; i < fileName.length; i++) {
    nameHash = Math.imul(nameHash ^ fileName.charCodeAt(i), 0x01000193);
  }
  nameHash = nameHash >>> 0;

  const combined = new DataView(new ArrayBuffer(16));
  combined.setUint32(0, h1, false);
  combined.setUint32(4, h2, false);
  combined.setUint32(8, nameHash, false);
  combined.setBigUint64(8, BigInt(fileSize), false);

  let hex = '';
  for (let i = 0; i < 16; i++) {
    hex += combined.getUint8(i).toString(16).padStart(2, '0');
  }
  return hex + hex;
}

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

  let hash: string;
  let hashMethod: string;

  if (typeof crypto !== 'undefined' && crypto.subtle && crypto.subtle.digest) {
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    hash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    hashMethod = 'SHA-256';
  } else {
    hash = fallbackHash(buffer, file.size, file.name);
    hashMethod = 'FNV1a-fallback';
  }

  const elapsed = performance.now() - startTime;
  console.log(`[fileHash] 计算完成: size=${file.size}, method=${hashMethod}, hash=${hash.slice(0, 16)}..., time=${elapsed.toFixed(1)}ms`);

  return hash;
}
