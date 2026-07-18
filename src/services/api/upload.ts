import { API_BASE, CHUNK_SIZE, log } from './_shared';
import type { UploadResponse, DualUploadResponse, ProgressCallback } from './types';

export async function checkFileHash(fileHash: string): Promise<{ exists: boolean; task_id?: string; filename?: string }> {
  const url = `${API_BASE}/check-hash`;
  log('check-hash', `POST ${url} hash=${fileHash}`);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_hash: fileHash }),
    });
    if (!res.ok) return { exists: false };
    const data = await res.json();
    log('check-hash', `result: exists=${data.exists} task_id=${data.task_id || 'none'}`);
    return data;
  } catch {
    log('check-hash', 'FAILED');
    return { exists: false };
  }
}

async function uploadFileSimple(
  file: File,
  endpoint: string,
  extraFields: Record<string, string> | undefined,
  onProgress?: ProgressCallback
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (extraFields) {
    Object.entries(extraFields).forEach(([key, value]) => {
      if (value) formData.append(key, value);
    });
  }

  return new Promise<UploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', endpoint);
    xhr.timeout = 300000;

    const startTime = Date.now();
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        const elapsed = (Date.now() - startTime) / 1000;
        const speed = elapsed > 0 ? e.loaded / elapsed : 0;
        onProgress(e.loaded, e.total, speed);
      }
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.detail || data.message || '上传失败'));
        }
      } catch {
        reject(new Error('上传响应解析失败'));
      }
    };

    xhr.onerror = () => reject(new Error('上传失败'));
    xhr.ontimeout = () => reject(new Error('上传超时(300s)'));
    xhr.send(formData);
  });
}

async function uploadFileChunked(
  file: File,
  endpoint: string,
  extraFields: Record<string, string> | undefined,
  onProgress?: ProgressCallback
): Promise<UploadResponse> {
  const fileName = file.name;
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  const fileHash = extraFields?.file_hash;

  log('upload', `Starting chunked upload: ${totalChunks} chunks, ${file.size} bytes`);

  const initFormData = new FormData();
  initFormData.append('filename', fileName);
  initFormData.append('total_size', String(file.size));
  initFormData.append('total_chunks', String(totalChunks));
  if (fileHash) initFormData.append('file_hash', fileHash);

  let sessionId: string;
  try {
    const initResp = await fetch(`${API_BASE}/upload-init`, { method: 'POST', body: initFormData });
    if (!initResp.ok) throw new Error(`初始化失败: ${initResp.statusText}`);
    const initData = await initResp.json();
    sessionId = initData.session_id;
  } catch (error) {
    log('upload', `Init failed, falling back to simple upload: ${(error as Error).message}`);
    return uploadFileSimple(file, endpoint, extraFields, onProgress);
  }

  const uploadedChunks = new Set<number>();
  let successfulChunks = 0;
  let uploadedBytes = 0;

  try {
    const checkResp = await fetch(`${API_BASE}/upload-status?session_id=${sessionId}`);
    if (checkResp.ok) {
      const checkData = await checkResp.json();
      (checkData.uploaded_chunks || []).forEach((i: number) => uploadedChunks.add(i));
      successfulChunks = uploadedChunks.size;
      uploadedBytes = successfulChunks * CHUNK_SIZE;
      if (onProgress && file.size > 0) {
        const clamped = Math.min(uploadedBytes, file.size);
        onProgress(clamped, file.size, 0);
      }
    }
  } catch { /* ignore */ }

  const startTime = Date.now();

  for (let i = 0; i < totalChunks; i++) {
    if (uploadedChunks.has(i)) continue;

    const start = i * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, file.size);
    const chunk = file.slice(start, end);

    let retrySuccess = false;
    for (let retry = 0; retry < 3; retry++) {
      try {
        if (retry > 0) {
          await new Promise(r => setTimeout(r, 500 * retry));
        }
        const result = await uploadChunkWithProgress(
          `${API_BASE}/upload-chunk`,
          sessionId,
          i,
          chunk,
          (chunkLoaded, chunkTotal) => {
            if (!onProgress) return;
            const totalLoaded = uploadedBytes + chunkLoaded;
            const elapsed = (Date.now() - startTime) / 1000;
            const speed = elapsed > 0 ? totalLoaded / elapsed : 0;
            const clamped = Math.min(totalLoaded, file.size);
            onProgress(clamped, file.size, speed);
          }
        );
        if (result) {
          uploadedChunks.add(i);
          successfulChunks++;
          uploadedBytes = Math.min(successfulChunks * CHUNK_SIZE, file.size);
          retrySuccess = true;
          break;
        }
      } catch { /* retry */ }
    }

    if (!retrySuccess) {
      await fetch(`${API_BASE}/upload-cancel?session_id=${sessionId}`, { method: 'POST' }).catch(() => {});
      throw new Error(`分片 ${i} 上传失败，已重试3次`);
    }
  }

  const finalizeFormData = new FormData();
  finalizeFormData.append('session_id', sessionId);

  const finalizeResp = await fetch(`${API_BASE}/upload-finalize`, { method: 'POST', body: finalizeFormData });
  if (!finalizeResp.ok) {
    throw new Error(`合并文件失败: ${finalizeResp.statusText}`);
  }

  const finalizeData = await finalizeResp.json();
  if (!finalizeData.success) throw new Error(finalizeData.error || '合并文件失败');

  return {
    task_id: finalizeData.task_id,
    filename: fileName,
    size: file.size,
    message: '上传完成',
  };
}

function uploadChunkWithProgress(
  url: string,
  sessionId: string,
  chunkIndex: number,
  chunk: Blob,
  onProgress?: (loaded: number, total: number) => void
): Promise<boolean> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.timeout = 120000;

    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('chunk_index', String(chunkIndex));
    formData.append('chunk', chunk);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded, e.total);
      }
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300 && data.success) {
          resolve(true);
        } else {
          reject(new Error(data.error || '分片上传失败'));
        }
      } catch {
        reject(new Error('分片上传响应解析失败'));
      }
    };

    xhr.onerror = () => reject(new Error('分片上传网络错误'));
    xhr.ontimeout = () => reject(new Error('分片上传超时(120s)'));
    xhr.send(formData);
  });
}

async function uploadFileCore(
  file: File,
  endpoint: string,
  extraFields?: Record<string, string>,
  onProgress?: ProgressCallback
): Promise<UploadResponse> {
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  const useChunked = totalChunks > 1;

  if (!useChunked) {
    return uploadFileSimple(file, endpoint, extraFields, onProgress);
  }
  return uploadFileChunked(file, endpoint, extraFields, onProgress);
}

export async function uploadAudio(file: File, onProgress?: ProgressCallback, fileHash?: string): Promise<UploadResponse> {
  if (fileHash) {
    const checkResult = await checkFileHash(fileHash);
    if (checkResult.exists && checkResult.task_id) {
      log('upload', `CACHE HIT hash=${fileHash} task_id=${checkResult.task_id}`);
      return {
        task_id: checkResult.task_id,
        filename: checkResult.filename || file.name,
        size: file.size,
        message: '文件已缓存，跳过上传',
        cached: true,
      };
    }
  }

  const url = `${API_BASE}/upload`;
  log('upload', `POST ${url} file=${file.name} size=${file.size} hash=${fileHash || 'none'}`);

  return uploadFileCore(file, url, fileHash ? { file_hash: fileHash } : undefined, onProgress);
}

export async function uploadDualAudio(
  vocalFile: File,
  accompanimentFile: File,
  onProgress?: (loaded: number, total: number, speed: number, type: 'vocal' | 'accompaniment') => void,
  fileHash?: string,
  vocalFileHash?: string,
  accompanimentFileHash?: string
): Promise<DualUploadResponse> {
  const totalSize = vocalFile.size + accompanimentFile.size;
  let vocalLoaded = 0;
  let accLoaded = 0;
  const startTime = Date.now();

  const vocalResult = await uploadFileCore(
    vocalFile,
    `${API_BASE}/upload`,
    vocalFileHash ? { file_hash: vocalFileHash } : undefined,
    onProgress ? (loaded, total, speed) => {
      vocalLoaded = loaded;
      const totalLoaded = vocalLoaded + accLoaded;
      const elapsed = (Date.now() - startTime) / 1000;
      const avgSpeed = elapsed > 0 ? totalLoaded / elapsed : 0;
      onProgress(totalLoaded, totalSize, avgSpeed, 'vocal');
    } : undefined
  );
  vocalLoaded = vocalFile.size;

  const accResult = await uploadFileCore(
    accompanimentFile,
    `${API_BASE}/upload`,
    accompanimentFileHash ? { file_hash: accompanimentFileHash } : undefined,
    onProgress ? (loaded, total, speed) => {
      accLoaded = loaded;
      const totalLoaded = vocalLoaded + accLoaded;
      const elapsed = (Date.now() - startTime) / 1000;
      const avgSpeed = elapsed > 0 ? totalLoaded / elapsed : 0;
      onProgress(totalLoaded, totalSize, avgSpeed, 'accompaniment');
    } : undefined
  );

  log('upload-dual', `Dual upload complete: vocal=${vocalResult.task_id}, acc=${accResult.task_id}`);

  return {
    task_id: vocalResult.task_id,
    vocal_task_id: vocalResult.task_id,
    accompaniment_task_id: accResult.task_id,
    vocal_filename: vocalFile.name,
    accompaniment_filename: accompanimentFile.name,
    vocal_size: vocalFile.size,
    accompaniment_size: accompanimentFile.size,
    message: '双轨上传完成',
  };
}

export async function checkTrainingHash(fileHash: string): Promise<{ exists: boolean; filename?: string; size?: number }> {
  const url = `${API_BASE}/training/check-hash`;
  log('training-check-hash', `POST ${url} hash=${fileHash}`);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_hash: fileHash }),
    });
    if (!res.ok) return { exists: false };
    const data = await res.json();
    log('training-check-hash', `result: exists=${data.exists}`);
    return data;
  } catch {
    log('training-check-hash', 'FAILED');
    return { exists: false };
  }
}

async function uploadTrainingSimple(
  file: File,
  url: string,
  fileHash: string | undefined,
  onProgress: ((loaded: number, total: number) => void) | undefined
): Promise<{ filename: string; size: number; message: string; cached?: boolean }> {
  const formData = new FormData();
  formData.append('file', file);
  if (fileHash) formData.append('file_hash', fileHash);
  formData.append('label', 'ai_generated');

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.timeout = 300000;

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded, e.total);
      }
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve({
            filename: data.filename || file.name,
            size: data.size || file.size,
            message: '上传完成',
          });
        } else {
          reject(new Error(data.detail || '上传失败'));
        }
      } catch {
        reject(new Error('上传响应解析失败'));
      }
    };

    xhr.onerror = () => reject(new Error('上传失败'));
    xhr.ontimeout = () => reject(new Error('上传超时(300s)'));
    xhr.send(formData);
  });
}

async function uploadTrainingChunked(
  file: File,
  url: string,
  fileHash: string | undefined,
  onProgress: ((loaded: number, total: number) => void) | undefined
): Promise<{ filename: string; size: number; message: string; cached?: boolean }> {
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  let sessionId: string;

  const initFormData = new FormData();
  initFormData.append('filename', file.name);
  initFormData.append('total_size', String(file.size));
  initFormData.append('total_chunks', String(totalChunks));
  if (fileHash) initFormData.append('file_hash', fileHash);
  initFormData.append('label', 'ai_generated');

  try {
    const initResp = await fetch(`${API_BASE}/training/upload-init`, {
      method: 'POST',
      body: initFormData,
    });
    if (!initResp.ok) throw new Error(`初始化失败: ${initResp.statusText}`);
    const initData = await initResp.json();
    sessionId = initData.session_id;
  } catch (error) {
    log('trainingUpload', `Init failed, falling back to simple upload: ${(error as Error).message}`);
    return uploadTrainingSimple(file, url, fileHash, onProgress);
  }

  const uploadedChunks = new Set<number>();
  let successfulChunks = 0;

  try {
    const checkResp = await fetch(`${API_BASE}/upload-status?session_id=${sessionId}`);
    if (checkResp.ok) {
      const checkData = await checkResp.json();
      (checkData.uploaded_chunks || []).forEach((i: number) => uploadedChunks.add(i));
      successfulChunks = uploadedChunks.size;
    }
  } catch { /* ignore */ }

  for (let i = 0; i < totalChunks; i++) {
    if (uploadedChunks.has(i)) continue;

    const start = i * CHUNK_SIZE;
    const end = Math.min(start + CHUNK_SIZE, file.size);
    const chunk = file.slice(start, end);

    const chunkFormData = new FormData();
    chunkFormData.append('session_id', sessionId);
    chunkFormData.append('chunk_index', String(i));
    chunkFormData.append('chunk', chunk);

    let retrySuccess = false;
    for (let retry = 0; retry < 3; retry++) {
      try {
        await new Promise(r => setTimeout(r, 1000 * retry));
        const resp = await fetch(`${API_BASE}/upload-chunk`, { method: 'POST', body: chunkFormData });
        if (resp.ok) {
          const data = await resp.json();
          if (data.success) {
            uploadedChunks.add(i);
            successfulChunks++;
            retrySuccess = true;
            if (onProgress) onProgress(file.size * (successfulChunks / totalChunks), file.size);
            break;
          }
        }
      } catch { /* retry */ }
    }

    if (!retrySuccess) {
      await fetch(`${API_BASE}/upload-cancel?session_id=${sessionId}`, { method: 'POST' }).catch(() => {});
      throw new Error(`分片 ${i} 上传失败，已重试3次`);
    }
  }

  const finalizeFormData = new FormData();
  finalizeFormData.append('session_id', sessionId);

  const finalizeResp = await fetch(`${API_BASE}/training/upload-finalize`, {
    method: 'POST',
    body: finalizeFormData,
  });

  if (!finalizeResp.ok) throw new Error(`合并文件失败: ${finalizeResp.statusText}`);

  const finalizeData = await finalizeResp.json();
  if (finalizeData.status !== 'ok') throw new Error(finalizeData.detail || '合并文件失败');

  return {
    filename: file.name,
    size: finalizeData.size || file.size,
    message: '上传完成',
  };
}

export async function uploadTrainingAudio(
  file: File,
  onProgress?: (loaded: number, total: number, speed?: number) => void,
  fileHash?: string
): Promise<{ filename: string; size: number; message: string; cached?: boolean }> {
  const url = `${API_BASE}/training/upload`;
  
  if (fileHash) {
    const checkResult = await checkTrainingHash(fileHash);
    if (checkResult.exists) {
      log('trainingUpload', `CACHE HIT hash=${fileHash} filename=${checkResult.filename}`);
      return {
        filename: checkResult.filename || file.name,
        size: checkResult.size || file.size,
        message: '文件已缓存，跳过上传',
        cached: true,
      };
    }
  }
  
  log('trainingUpload', `POST ${url} file=${file.name} size=${file.size} hash=${fileHash || 'none'}`);

  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  const useChunked = totalChunks > 1;

  if (!useChunked) {
    return uploadTrainingSimple(file, url, fileHash, onProgress);
  }

  return uploadTrainingChunked(file, url, fileHash, onProgress);
}
