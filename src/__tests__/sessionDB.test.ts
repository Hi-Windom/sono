import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import 'fake-indexeddb/auto';

import { saveSession, loadSession, clearSession, saveAnalysisCache, getAnalysisCache } from '../utils/sessionDB';

describe('sessionDB', () => {
  beforeEach(async () => {
    await clearSession();
  });

  afterEach(async () => {
    await clearSession();
  });

  function makeMockFile(name = 'test.mp3', size = 1024): File {
    const arr = new Uint8Array(size);
    arr[0] = 0x49; arr[1] = 0x44; arr[2] = 0x33;
    return new File([arr], name, { type: 'audio/mpeg' });
  }

  it('saveSession + loadSession 往返正确', async () => {
    const file = makeMockFile();
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'abc123',
      taskId: 'task-001',
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
    expect(loaded!.fileName).toBe('test.mp3');
    expect(loaded!.fileHash).toBe('abc123');
    expect(loaded!.taskId).toBe('task-001');
    expect(loaded!.backendAvailable).toBe(true);
    expect(loaded!.hasBeenProcessed).toBe(false);
    expect(loaded!.file).toBeInstanceOf(File);
  });

  it('loadSession 在无数据时返回 null', async () => {
    const loaded = await loadSession();
    expect(loaded).toBeNull();
  });

  it('clearSession 清除已保存的会话', async () => {
    const file = makeMockFile();
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'hash',
      taskId: 'task-001',
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo: '{"sampleRate":44100}',
      repairResult: '{"issues_found":[]}',
      originalDetectTime: '2024-01-01',
      repairedDetectTime: '2024-01-02',
      processingOptions: '{"sampleRate":48000,"bitDepth":24}',
    });

    await clearSession();

    const loaded = await loadSession();
    expect(loaded).toBeNull();
  });

  it('saveSession 覆盖已有会话（同 key "current"）', async () => {
    const file1 = makeMockFile('first.mp3', 100);
    await saveSession({
      file: file1,
      fileName: file1.name,
      fileSize: file1.size,
      fileHash: 'hash1',
      taskId: 'task-001',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '',
    });

    const file2 = makeMockFile('second.wav', 200);
    await saveSession({
      file: file2,
      fileName: file2.name,
      fileSize: file2.size,
      fileHash: 'hash2',
      taskId: 'task-002',
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo: '{"sampleRate":96000}',
      repairResult: '{}',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '{"sampleRate":96000,"bitDepth":32}',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.fileName).toBe('second.wav');
    expect(loaded!.taskId).toBe('task-002');
    expect(loaded!.hasBeenProcessed).toBe(true);
  });

  it('保存并恢复完整修复后的会话数据', async () => {
    const file = makeMockFile('song.flac', 5242880);
    const repairResult = JSON.stringify({
      issues_found: ['clipping', 'noise'],
      output_sample_rate: 96000,
      output_bit_depth: 24,
      duration: 180.5,
      algorithm_version: 'v2.4a',
    });
    const wavInfo = JSON.stringify({ sampleRate: 44100, channels: 2, duration: 180.5, bitDepth: 16 });
    const processingOptions = JSON.stringify({ sampleRate: 48000, bitDepth: 24 });

    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'deadbeef12345678',
      taskId: 'task-full-restore',
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo,
      repairResult,
      originalDetectTime: '2024-06-15T10:30:00Z',
      repairedDetectTime: '2024-06-15T10:35:22Z',
      processingOptions,
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.taskId).toBe('task-full-restore');
    expect(loaded!.hasBeenProcessed).toBe(true);

    const parsedRepair = JSON.parse(loaded!.repairResult);
    expect(parsedRepair.issues_found).toEqual(['clipping', 'noise']);
    expect(parsedRepair.output_sample_rate).toBe(96000);
    expect(parsedRepair.algorithm_version).toBe('v2.4a');

    const parsedWav = JSON.parse(loaded!.wavInfo);
    expect(parsedWav.sampleRate).toBe(44100);
    expect(parsedWav.channels).toBe(2);

    const parsedOpts = JSON.parse(loaded!.processingOptions);
    expect(parsedOpts.sampleRate).toBe(48000);
    expect(parsedOpts.bitDepth).toBe(24);

    expect(loaded!.originalDetectTime).toBe('2024-06-15T10:30:00Z');
    expect(loaded!.repairedDetectTime).toBe('2024-06-15T10:35:22Z');

    expect(loaded!.file).toBeInstanceOf(File);
    expect(loaded!.file.size).toBe(5242880);
  });

  it('无效 File 对象也能保存（移动端暂离场景）', async () => {
    const emptyFile = new File([], 'empty.dat', { type: 'application/octet-stream' });
    await saveSession({
      file: emptyFile,
      fileName: 'empty.dat',
      fileSize: 0,
      fileHash: '',
      taskId: 'task-empty',
      backendAvailable: false,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.fileName).toBe('empty.dat');
    expect(loaded!.fileSize).toBe(0);
  });

  it('多次 save/load 不丢失数据', async () => {
    const file = makeMockFile('stable.wav', 4096);
    for (let i = 0; i < 5; i++) {
      await saveSession({
        file,
        fileName: file.name,
        fileSize: file.size,
        fileHash: `hash-${i}`,
        taskId: `task-${i}`,
        backendAvailable: i % 2 === 0,
        hasBeenProcessed: i > 2,
        wavInfo: '',
        repairResult: '',
        originalDetectTime: '',
        repairedDetectTime: '',
        processingOptions: JSON.stringify({ sampleRate: 44100 + i * 975, bitDepth: 16 + i * 4 }),
      });
    }

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.taskId).toBe('task-4');
    expect(loaded!.fileHash).toBe('hash-4');
    expect(loaded!.backendAvailable).toBe(true);
    expect(loaded!.hasBeenProcessed).toBe(true);

    const parsedOpts = JSON.parse(loaded!.processingOptions);
    expect(parsedOpts.sampleRate).toBe(44100 + 4 * 975);
    expect(parsedOpts.bitDepth).toBe(32);
  });

  it('processingOptions 持久化和恢复', async () => {
    const file = makeMockFile('opts-test.wav', 2048);
    const opts = JSON.stringify({ sampleRate: 96000, bitDepth: 32 });
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'opts-hash',
      taskId: 'task-opts',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: opts,
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.processingOptions).toBe(opts);
    const parsed = JSON.parse(loaded!.processingOptions);
    expect(parsed.sampleRate).toBe(96000);
    expect(parsed.bitDepth).toBe(32);
  });

  it('processingOptions 为空字符串时不影响其他字段', async () => {
    const file = makeMockFile('empty-opts.wav', 512);
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'empty-opts-hash',
      taskId: 'task-empty-opts',
      backendAvailable: true,
      hasBeenProcessed: false,
      wavInfo: '{"sampleRate":44100}',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.processingOptions).toBe('');
    expect(loaded!.wavInfo).toBe('{"sampleRate":44100}');
  });

  it('旧版 session 无 processingOptions 字段时 loadSession 不崩溃', async () => {
    const file = makeMockFile('legacy.wav', 1024);
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'legacy-hash',
      taskId: 'task-legacy',
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
    expect(loaded!.taskId).toBe('task-legacy');
    expect(loaded!.processingOptions).toBe('');
  });
});

describe('sessionDB analysis cache', () => {
  beforeEach(async () => {
    const { clearAllAnalysisCache } = await import('../utils/sessionDB');
    await clearAllAnalysisCache();
  });

  it('saveAnalysisCache + getAnalysisCache 往返正确', async () => {
    const wavInfo = JSON.stringify({ sampleRate: 44100, channels: 2, duration: 120, bitDepth: 16 });
    const analysis = JSON.stringify({ spectralFlatness: 0.5, dynamicRange: 40, issues: ['noise'] });

    await saveAnalysisCache({
      fileHash: 'analysis-hash-1',
      fileName: 'test.wav',
      fileSize: 1024,
      wavInfo,
      analysis,
    });

    const cached = await getAnalysisCache('analysis-hash-1');
    expect(cached).not.toBeNull();
    expect(cached!.fileHash).toBe('analysis-hash-1');
    expect(cached!.fileName).toBe('test.wav');

    const parsedWav = JSON.parse(cached!.wavInfo);
    expect(parsedWav.sampleRate).toBe(44100);
    expect(parsedWav.duration).toBe(120);

    const parsedAnalysis = JSON.parse(cached!.analysis);
    expect(parsedAnalysis.spectralFlatness).toBe(0.5);
    expect(parsedAnalysis.issues).toEqual(['noise']);
  });

  it('getAnalysisCache 在无数据时返回 null', async () => {
    const cached = await getAnalysisCache('nonexistent');
    expect(cached).toBeNull();
  });

  it('saveAnalysisCache 覆盖已有缓存', async () => {
    await saveAnalysisCache({
      fileHash: 'overwrite-hash',
      fileName: 'old.wav',
      fileSize: 100,
      wavInfo: '{"sampleRate":44100}',
      analysis: '{"old":true}',
    });

    await saveAnalysisCache({
      fileHash: 'overwrite-hash',
      fileName: 'new.wav',
      fileSize: 200,
      wavInfo: '{"sampleRate":48000}',
      analysis: '{"new":true}',
    });

    const cached = await getAnalysisCache('overwrite-hash');
    expect(cached).not.toBeNull();
    expect(cached!.fileName).toBe('new.wav');
    expect(cached!.fileSize).toBe(200);
  });
});
