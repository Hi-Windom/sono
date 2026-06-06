# Checklist

## 后端 — v3.1/v3.1a 算法
- [x] `backend/services/repair/repair_v3_1/__init__.py` 创建正确
- [x] `backend/services/repair/repair_v3_1/core.py` 包含增强型 AI 人声修复、激励器、压缩器、齿音抑制、空间感、温暖度、伴奏立体声增强、三种母带风格
- [x] `backend/services/repair/repair_v3_1a/__init__.py` 创建正确
- [x] `backend/services/repair/repair_v3_1a/core.py` 包含精简版增强功能
- [x] `backend/services/audio_repair.py` 中 ALGORITHM_VERSIONS 注册了 v3.1/v3.1a
- [x] `backend/services/memory_guard.py` 包含 v3.1/v3.1a 内存估算
- [x] v3.1/v3.1a 修复后音频质量不低于 v3.0/v3.0a

## 后端 — 交付渲染列表 API
- [x] `GET /api/v1/delivery-files` 返回正确的文件列表，含父子关系
- [x] `DELETE /api/v1/delivery-files/{filename}` 正确删除单个文件
- [x] `DELETE /api/v1/delivery-files/parent/{filename}` 级联删除父项及所有子项
- [x] 双轨 render 端点自动生成三个交付文件（人声轨、伴奏轨、合并轨）

## 前端 — backendApi.ts
- [x] VocalRepairParams 增加 exciter/compressor/spatial/warmth 字段
- [x] InstrumentRepairParams 增加 stereo_enhance 字段
- [x] ProcessingOptions 增加 masteringStyle 字段
- [x] DeliveryFile 接口定义正确
- [x] fetchDeliveryFiles() / deleteDeliveryFile() / deleteDeliveryParent() 函数实现正确
- [x] ALGORITHM_VERSIONS 包含 v3.1/v3.1a

## 前端 — AIRepairPanel v3.1 面板
- [x] v3.1/v3.1a 人声参数面板显示新效果器控件
- [x] v3.1/v3.1a 伴奏参数面板显示立体声增强控件
- [x] 母带风格选择器（标准/强劲/温暖）正常工作
- [x] 渲染请求参数包含 mastering_style 和新效果器参数

## 前端 — CacheManagerPage 交付渲染 Tab
- [x] 第 4 个 Tab「交付渲染」存在且可切换
- [x] 列表显示所有交付渲染文件
- [x] 合并轨作为父项，可展开显示子项
- [x] 下载按钮正常工作
- [x] 删除子项仅删自身
- [x] 删除父项级联删除所有子项
- [x] 无交付文件时显示空状态提示