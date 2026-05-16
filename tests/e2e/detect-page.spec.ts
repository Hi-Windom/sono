import { test, expect } from '@playwright/test';

test.describe('Detect Page', () => {
  test('should render detect page correctly', async ({ page }) => {
    await page.goto('/detect');
    
    // Check that main elements are present
    await expect(page.getByText(/检测|AI 检测/).first()).toBeVisible();
    
    // Check for file upload area
    await expect(page.getByText(/上传|选择文件|音频文件/).first()).toBeVisible();
  });

  test('should navigate back to landing page', async ({ page }) => {
    await page.goto('/detect');
    
    // Go back to landing page
    await page.goBack();
    await expect(page).toHaveURL('/');
  });
});
