const DB_NAME = 'audio_repair_session';
const DB_VERSION = 3;
const STORE_NAME = 'session';
const ANALYSIS_STORE = 'analysis_cache';

interface SessionData {
  id: string;
  file: File | null;
  fileName: string;
  fileSize: number;
  fileHash: string;
  taskId: string;
  backendAvailable: boolean;
  hasBeenProcessed: boolean;
  wavInfo: string;
  repairResult: string;
  originalDetectTime: string;
  repairedDetectTime: string;
}

export interface AnalysisCacheEntry {
  fileHash: string;
  fileName: string;
  fileSize: number;
  wavInfo: string;
  analysis: string;
  timestamp: number;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = request.result;
      const oldVersion = event.oldVersion;

      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      } else if (oldVersion < 2) {
        const tx = request.transaction;
        if (tx) {
          tx.objectStore(STORE_NAME).clear();
        }
      }
      if (!db.objectStoreNames.contains(ANALYSIS_STORE)) {
        const store = db.createObjectStore(ANALYSIS_STORE, { keyPath: 'fileHash' });
        store.createIndex('timestamp', 'timestamp', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function saveSession(data: Omit<SessionData, 'id'>): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.put({ id: 'current', ...data });
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    console.warn('[sessionDB] saveSession failed');
  }
}

export async function loadSession(): Promise<SessionData | null> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const request = store.get('current');
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  } catch {
    return null;
  }
}

export async function clearSession(): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).delete('current');
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    console.warn('[sessionDB] clearSession failed');
  }
}

// ===== 音频解析缓存 =====

export async function getAnalysisCache(fileHash: string): Promise<AnalysisCacheEntry | null> {
  try {
    const db = await openDB();
    const tx = db.transaction(ANALYSIS_STORE, 'readonly');
    const request = tx.objectStore(ANALYSIS_STORE).get(fileHash);
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  } catch {
    return null;
  }
}

export async function saveAnalysisCache(entry: Omit<AnalysisCacheEntry, 'timestamp'>): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(ANALYSIS_STORE, 'readwrite');
    tx.objectStore(ANALYSIS_STORE).put({ ...entry, timestamp: Date.now() });
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    console.warn('[sessionDB] saveAnalysisCache failed');
  }
}

export async function getAllAnalysisCache(): Promise<AnalysisCacheEntry[]> {
  try {
    const db = await openDB();
    const tx = db.transaction(ANALYSIS_STORE, 'readonly');
    const request = tx.objectStore(ANALYSIS_STORE).getAll();
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  } catch {
    return [];
  }
}

export async function clearAllAnalysisCache(): Promise<number> {
  try {
    const db = await openDB();
    const tx = db.transaction(ANALYSIS_STORE, 'readwrite');
    const store = tx.objectStore(ANALYSIS_STORE);
    const countReq = store.count();
    return new Promise((resolve, reject) => {
      countReq.onsuccess = () => {
        const count = countReq.result;
        store.clear();
        tx.oncomplete = () => resolve(count);
        tx.onerror = () => reject(tx.error);
      };
      countReq.onerror = () => reject(countReq.error);
    });
  } catch {
    return 0;
  }
}

export async function deleteAnalysisCache(fileHash: string): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(ANALYSIS_STORE, 'readwrite');
    tx.objectStore(ANALYSIS_STORE).delete(fileHash);
    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    console.warn('[sessionDB] deleteAnalysisCache failed');
  }
}

export async function getAnalysisCacheCount(): Promise<number> {
  try {
    const db = await openDB();
    const tx = db.transaction(ANALYSIS_STORE, 'readonly');
    const request = tx.objectStore(ANALYSIS_STORE).count();
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } catch {
    return 0;
  }
}
