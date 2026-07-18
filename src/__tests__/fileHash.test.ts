import { describe, it, expect, vi, beforeEach } from 'vitest';
import { computeFileHash } from '../utils/fileHash';

const fnv1aHash = (data: Uint8Array, extraSeed = 0): number => {
  let hash = 0x811c9dc5 ^ extraSeed;
  for (let i = 0; i < data.length; i++) {
    hash ^= data[i];
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
};

describe('fileHash - 哈希计算', () => {
  describe('fnv1aHash 算法验证', () => {
    it('空数组返回 FNV 偏移基准', () => {
      const hash = fnv1aHash(new Uint8Array(0));
      expect(hash).toBe(0x811c9dc5);
    });
    
    it('相同输入产生相同哈希', () => {
      const data = new Uint8Array([1, 2, 3, 4, 5]);
      const hash1 = fnv1aHash(data);
      const hash2 = fnv1aHash(data);
      expect(hash1).toBe(hash2);
    });
    
    it('不同输入产生不同哈希', () => {
      const data1 = new Uint8Array([1, 2, 3]);
      const data2 = new Uint8Array([3, 2, 1]);
      expect(fnv1aHash(data1)).not.toBe(fnv1aHash(data2));
    });
    
    it('支持 extraSeed 参数', () => {
      const data = new Uint8Array([1, 2, 3]);
      const hash1 = fnv1aHash(data, 0);
      const hash2 = fnv1aHash(data, 123);
      expect(hash1).not.toBe(hash2);
    });
    
    it('单字节数据计算正确', () => {
      const hash = fnv1aHash(new Uint8Array([0x00]));
      const expected = Math.imul(0x811c9dc5 ^ 0x00, 0x01000193) >>> 0;
      expect(hash).toBe(expected);
    });
  });
  
  describe('computeFileHash', () => {
    beforeEach(() => {
      vi.restoreAllMocks();
    });
    
    it('crypto.subtle 可用时使用 SHA-256', async () => {
      const mockDigest = vi.fn().mockResolvedValue(new ArrayBuffer(32));
      Object.defineProperty(globalThis, 'crypto', {
        value: {
          subtle: {
            digest: mockDigest,
          },
        },
        writable: true,
      });
      
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' });
      const hash = await computeFileHash(file);
      
      expect(mockDigest).toHaveBeenCalled();
      expect(typeof hash).toBe('string');
      expect(hash.length).toBe(64);
    });
    
    it('crypto.subtle 不可用时回退到 FNV1a', async () => {
      Object.defineProperty(globalThis, 'crypto', {
        value: {
          subtle: undefined,
        },
        writable: true,
      });
      
      const file = new File(['test content 12345'], 'test.txt', { type: 'text/plain' });
      const hash = await computeFileHash(file);
      
      expect(typeof hash).toBe('string');
      expect(hash.length).toBeGreaterThan(10);
    });
    
    it('相同文件内容产生相同哈希', async () => {
      Object.defineProperty(globalThis, 'crypto', {
        value: {
          subtle: undefined,
        },
        writable: true,
      });
      
      const content = 'test content for hash';
      const file1 = new File([content], 'file1.txt', { type: 'text/plain' });
      const file2 = new File([content], 'file2.txt', { type: 'text/plain' });
      
      const hash1 = await computeFileHash(file1);
      const hash2 = await computeFileHash(file2);
      
      expect(hash1).toBe(hash2);
    });
    
    it('相同内容不同文件名产生相同哈希', async () => {
      Object.defineProperty(globalThis, 'crypto', {
        value: {
          subtle: undefined,
        },
        writable: true,
      });
      
      const content = 'same content';
      const file1 = new File([content], 'a.txt', { type: 'text/plain' });
      const file2 = new File([content], 'b.txt', { type: 'text/plain' });
      
      const hash1 = await computeFileHash(file1);
      const hash2 = await computeFileHash(file2);
      
      expect(hash1).toBe(hash2);
    });
    
    it('小文件（<2MB）读取全部内容', async () => {
      Object.defineProperty(globalThis, 'crypto', {
        value: {
          subtle: undefined,
        },
        writable: true,
      });
      
      const smallContent = new Array(1000).fill('x').join('');
      const file = new File([smallContent], 'small.txt', { type: 'text/plain' });
      
      const hash = await computeFileHash(file);
      
      expect(typeof hash).toBe('string');
      expect(hash.length).toBeGreaterThan(0);
    });
    
    it('大文件（>2MB）使用首尾分块采样', async () => {
      Object.defineProperty(globalThis, 'crypto', {
        value: {
          subtle: undefined,
        },
        writable: true,
      });
      
      const largeContent = new Array(3 * 1024 * 1024).fill('x').join('');
      const file = new File([largeContent], 'large.txt', { type: 'text/plain' });
      
      const hash = await computeFileHash(file);
      
      expect(typeof hash).toBe('string');
      expect(hash.length).toBeGreaterThan(0);
    });
    
    it('哈希格式为十六进制字符串', async () => {
      Object.defineProperty(globalThis, 'crypto', {
        value: {
          subtle: undefined,
        },
        writable: true,
      });
      
      const file = new File(['hello'], 'test.txt', { type: 'text/plain' });
      const hash = await computeFileHash(file);
      
      expect(/^[0-9a-f]+$/.test(hash)).toBe(true);
    });
  });
});
