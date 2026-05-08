# 修复三个问题：播放切换、电流声、桌面端效果

## 问题总结

### 问题 1：播放音频切换多个源共同播放
**现象**: 切换 A/B 对比时，两个音频同时播放
**根因**: `AudioPlayer.tsx` 中 `playPreview()` 每次切换都创建新的 `Audio` 对象，旧的未被正确停止

### 问题 2：移动端 v2.2a 呲呲电流声
**现象**: 修复后出现"呲呲"噪声，仅在修复后出现
**根因**: 
- 频谱减法过度：`floor=0.3` 仍然过低，产生"音乐噪声"
- 去齿音衰减过度：`attenuation = 1.0 - 0.5 * deess` 在 deess=0.2 时衰减 10%
- 硬削波检测 `_simple_declip` 使用 `np.sign(y) * (1.0 - np.exp(-abs_y))` 产生非线性失真
- 单段压缩分块处理导致增益突变

### 问题 3：桌面端 v2.2 效果一般
**现象**: 音质改善不明显、特定问题修复不到位、听感不自然
**根因**:
- 默认参数过于保守（de_clipping=0.35, noise_reduction=0.25）
- 处理步骤过多但每个步骤强度不足
- 缺少真正的 AI 感知修复，仍基于传统 DSP
- 音乐类型检测后未充分利用类型信息调整参数

## 修复方案

### 问题 1：修复播放切换

**文件**: `src/components/AudioPlayer.tsx`

**改动**:
1. `playPreview()` 中切换 source 前先 `stop()` 当前播放
2. `useEffect` 清理时确保所有 Audio 对象被释放
3. 添加 `audioRef` 追踪当前活跃的 Audio 对象

```typescript
// 在切换前确保停止当前播放
const playPreview = useCallback((source: 'original' | 'repaired') => {
  if (audioRef.current) {
    audioRef.current.pause();
    audioRef.current.currentTime = 0;
    audioRef.current = null;
  }
  // ... 创建新 Audio
}, []);
```

### 问题 2：修复移动端电流声

**文件**: `backend/services/repair/repair_v2_2a/core.py`

**改动**:
1. **提高频谱减法 floor**: 从 0.3 提高到 0.5，避免过度衰减
2. **降低去齿音强度**: 衰减系数从 0.5 降低到 0.3
3. **修复削波检测**: 使用更保守的阈值检测，避免非线性失真
4. **添加噪声门限**: 在输出前添加简单噪声门限，抑制低电平噪声
5. **压缩器增益平滑**: 增加块间增益过渡

### 问题 3：提升桌面端效果

**文件**: `backend/services/repair/repair_v2_2/core.py`

**改动**:
1. **增强默认参数**: 
   - de_clipping: 0.35 → 0.45
   - noise_reduction: 0.25 → 0.35
   - de_essing: 0.25 → 0.35
   - harmonic_enhance: 0.12 → 0.18
   
2. **类型自适应增强**:
   - 人声：增强去齿音和谐波
   - 器乐：增强空间感和清晰度
   - 电子：增强低频和动态
   
3. **添加智能强度调整**:
   - 根据输入音频质量自动调整处理强度
   - 检测到严重问题时增加处理力度

## 文件改动清单

| 文件 | 操作 | 说明 |
|-----|------|------|
| `src/components/AudioPlayer.tsx` | 修改 | 修复切换播放时多源共存 |
| `backend/services/repair/repair_v2_2a/core.py` | 修改 | 修复电流声：提高floor、降低去齿音、噪声门限 |
| `backend/services/repair/repair_v2_2/core.py` | 修改 | 增强默认参数、类型自适应 |

## 验证步骤

1. 前端：切换 A/B 对比，确认只有一个音频播放
2. 移动端：测试修复后音频，确认无电流声
3. 桌面端：对比修复前后，确认音质明显改善
