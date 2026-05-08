const DB_NAME = 'audio_repair_session';
const DB_VERSION = 2;
const STORE_NAME = 'session';

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

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = request.result;
      const oldVersion = event.oldVersion;

      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      } else if (oldVersion < 2) {
        // 版本升级时清除旧数据，确保新字段可用
        const tx = request.transaction;
        if (tx) {
          tx.objectStore(STORE_NAME).clear();
        }
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
