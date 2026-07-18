import { uploadAudio, uploadDualAudio, checkFileHash } from './api/upload';
import { pollProgress, connectProgressWS } from './api/repair';
import { connectCacheWS } from './api/cache';

if (import.meta.env.DEV) {
  (window as any).__testUpload = {
    uploadAudio,
    uploadDualAudio,
    checkFileHash,
    pollProgress,
    connectProgressWS,
    connectCacheWS,
  };
  console.log('[DevTools] 上传测试工具已挂载到 window.__testUpload');
}

export {};
