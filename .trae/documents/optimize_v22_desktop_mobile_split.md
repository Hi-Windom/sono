# v2.2 桌面端与移动端隔离实现方案

## 用户核心需求
- **桌面端**: 最佳效果，音质显著提升
- **移动端**: 确保音质和速度，牺牲部分处理效果
- **版本区分**: 移动端注册为 v2.2a
- **Termux 兼容**: 移动端必须兼容

## 架构设计

### 版本区分策略
```
v2.2  - 桌面端完整版（最佳音质）
v2.2a - 移动端精简版（速度优先）
```

### 代码共享与隔离
```
backend/services/repair/
├── repair_v2_2/              # 桌面端完整版
│   ├── __init__.py
│   ├── core.py              # 桌面端核心流程
│   ├── spectral_group_a.py  # 完整频谱处理
│   ├── dynamics.py          # 多段压缩
│   └── ...
│
└── repair_v2_2a/             # 移动端精简版
    ├── __init__.py
    ├── core.py              # 移动端核心流程（精简）
    ├── spectral_fast.py     # 极速频谱处理
    ├── dynamics_simple.py   # 单段压缩
    └── ...
```

## 桌面端 v2.2 特性（最佳效果）

### 算法特性
1. **完整频谱处理**
   - Wiener 滤波降噪
   - 自适应去齿音
   - 毛刺修复
   - 谐波增强

2. **多段动态处理**
   - 3 段压缩
   - 自适应阈值
   - 保留动态范围

3. **高级功能**
   - 音乐类型检测
   - 立体声增强
   - 响度归一化（True Peak）

### 性能目标
- 处理速度：可接受（不追求极致速度）
- 音质：显著提升
- 内存：无限制

## 移动端 v2.2a 特性（速度优先）

### 算法精简
1. **简化频谱处理**
   - 频谱减法降噪（替代 Wiener）
   - 固定频段去齿音
   - 可选毛刺修复

2. **单段压缩**
   - 替代多段压缩
   - 简化包络检测

3. **核心功能保留**
   - 基础降噪
   - 基础去齿音
   - 响度归一化

### 性能目标
- 处理速度：提升 5x+
- 音质：确保不下降（可接受轻微损失）
- 内存：< 300MB

## 具体实现差异

### 1. 核心流程差异

#### 桌面端 core.py
```python
# 完整处理流程
1. 时域修复（削波、爆音）
2. 动态处理（多段压缩）
3. 频谱处理（完整 Wiener 降噪 + 去齿音 + 毛刺）
4. 谐波增强
5. 立体声增强
6. 响度归一化
```

#### 移动端 core_a.py
```python
# 精简处理流程
1. 时域修复（削波、爆音）- 简化
2. 单次 STFT
3. 频谱处理（简化降噪 + 固定去齿音）
4. ISTFT
5. 单段压缩
6. 响度归一化
```

### 2. 频谱处理差异

#### 桌面端 spectral_group_a.py
- 完整 Wiener 滤波
- 决策导向 SNR 估计
- 时间 + 频率平滑
- 自适应去齿音

#### 移动端 spectral_fast.py
- 简化频谱减法
- 固定噪声估计
- 单次平滑
- 固定频段去齿音

### 3. 压缩器差异

#### 桌面端 dynamics.py
- 3 段压缩
- 独立频段处理
- 复杂包络检测

#### 移动端 dynamics_simple.py
- 单段压缩
- 全频段统一处理
- 简化包络检测

## 版本注册

### audio_repair.py 配置
```python
ALGORITHM_VERSIONS = {
    "v2.2": {
        "name": "v2.2",
        "label": "v2.2 桌面版",
        "description": "最佳音质，完整处理",
        "mobile_compatible": False,  # 桌面端
        "repair_fn": repair_audio_v2_2,
        ...
    },
    "v2.2a": {
        "name": "v2.2a",
        "label": "v2.2a 移动版",
        "description": "速度优先，精简处理",
        "mobile_compatible": True,   # 移动端
        "repair_fn": repair_audio_v2_2a,
        ...
    },
}
```

## 文件结构

```
backend/services/repair/
├── repair_v2_2/                    # 桌面端
│   ├── __init__.py
│   ├── core.py                     # 完整核心流程
│   ├── music_type_detector.py      # 完整类型检测
│   ├── spectral_group_a.py         # 完整频谱处理
│   ├── spectral_group_b.py         # 谐波增强
│   ├── dynamics.py                 # 多段压缩
│   ├── filters.py                  # 滤波处理
│   ├── spatial.py                  # 空间处理
│   ├── postprocess.py              # 后期处理
│   └── type_params.py              # 参数配置
│
├── repair_v2_2a/                   # 移动端
│   ├── __init__.py
│   ├── core.py                     # 精简核心流程
│   ├── spectral_fast.py            # 极速频谱处理
│   ├── dynamics_simple.py          # 单段压缩
│   ├── filters_simple.py           # 简化滤波
│   ├── postprocess_simple.py       # 简化后期处理
│   └── type_params.py              # 精简参数
│
└── audio_repair.py                 # 版本注册
```

## 实施计划

### Phase 1: 创建 v2.2a 移动端版本
1. 创建 `repair_v2_2a/` 目录
2. 实现精简版核心流程
3. 实现极速频谱处理
4. 实现单段压缩

### Phase 2: 注册版本
1. 在 `audio_repair.py` 注册 v2.2a
2. 配置移动端参数
3. 标记 mobile_compatible=True

### Phase 3: 测试验证
1. 桌面端测试（v2.2）
2. 移动端测试（v2.2a）
3. 性能对比
4. 音质对比

## 验证标准

### 桌面端 v2.2
- [ ] 音质显著提升
- [ ] 处理效果完整
- [ ] 不追求极致速度

### 移动端 v2.2a
- [ ] 速度提升 5x+
- [ ] 音质不下降
- [ ] Termux 兼容
- [ ] 内存 < 300MB
