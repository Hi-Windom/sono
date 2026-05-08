# Checklist

## 语法检查

- [ ] spectral_combined.py 通过 `python -m py_compile` 检查
- [ ] spectral_group_a.py 通过 `python -m py_compile` 检查
- [ ] transient.py 通过 `python -m py_compile` 检查
- [ ] core.py 通过 `python -m py_compile` 检查
- [ ] 无运行时导入错误

## 功能检查

- [ ] 频谱修复功能正常
- [ ] 瞬态修复功能正常
- [ ] 合并处理功能正常
- [ ] 处理音频不崩溃
- [ ] 输出音频质量可接受

## 性能检查

- [ ] 频谱修复达到 3x+ 提速
- [ ] 瞬态修复达到 3x+ 提速
- [ ] 整体处理时间显著减少

## Termux 兼容性检查

- [ ] 无 numba 依赖
- [ ] 所有依赖可在 Termux 安装
- [ ] 服务启动无 ModuleNotFoundError

## 打包检查

- [ ] Android 发布包生成成功
- [ ] 包大小合理
