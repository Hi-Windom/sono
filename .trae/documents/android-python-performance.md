# 安卓 Python 后端性能优化方案

## 现状分析

当前安卓部署架构：
- **运行方式**：Termux + CPython 解释器 + py 源码直接运行
- **启动**：`python main.py` → uvicorn 单进程单线程
- **核心依赖**：numpy/scipy（pkg 预编译）、fastapi、uvicorn、miniaudio、soundfile
- **DSP 核心**：`dsp_utils.py`（纯 numpy+scipy，~600行），已有 C 原生库 `dsp_native/` 但实际未使用（所有 native 函数都 fallback 到 Python）
- **修复算法**：v1.0~v2.3a 共 8 个版本，热路径 v2.3a ~500行
- **线程模型**：ThreadPoolExecutor(max_workers=4) + 单 uvicorn worker
- **内存优化**：已有 streaming_spectral_process（流式分块）、float32 自动降精度

## 实施步骤

### 步骤1：延迟 import — 加速启动

**文件：`backend/services/audio_repair.py`**
- 将顶部 8 个 `from services.repair.xxx import repair_audio as xxx` 改为函数内延迟 import
- 新增 `_REPAIR_MODULES` 字典映射版本名到模块路径
- `repair_audio()` 函数内按需 import，首次调用时加载

**文件：`backend/services/dsp_utils.py`**
- 将 `from scipy.signal import get_window, medfilt` 改为函数内 import
- 将 `from scipy.fftpack import dct` 改为函数内 import

**文件：`backend/services/render.py`**
- 将 `from scipy.signal import butter, sosfiltfilt, resample_poly` 改为函数内 import

### 步骤2：启用 dsp_native C 原生库 — 加速 DSP 运算

**文件：`backend/services/dsp_native/__init__.py`**
- 实现 `stft_native()` 的 ctypes 绑定：
  - 设置 `lib.stft_execute.argtypes` 和 `restype`
  - 分配 ctypes 数组，调用 C 函数，转换回 numpy
- 同理实现 `istft_native()`、`compressor_native()`、`peak_limiter_native()`

**文件：`backend/services/dsp_utils.py`**
- 在 `stft()` 和 `istft()` 开头检查 native 可用性
- 可用时调用 `dsp_native.stft_native()`，否则 fallback 到 numpy

**文件：`deploy/setup_android.sh`**
- 在安装依赖后，编译 C 库：`cd backend/services/dsp_native && make && make install`

### 步骤3：预编译 .pyc

**文件：`scripts/build_android_release.sh`**
- 在打包前添加：`python -m compileall backend/`
- 确保 .pyc 文件被打包

### 步骤4：构建验证 + 打包

- `npm run build` 无报错
- `python -m pytest backend/tests/test_repair_quality.py -v` 质量测试通过
- `bash scripts/build_android_release.sh` 打包成功

## 风险评估

| 优化项 | 风险 | 缓解措施 |
|--------|------|----------|
| 延迟 import | 低：首次调用时可能慢几ms | 不影响用户体验，修复本身需要数秒 |
| 启用 C 原生库 | 中：ctypes 绑定可能有数值差异 | 对比测试 native vs numpy 结果，差异 < 1e-6 才启用 |
| 预编译 .pyc | 极低：Python 标准功能 | 无需缓解 |
