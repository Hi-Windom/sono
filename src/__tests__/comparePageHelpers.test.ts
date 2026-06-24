import { describe, it, expect } from 'vitest';
import { formatTime, formatTimePrecise, parseTimeInput } from '../pages/ComparePage';

describe('ComparePage 时间辅助函数', () => {
  describe('formatTime', () => {
    it('格式化秒为 m:ss', () => {
      expect(formatTime(0)).toBe('0:00');
      expect(formatTime(5)).toBe('0:05');
      expect(formatTime(65)).toBe('1:05');
      expect(formatTime(125)).toBe('2:05');
      expect(formatTime(3661)).toBe('61:01');
    });

    it('负数与非有限值回退为 0:00', () => {
      expect(formatTime(-1)).toBe('0:00');
      expect(formatTime(NaN)).toBe('0:00');
      expect(formatTime(Infinity)).toBe('0:00');
    });

    it('向下取整秒', () => {
      expect(formatTime(5.9)).toBe('0:05');
      expect(formatTime(59.99)).toBe('0:59');
    });
  });

  describe('formatTimePrecise', () => {
    it('格式化为 m:ss.d（十分位）', () => {
      expect(formatTimePrecise(0)).toBe('0:00.0');
      expect(formatTimePrecise(5.3)).toBe('0:05.3');
      expect(formatTimePrecise(65.25)).toBe('1:05.2');
    });

    it('负数与非有限值回退为 0:00.0', () => {
      expect(formatTimePrecise(-1)).toBe('0:00.0');
      expect(formatTimePrecise(Infinity)).toBe('0:00.0');
    });
  });

  describe('parseTimeInput', () => {
    it('解析 m:ss 格式', () => {
      expect(parseTimeInput('0:05')).toBe(5);
      expect(parseTimeInput('1:05')).toBe(65);
      expect(parseTimeInput('2:30')).toBe(150);
    });

    it('解析 m:ss.d 带十分位', () => {
      expect(parseTimeInput('1:05.5')).toBe(65.5);
      expect(parseTimeInput('0:00.3')).toBe(0.3);
    });

    it('解析纯数字（秒）', () => {
      expect(parseTimeInput('90')).toBe(90);
      expect(parseTimeInput('12.5')).toBe(12.5);
    });

    it('空字符串返回 null', () => {
      expect(parseTimeInput('')).toBeNull();
      expect(parseTimeInput('   ')).toBeNull();
    });

    it('非法格式返回 null', () => {
      expect(parseTimeInput('abc')).toBeNull();
      expect(parseTimeInput(':30')).toBeNull();
    });

    it('m:ss 中秒数超出 0-59 不会匹配 m:ss 格式，回退到 parseFloat', () => {
      // '1:99' 不匹配 m:ss（秒位 [0-5]?\d），回退 parseFloat('1:99') = 1
      expect(parseTimeInput('1:99')).toBe(1);
    });

    it('解析结果可被 formatTimePrecise 往返（十分位精度）', () => {
      const inputs = ['0:05.3', '1:30.0', '2:15.7'];
      for (const input of inputs) {
        const parsed = parseTimeInput(input);
        expect(parsed).not.toBeNull();
        expect(formatTimePrecise(parsed!)).toBe(input);
      }
    });
  });
});
