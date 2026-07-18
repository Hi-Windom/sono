const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const TEST_FILE = path.join(__dirname, '../scripts/test_10mb.mp3');
const BASE_URL = 'http://localhost:5175';

async function runTest() {
  console.log('=== 10MB MP3 + v3.2 修复全流程测试 ===\n');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];
  const logs = [];

  page.on('console', (msg) => {
    logs.push(`[${msg.type()}] ${msg.text()}`);
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });

  page.on('pageerror', (err) => {
    errors.push(`PageError: ${err.message}`);
  });

  try {
    // 1. 打开修复页面
    console.log('1. 打开修复页面...');
    await page.goto(`${BASE_URL}/repair`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    console.log('   ✅ 页面加载成功');

    // 2. 检查后端连接
    console.log('\n2. 检查后端连接状态...');
    const connStatus = await page.locator('text=已连接').first();
    if (await connStatus.isVisible()) {
      console.log('   ✅ 后端已连接');
    } else {
      console.log('   ⚠️  未找到"已连接"状态，继续测试');
    }

    // 3. 切换到双轨模式（v3.2 是双轨版本）
    console.log('\n3. 切换到双轨上传模式...');
    const dualTrackBtn = page.locator('button:has-text("双轨上传")').first();
    if (await dualTrackBtn.isVisible()) {
      await dualTrackBtn.click();
      await page.waitForTimeout(1000);
      console.log('   ✅ 已切换到双轨模式');
    } else {
      console.log('   ⚠️  未找到双轨上传按钮，继续单轨模式');
    }

    // 4. 上传 10MB MP3 文件
    console.log('\n4. 上传 10MB MP3 文件...');
    
    const fileInput = page.locator('input[type="file"]').first();
    if (await fileInput.isVisible()) {
      await fileInput.setInputFiles(TEST_FILE);
    } else {
      const dropZone = page.locator('[class*="drop"], [class*="upload"]').first();
      await dropZone.setInputFiles(TEST_FILE);
    }
    
    console.log('   文件已选择，等待上传和解码...');
    
    await page.waitForTimeout(5000);
    
    const uploadStartTime = Date.now();
    let uploadSuccess = false;
    
    for (let i = 0; i < 60; i++) {
      await page.waitForTimeout(1000);
      const pageText = await page.locator('body').innerText();
      
      if (pageText.includes('修复参数') || pageText.includes('开始修复') || pageText.includes('AI音频修复')) {
        uploadSuccess = true;
        const uploadDuration = (Date.now() - uploadStartTime) / 1000;
        console.log(`   ✅ 上传/解码完成，耗时 ${uploadDuration.toFixed(1)}s`);
        break;
      }
      
      if (pageText.includes('失败') || pageText.includes('错误')) {
        console.log(`   ❌ 上传失败`);
        break;
      }
    }
    
    if (!uploadSuccess) {
      console.log('   ⚠️  上传状态不确定，继续尝试修复');
    }

    // 5. 选择 v3.2 算法版本
    console.log('\n5. 选择 v3.2 算法版本...');
    
    const algoSelector = page.locator('button:has-text("v")').first();
    if (await algoSelector.isVisible()) {
      await algoSelector.click();
      await page.waitForTimeout(500);
      
      const v32Option = page.locator('text=v3.2').first();
      if (await v32Option.isVisible()) {
        await v32Option.click();
        await page.waitForTimeout(1000);
        console.log('   ✅ 已选择 v3.2');
      } else {
        console.log('   ⚠️  未找到 v3.2 选项');
      }
    } else {
      console.log('   ⚠️  未找到算法版本选择器');
    }

    // 6. 开始修复
    console.log('\n6. 开始修复...');
    
    const startRepairBtn = page.locator('button:has-text("开始修复")').first();
    if (await startRepairBtn.isVisible() && await startRepairBtn.isEnabled()) {
      await startRepairBtn.click();
      console.log('   ✅ 已点击开始修复');
    } else {
      console.log('   ⚠️  开始修复按钮不可用，尝试查找其他按钮...');
      const buttons = await page.locator('button').all();
      for (const btn of buttons) {
        const text = await btn.innerText();
        if (text.includes('修复') && !text.includes('修复参数')) {
          await btn.click();
          console.log(`   ✅ 点击了 "${text}" 按钮`);
          break;
        }
      }
    }

    // 7. 等待修复完成
    console.log('\n7. 等待修复完成...');
    
    const repairStartTime = Date.now();
    let repairSuccess = false;
    let lastProgress = '';
    
    for (let i = 0; i < 300; i++) {
      await page.waitForTimeout(1000);
      const pageText = await page.locator('body').innerText();
      
      const progressMatch = pageText.match(/(\d+)%/);
      if (progressMatch && progressMatch[0] !== lastProgress) {
        lastProgress = progressMatch[0];
        console.log(`   进度: ${lastProgress} (${Math.floor((Date.now() - repairStartTime) / 1000)}s)`);
      }
      
      if (pageText.includes('修复完成') || pageText.includes('完成!') || pageText.includes('已完成')) {
        repairSuccess = true;
        const repairDuration = (Date.now() - repairStartTime) / 1000;
        console.log(`   ✅ 修复完成！总耗时 ${repairDuration.toFixed(1)}s`);
        break;
      }
      
      if (pageText.includes('修复失败') || pageText.includes('错误') || pageText.includes('失败')) {
        console.log(`   ❌ 修复失败`);
        break;
      }
      
      if (Date.now() - repairStartTime > 300000) {
        console.log('   ⏰ 修复超时（5分钟）');
        break;
      }
    }

    // 8. 检查控制台错误
    console.log('\n8. 检查控制台错误...');
    console.log(`   控制台错误数: ${errors.length}`);
    if (errors.length > 0) {
      console.log('   错误列表:');
      errors.slice(0, 10).forEach(e => console.log(`     - ${e}`));
    } else {
      console.log('   ✅ 无控制台错误');
    }

    // 9. 截图
    console.log('\n9. 保存截图...');
    const screenshotPath = path.join(__dirname, 'test_result.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`   ✅ 截图已保存: ${screenshotPath}`);

    // 总结
    console.log('\n=== 测试总结 ===');
    console.log(`页面加载: ✅`);
    console.log(`文件上传: ${uploadSuccess ? '✅' : '⚠️'}`);
    console.log(`修复完成: ${repairSuccess ? '✅' : '❌'}`);
    console.log(`控制台错误: ${errors.length} 个`);

    return {
      success: repairSuccess,
      errors,
      duration: (Date.now() - repairStartTime) / 1000,
    };

  } catch (error) {
    console.error('\n❌ 测试异常:', error.message);
    console.error(error.stack);
    
    const screenshotPath = path.join(__dirname, 'test_error.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`错误截图已保存: ${screenshotPath}`);
    
    return {
      success: false,
      error: error.message,
    };
  } finally {
    await browser.close();
  }
}

runTest().then(result => {
  process.exit(result.success ? 0 : 1);
}).catch(err => {
  console.error('测试运行失败:', err);
  process.exit(1);
});
