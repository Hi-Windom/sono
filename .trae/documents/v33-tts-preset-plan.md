## v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5.# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

## 实现步骤

### 1. 后端：添加 TTS 预设配置

#### a. `repair_v3_3/config.py`
```python
PRESETS = {# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

## 实现步骤

### 1. 后端：添加 TTS 预设配置

#### a. `repair_v3_3/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

## 实现步骤

### 1. 后端：添加 TTS 预设配置

#### a. `repair_v3_3/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },
    "tts": {
        "spectral_naturalize": 0.6,
        "noise_floor_shape":# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

## 实现步骤

### 1. 后端：添加 TTS 预设配置

#### a. `repair_v3_3/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },
    "tts": {
        "spectral_naturalize": 0.6,
        "noise_floor_shape": 0.5,
        "harmonic_deregularize": 0.4,
        "phase_naturalize": 0.# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

## 实现步骤

### 1. 后端：添加 TTS 预设配置

#### a. `repair_v3_3/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },
    "tts": {
        "spectral_naturalize": 0.6,
        "noise_floor_shape": 0.5,
        "harmonic_deregularize": 0.4,
        "phase_naturalize": 0.3,
        "transient_protect": 0.8,
        "dynamic_naturalize": 0.3,
# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

## 实现步骤

### 1. 后端：添加 TTS 预设配置

#### a. `repair_v3_3/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },
    "tts": {
        "spectral_naturalize": 0.6,
        "noise_floor_shape": 0.5,
        "harmonic_deregularize": 0.4,
        "phase_naturalize": 0.3,
        "transient_protect": 0.8,
        "dynamic_naturalize": 0.3,
    },
}
```

#### b. `repair_v3_3p/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

## 实现步骤

### 1. 后端：添加 TTS 预设配置

#### a. `repair_v3_3/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },
    "tts": {
        "spectral_naturalize": 0.6,
        "noise_floor_shape": 0.5,
        "harmonic_deregularize": 0.4,
        "phase_naturalize": 0.3,
        "transient_protect": 0.8,
        "dynamic_naturalize": 0.3,
    },
}
```

#### b. `repair_v3_3p/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },
    "tts": {
        "spectral_naturalize": 0.7,
# v3.3 系列算法 TTS 预设开发计划

## 目标
在 v3.3 系列算法的单轨模式新增 "TTS" 预设，专门处理 TTS 音频。

## 涉及文件

### 后端
1. `backend/services/repair/repair_v3_3/config.py` - 添加 TTS 预设配置
2. `backend/services/repair/repair_v3_3p/config.py` - 添加 TTS 预设配置
3. `backend/services/audio_repair.py` - 在 v3.3+ 的 modes 中添加 TTS 模式
4. `backend/services/repair/repair_v3_3/core.py` - 更新预设检查逻辑

### 前端
5. `src/services/backendApi.ts` - 更新 V33RepairParams 类型
6. `src/components/AIRepairPanel.tsx` - 添加 TTS 预设按钮

## 实现步骤

### 1. 后端：添加 TTS 预设配置

#### a. `repair_v3_3/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },
    "tts": {
        "spectral_naturalize": 0.6,
        "noise_floor_shape": 0.5,
        "harmonic_deregularize": 0.4,
        "phase_naturalize": 0.3,
        "transient_protect": 0.8,
        "dynamic_naturalize": 0.3,
    },
}
```

#### b. `repair_v3_3p/config.py`
```python
PRESETS = {
    "anti-detect": { ... },
    "hifi-pure": { ... },
    "vocal": { ... },
    "tts": {
        "spectral_naturalize": 0.7,
        "noise_floor_shape": 0.55,
        "harmonic_deregularize": 0.5,
        "phase_naturalize": 0.3