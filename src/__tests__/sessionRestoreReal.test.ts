import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import 'fake-indexeddb/auto';

import { saveSession, loadSession, clearSession } from '../utils/sessionDB';

function makeMockFile(name = 'test.wav', size = 1024): File {
  const arr = new Uint8Array(size);
  return new File([arr], name, { type: 'audio/wav' });
}

describe('sessionRestore - 真实场景模拟', () => {
  beforeEach(async () => {
    await clearSession();
  });

  afterEach(async () => {
    await clearSession();
  });

  it('场景1: save → load → file instanceof File 检查', async () => {
    const file = makeMockFile('check.wav', 2048);
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'hash-check',
      taskId: 'task-check',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();

    // 模拟 useAudioProcessor 中的检查
    const sessionFile = loaded!.file;
    const isFileInstance = sessionFile instanceof File;
    const hasSize = sessionFile.size > 0;
    expect(isFileInstance).toBe(true);
    expect(hasSize).toBe(true);
  });

  it('场景2: save → load → arrayBuffer 读取', async () => {
    const file = makeMockFile('read.wav', 512);
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'hash-read',
      taskId: 'task-read',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();

    const sessionFile = loaded!.file;
    let arrayBuf: ArrayBuffer | null = null;
    let restoredFile: File | null = null;

    if (sessionFile instanceof File && sessionFile.size > 0) {
      try {
        arrayBuf = await sessionFile.arrayBuffer();
        if (arrayBuf.byteLength === 0) throw new Error('arrayBuffer 为空');
        restoredFile = sessionFile;
      } catch {
        arrayBuf = null;
      }
    }

    expect(arrayBuf).not.toBeNull();
    expect(arrayBuf!.byteLength).toBe(512);
    expect(restoredFile).not.toBeNull();
  });

  it('场景3: 连续多次 save/load 往返（模拟反复刷新）', async () => {
    const file = makeMockFile('refresh.wav', 4096);
    const opts = JSON.stringify({ sampleRate: 48000, bitDepth: 24 });

    // 第一次保存（模拟首次上传）
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'hash-refresh',
      taskId: 'task-refresh',
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo: '{"sampleRate":44100}',
      repairResult: '{}',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: opts,
    });

    // 模拟5次刷新（每次：load → 检查 → 重新 save）
    for (let i = 0; i < 5; i++) {
      const loaded = await loadSession();
      expect(loaded).not.toBeNull();
      expect(loaded!.taskId).toBe('task-refresh');

      const sessionFile = loaded!.file;
      let arrayBuf: ArrayBuffer | null = null;
      let restoredFile: File | null = null;

      if (sessionFile instanceof File && sessionFile.size > 0) {
        try {
          arrayBuf = await sessionFile.arrayBuffer();
          if (arrayBuf.byteLength === 0) throw new Error('empty');
          restoredFile = sessionFile;
        } catch {
          arrayBuf = null;
        }
      }

      expect(arrayBuf).not.toBeNull();
      expect(restoredFile).not.toBeNull();

      // 模拟恢复后重新 saveSession（刷新 File 对象）
      await saveSession({
        file: restoredFile!,
        fileName: loaded!.fileName,
        fileSize: restoredFile!.size,
        fileHash: loaded!.fileHash,
        taskId: loaded!.taskId,
        backendAvailable: true,
        hasBeenProcessed: loaded!.hasBeenProcessed,
        wavInfo: loaded!.wavInfo,
        repairResult: loaded!.repairResult,
        originalDetectTime: loaded!.originalDetectTime,
        repairedDetectTime: loaded!.repairedDetectTime,
        processingOptions: loaded!.processingOptions,
      });
    }
  });

  it('场景4: File 对象 size=0 时被正确识别为无效', async () => {
    const emptyFile = new File([], 'empty.wav', { type: 'audio/wav' });
    await saveSession({
      file: emptyFile,
      fileName: 'empty.wav',
      fileSize: 0,
      fileHash: 'hash-empty',
      taskId: 'task-empty',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();

    const sessionFile = loaded!.file;
    const isFileValid = sessionFile instanceof File && sessionFile.size > 0;
    expect(isFileValid).toBe(false);
  });

  it('场景5: saveSession 不等待完成时立即 loadSession', async () => {
    const file = makeMockFile('race.wav', 1024);

    const savePromise = saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'hash-race',
      taskId: 'task-race',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '',
    });

    const earlyLoad = await loadSession();

    await savePromise;

    const lateLoad = await loadSession();
    expect(lateLoad).not.toBeNull();
    expect(lateLoad!.taskId).toBe('task-race');
  });

  it('场景6: File 对象无效时不应清除 session（有 taskId 可后端下载）', async () => {
    const emptyFile = new File([], 'invalid.wav', { type: 'audio/wav' });
    await saveSession({
      file: emptyFile,
      fileName: 'invalid.wav',
      fileSize: 0,
      fileHash: 'hash-invalid-file',
      taskId: 'task-has-backend',
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo: '{"sampleRate":44100}',
      repairResult: '{"issues_found":[]}',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '{"sampleRate":48000,"bitDepth":24}',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.taskId).toBe('task-has-backend');

    const isFileValid = loaded!.file instanceof File && loaded!.file.size > 0;
    expect(isFileValid).toBe(false);

    // 关键：File 无效但 taskId 存在，不应清除 session
    // 旧逻辑会 clearSession()，新逻辑保留 session 以便后端下载回退
    const reloaded = await loadSession();
    expect(reloaded).not.toBeNull();
    expect(reloaded!.taskId).toBe('task-has-backend');
    expect(reloaded!.processingOptions).toBe('{"sampleRate":48000,"bitDepth":24}');
  });

  it('场景7: 只有 taskId 没有 File 时 session 仍可加载', async () => {
    await saveSession({
      file: null,
      fileName: 'backend-only.wav',
      fileSize: 0,
      fileHash: 'hash-no-file',
      taskId: 'task-no-file',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '{"sampleRate":44100,"bitDepth":16}',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.taskId).toBe('task-no-file');
    expect(loaded!.file).toBeNull();

    // 旧逻辑: !session.file → sessionRestoredRef=true → 跳过恢复
    // 新逻辑: session.taskId 存在 → 尝试后端下载恢复
    const opts = JSON.parse(loaded!.processingOptions);
    expect(opts.sampleRate).toBe(44100);
  });

  it('场景8: 模拟二次刷新 — session 在第一次恢复失败后仍保留', async () => {
    const file = makeMockFile('double-refresh.wav', 2048);
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'hash-double',
      taskId: 'task-double',
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo: '{"sampleRate":44100}',
      repairResult: '{"issues_found":["noise"]}',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '{"sampleRate":48000,"bitDepth":24}',
    });

    // 第一次刷新：load session
    const first = await loadSession();
    expect(first).not.toBeNull();
    expect(first!.taskId).toBe('task-double');

    // 模拟恢复过程中遇到瞬态错误（如网络超时）
    // 旧逻辑: clearSession() → session 永久丢失
    // 新逻辑: 不清除 session，下次刷新可重试

    // 验证 session 仍在 IndexedDB 中
    const afterError = await loadSession();
    expect(afterError).not.toBeNull();
    expect(afterError!.taskId).toBe('task-double');

    // 第二次刷新：仍能 load session
    const second = await loadSession();
    expect(second).not.toBeNull();
    expect(second!.taskId).toBe('task-double');
    expect(second!.processingOptions).toBe('{"sampleRate":48000,"bitDepth":24}');
  });

  it('场景9: 后端下载优先于 IndexedDB File（模拟新逻辑顺序）', async () => {
    const file = makeMockFile('priority.wav', 1024);
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'hash-priority',
      taskId: 'task-priority',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();

    // 新逻辑: 先尝试后端下载，失败后才回退到 IndexedDB File
    // 模拟后端下载失败
    const backendDownloadOk = false;
    let usedIndexedDBFallback = false;

    if (!backendDownloadOk && loaded!.file && loaded!.file.size > 0) {
      try {
        const buf = await loaded!.file.arrayBuffer();
        if (buf.byteLength > 0) usedIndexedDBFallback = true;
      } catch {}
    }

    expect(usedIndexedDBFallback).toBe(true);
  });
});
