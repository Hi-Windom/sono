import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import 'fake-indexeddb/auto';

import { saveSession, loadSession, clearSession } from '../utils/sessionDB';

describe('sessionDB', () => {
  beforeEach(async () => {
    await clearSession();
  });

  afterEach(async () => {
    await clearSession();
  });

  function makeMockFile(name = 'test.mp3', size = 1024): File {
    const arr = new Uint8Array(size);
    arr[0] = 0x49; arr[1] = 0x44; arr[2] = 0x33; // fake ID3 header
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
      });
    }

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.taskId).toBe('task-4');
    expect(loaded!.fileHash).toBe('hash-4');
    expect(loaded!.backendAvailable).toBe(true);
    expect(loaded!.hasBeenProcessed).toBe(true);
  });
});
