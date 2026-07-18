import { API_BASE } from './_shared';
import type { ProgressCallback, DeliveryFilesResponse, DeliveryFile } from './types';

export function getDownloadUrl(taskId: string): string {
  return `${API_BASE}/download/${taskId}`;
}

export function getPreviewUrl(taskId: string, type: 'original' | 'repaired'): string {
  return `${API_BASE}/preview/${taskId}?type=${type}`;
}

export async function downloadWithProgress(url: string, onProgress?: ProgressCallback, maxRetries: number = 3): Promise<ArrayBuffer> {
  let lastError: Error | null = null;
  let savedChunks: Uint8Array[] = [];
  let savedBytes = 0;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const startByte = savedBytes;
      const result = await new Promise<ArrayBuffer>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('GET', url);
        xhr.responseType = 'arraybuffer';

        if (startByte > 0) {
          xhr.setRequestHeader('Range', `bytes=${startByte}-`);
        }

        const startTime = Date.now();
        let lastSpeedLoaded = 0;

        xhr.onprogress = (e) => {
          if (e.lengthComputable && onProgress) {
            const currentLoaded = startByte + e.loaded;
            const total = startByte + e.total;
            const elapsed = (Date.now() - startTime) / 1000;
            const speed = elapsed > 0 ? (e.loaded - lastSpeedLoaded) / elapsed : 0;
            lastSpeedLoaded = e.loaded;
            onProgress(currentLoaded, total, speed);
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            savedChunks = [];
            savedBytes = 0;
            resolve(xhr.response);
          } else if (xhr.status === 206) {
            resolve(xhr.response);
          } else {
            reject(new Error(`下载失败 (HTTP ${xhr.status})`));
          }
        };

        xhr.onerror = () => {
          reject(new Error('下载网络错误'));
        };

        xhr.ontimeout = () => {
          reject(new Error('下载超时'));
        };

        xhr.timeout = 60000;
        xhr.send();
      });

      if (savedChunks.length > 0) {
        const newData = new Uint8Array(result);
        savedChunks.push(newData);
        const totalLen = savedChunks.reduce((s, c) => s + c.length, 0);
        const combined = new Uint8Array(totalLen);
        let off = 0;
        for (const chunk of savedChunks) {
          combined.set(chunk, off);
          off += chunk.length;
        }
        savedChunks = [];
        savedBytes = 0;
        return combined.buffer;
      }

      return result;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));

      if (attempt < maxRetries - 1) {
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
      }
    }
  }

  throw lastError || new Error('下载失败');
}

export function parseFilenameFromDisposition(disposition: string | null): string | null {
  if (!disposition) return null;
  const utf8 = disposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i);
  if (utf8?.[1]) return decodeURIComponent(utf8[1]);
  const plain = disposition.match(/filename=["']?([^"';\n]+)["']?/i);
  if (plain?.[1]) return plain[1].trim();
  return null;
}

export async function fetchDeliveryFiles(): Promise<DeliveryFilesResponse> {
  const res = await fetch(`${API_BASE}/delivery-files`);
  if (!res.ok) throw new Error('获取交付文件列表失败');
  return res.json();
}

export async function deleteDeliveryFile(filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}/delivery-files/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || '删除交付文件失败');
  }
}

export async function deleteDeliveryParent(filename: string): Promise<{deleted: string[]}> {
  const res = await fetch(`${API_BASE}/delivery-files/parent/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || '删除交付文件组失败');
  }
  return res.json();
}
