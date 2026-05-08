# Checklist

## AI 检测算法 v1.2 优化

- [ ] 训练素材（AI 音乐）特征已提取并分析
- [ ] 当前 v1.2 在 AI 音乐上的 AI 概率分布已统计
- [ ] 检出不足的关键特征已识别
- [ ] spectral_correlation 权重已提高
- [ ] centroid_cv 阈值已调整
- [ ] micro_rhythm_consistency 权重已提高
- [ ] rms_cv 阈值已调整
- [ ] dynamic_range 判定已优化
- [ ] mfcc_variability 敏感度已提高
- [ ] harmonic_ratio 权重已调整
- [ ] ai_score/human_score 总分已重新平衡
- [ ] 所有 AI 音乐素材 AI 概率 > 70%
- [ ] 人类创作音频误判率已验证（人类概率 > 50%）

## AI 修复算法 v2.1 音质优化

- [ ] 频谱组 A Wiener 掩码已增加时域平滑
- [ ] 频谱组 A 降噪 floor 参数已自适应
- [ ] 频谱组 B 谐波注入已增加频域交叉淡化
- [ ] 响度归一化已改为滑动窗口 RMS
- [ ] lookahead 限制器已增加减少 pumping
- [ ] 多段压缩器已增加自动 makeup gain
- [ ] 压缩/释放时间已自适应
- [ ] 峰值限制器已增加 4x 超采样
- [ ] 软削波曲线已优化

## 构建与测试

- [ ] 前端 `npm run build` 构建成功
- [ ] `release_android.tar.gz` 已重新打包
- [ ] v2.1 优化前后音质对比测试已完成
- [ ] artifacts 减少已验证
- [ ] 响度归一化 pumping 减少已验证
