import { test, expect } from '@playwright/test';

test.describe('Repair Page', () => {
  test('should render repair page correctly', async ({ page }) => {
    await page.goto('/repair');
    
    // Check that main elements are present
    await expect(page.getByRole('heading', { name: /修复/ })).toBeVisible();
    
    // Check for file upload area - it should have an upload button
    await expect(page.getByText(/上传|选择文件|音频文件/).first()).toBeVisible();
  });

  test('should show header with navigation', async ({ page }) => {
    await page.goto('/repair');
    
    // Check that header is present and has logo or site title
    const header = page.locator('header').first();
    await expect(header).toBeVisible();
    
    // Test navigation back to landing page
    await page.getByText(/首页|返回|AI 音乐处理工具/).first().click();
    await expect(page).toHaveURL('/');
  });
});
import { test, expect } from '@playwright/test';

test.describe('Repair Page', () => {
  test('should render repair page correctly', async ({ page }) => {
    await page.goto('/repair');
    
    // Check that main elements are present
    await expect(page.getByRole('heading', { name: /修复/ })).toBeVisible();
    
    // Check for file upload area - it should have an upload button
    await expect(page.getByText(/上传|选择文件|音频文件/).first()).toBeVisible();
  });

  test('should show header with navigation', async ({ page }) => {
    await page.goto('/repair');
    
    // Check that header is present and has logo or site title
    const header = page.locator('header').first();
    await expect(header).toBeVisible();
    
    // Test navigation back to landing page
    await page.getByText(/首页|返回|AI 音乐处理工具/).first().click();
    await expect(page).toHaveURL('/');
  });
});
