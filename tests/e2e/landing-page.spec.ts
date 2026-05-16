import { test, expect } from '@playwright/test';

test.describe('Landing Page', () => {
  test('should render landing page correctly', async ({ page }) => {
    await page.goto('/');
    
    // Check that main elements are present
    await expect(page.getByRole('heading', { name: 'AI 音乐处理工具' })).toBeVisible();
    await expect(page.getByText('专业的 AI 音乐修复与检测工具')).toBeVisible();
    
    // Check all feature cards are present
    await expect(page.getByText('AI 音乐修复')).toBeVisible();
    await expect(page.getByText('AI 训练素材上传')).toBeVisible();
    await expect(page.getByText('修复参数配置')).toBeVisible();
    await expect(page.getByText('质量测试')).toBeVisible();
    await expect(page.getByText('缓存管理')).toBeVisible();
    await expect(page.getByText('音频 AB 对比')).toBeVisible();
    await expect(page.getByText('AI检测分析')).toBeVisible();
    await expect(page.getByText('系统流程可视化')).toBeVisible();
  });

  test('should navigate to repair page when clicking AI 音乐修复 card', async ({ page }) => {
    await page.goto('/');
    
    await page.getByText('AI 音乐修复').click();
    await expect(page).toHaveURL('/repair');
  });

  test('should navigate to training upload page when clicking AI 训练素材上传 card', async ({ page }) => {
    await page.goto('/');
    
    await page.getByText('AI 训练素材上传').click();
    await expect(page).toHaveURL('/training-upload');
  });

  test('should navigate to profile manager page when clicking 修复参数配置 card', async ({ page }) => {
    await page.goto('/');
    
    await page.getByText('修复参数配置').click();
    await expect(page).toHaveURL('/profile-manager');
  });

  test('should navigate to quality test page when clicking 质量测试 card', async ({ page }) => {
    await page.goto('/');
    
    await page.getByText('质量测试').click();
    await expect(page).toHaveURL('/quality-tests');
  });

  test('should navigate to cache manager page when clicking 缓存管理 card', async ({ page }) => {
    await page.goto('/');
    
    await page.getByText('缓存管理').click();
    await expect(page).toHaveURL('/cache-manager');
  });

  test('should navigate to compare page when clicking 音频 AB 对比 card', async ({ page }) => {
    await page.goto('/');
    
    await page.getByText('音频 AB 对比').click();
    await expect(page).toHaveURL('/compare');
  });

  test('should navigate to detect page when clicking AI检测分析 card', async ({ page }) => {
    await page.goto('/');
    
    await page.getByText('AI检测分析').click();
    await expect(page).toHaveURL('/detect');
  });

  test('should navigate to flow page when clicking 系统流程可视化 card', async ({ page }) => {
    await page.goto('/');
    
    await page.getByText('系统流程可视化').click();
    await expect(page).toHaveURL('/flow');
  });
});
