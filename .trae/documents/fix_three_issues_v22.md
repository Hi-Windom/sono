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

### 问题 1：修复播放切换（采用静音策略）

**文件**: `src/components/AudioPlayer.tsx`

**用户反馈**: 频繁切换对比播放体验，应该使用**静音处理**而不是停止释放。

**原因**:
- 停止+释放会导致音频从头加载，切换时有延迟
- 静音可以保持音频缓冲，切换瞬间响应
- 两个 Audio 对象同时存在，通过控制 `muted` 属性实现 A/B 对比

**改动**:
1. 同时创建两个 `Audio` 对象（原始和修复），但初始都 `muted`
2. 切换时只需改变 `muted` 属性，无需重新加载
3. 播放/暂停时同步控制两个 Audio 的 `paused` 状态
4. 组件卸载时才释放 Audio 对象

```typescript
// 同时维护两个 Audio 对象
const originalAudioRef = useRef<HTMLAudioElement | null>(null);
const repairedAudioRef = useRef<HTMLAudioElement | null>(null);

const playPreview = useCallback((source: 'original' | 'repaired') => {
  // 确保两个音频都已加载
  if (!originalAudioRef.current) {
    originalAudioRef.current = new Audio(audioUrl);
    originalAudioRef.current.muted = true;
  }
  if (!repairedAudioRef.current) {
    repairedAudioRef.current = new Audio(repairedUrl);
    repairedAudioRef.current.muted = true;
  }
  
  // 同步播放进度
  const targetTime = source === 'original' 
    ? originalAudioRef.current.currentTime 
    : repairedAudioRef.current.currentTime;
  
  // 切换静音状态
  originalAudioRef.current.muted = (source === 'repaired');
  repairedAudioRef.current.muted = (source === 'original');
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
