import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import 'fake-indexeddb/auto';

import { saveSession, loadSession, clearSession } from '../utils/sessionDB';

interface PendingSession {
  file: File;
  fileName: string;
  fileHash: string;
  taskId: string;
  hasBeenProcessed: boolean;
  wavInfo?: string;
  repairResult?: string;
  processingOptions?: string;
}

function buildPendingSession(sessionData: {
  file: File;
  fileName: string;
  fileHash: string;
  taskId: string;
  hasBeenProcessed: boolean;
  wavInfo: string;
  repairResult: string;
  processingOptions: string;
}): PendingSession {
  return {
    file: sessionData.file,
    fileName: sessionData.fileName,
    fileHash: sessionData.fileHash,
    taskId: sessionData.taskId,
    hasBeenProcessed: sessionData.hasBeenProcessed,
    wavInfo: sessionData.wavInfo || undefined,
    repairResult: sessionData.repairResult || undefined,
    processingOptions: sessionData.processingOptions || undefined,
  };
}

function parseProcessingOptions(optsStr: string | undefined): { sampleRate: number; bitDepth: number } | null {
  if (!optsStr) return null;
  try {
    const opts = JSON.parse(optsStr);
    if (opts.sampleRate && opts.bitDepth) return opts;
  } catch {}
  return null;
}

function parseRepairResult(resultStr: string | undefined): Record<string, unknown> | null {
  if (!resultStr) return null;
  try {
    return JSON.parse(resultStr);
  } catch {}
  return null;
}

describe('sessionRestore - pendingSessionRef 构建', () => {
  function makeMockFile(name = 'test.wav', size = 1024): File {
    const arr = new Uint8Array(size);
    return new File([arr], name, { type: 'audio/wav' });
  }

  it('buildPendingSession 正确传递所有字段', () => {
    const file = makeMockFile();
    const pending = buildPendingSession({
      file,
      fileName: file.name,
      fileHash: 'hash1',
      taskId: 'task-1',
      hasBeenProcessed: true,
      wavInfo: '{"sampleRate":44100}',
      repairResult: '{"issues_found":["noise"]}',
      processingOptions: '{"sampleRate":48000,"bitDepth":24}',
    });

    expect(pending.file).toBe(file);
    expect(pending.fileName).toBe(file.name);
    expect(pending.fileHash).toBe('hash1');
    expect(pending.taskId).toBe('task-1');
    expect(pending.hasBeenProcessed).toBe(true);
    expect(pending.wavInfo).toBe('{"sampleRate":44100}');
    expect(pending.repairResult).toBe('{"issues_found":["noise"]}');
    expect(pending.processingOptions).toBe('{"sampleRate":48000,"bitDepth":24}');
  });

  it('buildPendingSession 空字符串字段转为 undefined', () => {
    const file = makeMockFile();
    const pending = buildPendingSession({
      file,
      fileName: file.name,
      fileHash: 'hash2',
      taskId: 'task-2',
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      processingOptions: '',
    });

    expect(pending.wavInfo).toBeUndefined();
    expect(pending.repairResult).toBeUndefined();
    expect(pending.processingOptions).toBeUndefined();
  });

  it('buildPendingSession processingOptions 缺失时为 undefined', () => {
    const file = makeMockFile();
    const pending = buildPendingSession({
      file,
      fileName: file.name,
      fileHash: 'hash3',
      taskId: 'task-3',
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      processingOptions: '',
    });

    expect(pending.processingOptions).toBeUndefined();
  });
});

describe('sessionRestore - processingOptions 解析', () => {
  it('有效 processingOptions 正确解析', () => {
    const result = parseProcessingOptions('{"sampleRate":48000,"bitDepth":24}');
    expect(result).not.toBeNull();
    expect(result!.sampleRate).toBe(48000);
    expect(result!.bitDepth).toBe(24);
  });

  it('96000/32bit 极限值正确解析', () => {
    const result = parseProcessingOptions('{"sampleRate":96000,"bitDepth":32}');
    expect(result).not.toBeNull();
    expect(result!.sampleRate).toBe(96000);
    expect(result!.bitDepth).toBe(32);
  });

  it('空字符串返回 null', () => {
    expect(parseProcessingOptions('')).toBeNull();
  });

  it('undefined 返回 null', () => {
    expect(parseProcessingOptions(undefined)).toBeNull();
  });

  it('无效 JSON 返回 null', () => {
    expect(parseProcessingOptions('not-json')).toBeNull();
  });

  it('缺少 sampleRate 返回 null', () => {
    expect(parseProcessingOptions('{"bitDepth":24}')).toBeNull();
  });

  it('缺少 bitDepth 返回 null', () => {
    expect(parseProcessingOptions('{"sampleRate":48000}')).toBeNull();
  });
});

describe('sessionRestore - repairResult 解析', () => {
  it('有效 repairResult 正确解析', () => {
    const result = parseRepairResult('{"issues_found":["clipping"],"duration":180}');
    expect(result).not.toBeNull();
    expect(result!.issues_found).toEqual(['clipping']);
    expect(result!.duration).toBe(180);
  });

  it('空字符串返回 null', () => {
    expect(parseRepairResult('')).toBeNull();
  });

  it('undefined 返回 null', () => {
    expect(parseRepairResult(undefined)).toBeNull();
  });

  it('无效 JSON 返回 null', () => {
    expect(parseRepairResult('broken')).toBeNull();
  });
});

describe('sessionRestore - 完整 save/load/restore 模拟', () => {
  beforeEach(async () => {
    await clearSession();
  });

  afterEach(async () => {
    await clearSession();
  });

  function makeMockFile(name = 'test.wav', size = 1024): File {
    const arr = new Uint8Array(size);
    return new File([arr], name, { type: 'audio/wav' });
  }

  it('模拟完整恢复流程：save → load → buildPendingSession → parse', async () => {
    const file = makeMockFile('full-test.wav', 2048);
    const wavInfo = JSON.stringify({ sampleRate: 44100, channels: 2, duration: 120, bitDepth: 16 });
    const repairResult = JSON.stringify({
      issues_found: ['noise'],
      output_sample_rate: 48000,
      output_bit_depth: 24,
      duration: 120,
    });
    const processingOptions = JSON.stringify({ sampleRate: 48000, bitDepth: 24 });

    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'full-hash',
      taskId: 'task-full',
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo,
      repairResult,
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions,
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();

    const pending = buildPendingSession({
      file: loaded!.file,
      fileName: loaded!.fileName,
      fileHash: loaded!.fileHash,
      taskId: loaded!.taskId,
      hasBeenProcessed: loaded!.hasBeenProcessed,
      wavInfo: loaded!.wavInfo,
      repairResult: loaded!.repairResult,
      processingOptions: loaded!.processingOptions,
    });

    expect(pending.taskId).toBe('task-full');
    expect(pending.hasBeenProcessed).toBe(true);

    const parsedOpts = parseProcessingOptions(pending.processingOptions);
    expect(parsedOpts).not.toBeNull();
    expect(parsedOpts!.sampleRate).toBe(48000);
    expect(parsedOpts!.bitDepth).toBe(24);

    const parsedResult = parseRepairResult(pending.repairResult);
    expect(parsedResult).not.toBeNull();
    expect(parsedResult!.issues_found).toEqual(['noise']);
    expect(parsedResult!.duration).toBe(120);
  });

  it('模拟连续刷新：save → load → restore → 再次 load 仍有数据', async () => {
    const file = makeMockFile('refresh-test.wav', 4096);
    const processingOptions = JSON.stringify({ sampleRate: 96000, bitDepth: 32 });

    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'refresh-hash',
      taskId: 'task-refresh',
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo: '{"sampleRate":44100,"channels":2,"duration":60,"bitDepth":16}',
      repairResult: '{"issues_found":[],"duration":60}',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions,
    });

    const first = await loadSession();
    expect(first).not.toBeNull();
    expect(first!.taskId).toBe('task-refresh');

    const second = await loadSession();
    expect(second).not.toBeNull();
    expect(second!.taskId).toBe('task-refresh');
    expect(second!.processingOptions).toBe(processingOptions);

    const third = await loadSession();
    expect(third).not.toBeNull();
    expect(third!.taskId).toBe('task-refresh');
  });

  it('模拟 File 对象失效：save → load → file.size===0 → clearSession', async () => {
    const emptyFile = new File([], 'invalid.dat', { type: 'application/octet-stream' });
    await saveSession({
      file: emptyFile,
      fileName: 'invalid.dat',
      fileSize: 0,
      fileHash: 'invalid-hash',
      taskId: 'task-invalid',
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

    const isFileValid = loaded!.file instanceof File && loaded!.file.size > 0;
    expect(isFileValid).toBe(false);

    await clearSession();

    const afterClear = await loadSession();
    expect(afterClear).toBeNull();
  });

  it('模拟 backendAvailable 延迟：session 在 backend 不可用时仍可 load', async () => {
    const file = makeMockFile('delay-test.wav', 1024);
    await saveSession({
      file,
      fileName: file.name,
      fileSize: file.size,
      fileHash: 'delay-hash',
      taskId: 'task-delay',
      backendAvailable: false,
      hasBeenProcessed: false,
      wavInfo: '',
      repairResult: '',
      originalDetectTime: '',
      repairedDetectTime: '',
      processingOptions: '{"sampleRate":44100,"bitDepth":16}',
    });

    const loaded = await loadSession();
    expect(loaded).not.toBeNull();
    expect(loaded!.backendAvailable).toBe(false);
    expect(loaded!.taskId).toBe('task-delay');

    const pending = buildPendingSession({
      file: loaded!.file,
      fileName: loaded!.fileName,
      fileHash: loaded!.fileHash,
      taskId: loaded!.taskId,
      hasBeenProcessed: loaded!.hasBeenProcessed,
      wavInfo: loaded!.wavInfo,
      repairResult: loaded!.repairResult,
      processingOptions: loaded!.processingOptions,
    });

    expect(pending.taskId).toBe('task-delay');
    const opts = parseProcessingOptions(pending.processingOptions);
    expect(opts).not.toBeNull();
    expect(opts!.sampleRate).toBe(44100);
  });
});
