import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TEST_MP3_PATH = path.resolve(__dirname, '../../public/test_real_10mb.mp3');

test.describe('文件上传 - 10MB MP3 真实测试', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!fs.existsSync(TEST_MP3_PATH), '测试MP3文件不存在');
    await page.goto('/repair');
  });

  test('10MB MP3 上传完整流程：解码 → 分析 → 上传 → 完成', async ({ page }) => {
    const fileSize = fs.statSync(TEST_MP3_PATH).size;
    console.log(`测试文件大小: ${(fileSize / 1024 / 1024).toFixed(2)} MB`);

    const uploadInput = page.locator('input[type="file"]');
    await uploadInput.setInputFiles(TEST_MP3_PATH);

    await expect(page.getByText('test_real_10mb.mp3')).toBeVisible({ timeout: 30000 });

    const startTime = Date.now();

    await expect
      .poll(
        async () => {
          const hasSampleRate = await page.getByText(/kHz/).first().isVisible().catch(() => false);
          const hasAnalysis = await page.getByText(/频谱|动态范围|峰值/).first().isVisible().catch(() => false);
          return hasSampleRate && hasAnalysis;
        },
        { timeout: 120000, intervals: [1000, 2000, 3000] }
      )
      .toBeTruthy();

    const elapsed = (Date.now() - startTime) / 1000;
    console.log(`上传+解码+分析耗时: ${elapsed.toFixed(1)}s`);

    await expect(page.getByRole('button', { name: /开始修复/ })).toBeEnabled({ timeout: 5000 });
  });

  test('上传过程中显示进度', async ({ page }) => {
    const uploadInput = page.locator('input[type="file"]');

    let hasProgress = false;
    page.on('console', (msg) => {
      const text = msg.text();
      if (text.includes('解码') || text.includes('上传') || text.includes('分析')) {
        hasProgress = true;
      }
    });

    await uploadInput.setInputFiles(TEST_MP3_PATH);

    await expect
      .poll(() => hasProgress, { timeout: 15000 })
      .toBeTruthy();
  });

  test('上传后显示正确的音频信息', async ({ page }) => {
    const uploadInput = page.locator('input[type="file"]');
    await uploadInput.setInputFiles(TEST_MP3_PATH);

    await expect(page.getByText(/MB/).first()).toBeVisible({ timeout: 30000 });
    await expect(page.getByText(/kHz/).first()).toBeVisible({ timeout: 60000 });
  });
});

test.describe('分块上传 - 后端API测试', () => {
  test('简单上传接口正常', async ({ request }) => {
    test.skip(!fs.existsSync(TEST_MP3_PATH), '测试MP3文件不存在');

    const buffer = fs.readFileSync(TEST_MP3_PATH);
    const response = await request.post('/api/v1/upload', {
      multipart: {
        file: {
          name: 'test_10mb.mp3',
          mimeType: 'audio/mpeg',
          buffer,
        },
        file_hash: 'test_hash_e2e',
      },
    });

    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.task_id).toBeTruthy();
    expect(data.size).toBe(buffer.length);
    expect(data.audio_info).toBeTruthy();
    expect(data.audio_info.sample_rate).toBe(44100);
  });

  test('分块上传接口正常', async ({ request }) => {
    test.skip(!fs.existsSync(TEST_MP3_PATH), '测试MP3文件不存在');

    const buffer = fs.readFileSync(TEST_MP3_PATH);
    const chunkSize = 5 * 1024 * 1024;
    const totalChunks = Math.ceil(buffer.length / chunkSize);

    const initResp = await request.post('/api/v1/upload-init', {
      form: {
        filename: 'test_chunked_10mb.mp3',
        total_size: String(buffer.length),
        total_chunks: String(totalChunks),
        file_hash: 'test_chunked_hash_e2e',
      },
    });
    expect(initResp.ok()).toBeTruthy();
    const initData = await initResp.json();
    const sessionId = initData.session_id;
    expect(sessionId).toBeTruthy();

    for (let i = 0; i < totalChunks; i++) {
      const start = i * chunkSize;
      const end = Math.min(start + chunkSize, buffer.length);
      const chunk = buffer.subarray(start, end);

      const chunkResp = await request.post('/api/v1/upload-chunk', {
        multipart: {
          session_id: sessionId,
          chunk_index: String(i),
          chunk: {
            name: `chunk_${i}`,
            mimeType: 'application/octet-stream',
            buffer: chunk,
          },
        },
      });
      expect(chunkResp.ok()).toBeTruthy();
      const chunkData = await chunkResp.json();
      expect(chunkData.success).toBeTruthy();
    }

    const statusResp = await request.get(`/api/v1/upload-status?session_id=${sessionId}`);
    expect(statusResp.ok()).toBeTruthy();
    const statusData = await statusResp.json();
    expect(statusData.uploaded_count).toBe(totalChunks);
    expect(statusData.progress).toBe(100);

    const finalizeResp = await request.post('/api/v1/upload-finalize', {
      form: { session_id: sessionId },
    });
    expect(finalizeResp.ok()).toBeTruthy();
    const finalizeData = await finalizeResp.json();
    expect(finalizeData.success).toBeTruthy();
    expect(finalizeData.task_id).toBeTruthy();
    expect(finalizeData.size).toBe(buffer.length);
  });

  test('哈希检查接口正常', async ({ request }) => {
    const resp = await request.post('/api/v1/check-hash', {
      data: { file_hash: 'nonexistent_hash_e2e_test' },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.exists).toBe(false);
  });
});
