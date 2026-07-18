/**
 * WASM DSP 示例模块
 * 
 * 演示如何将 DSP 算法编译为 WebAssembly。
 * 构建命令：
 *   clang --target=wasm32 -O3 -nostdlib -Wl,--no-entry \
 *         -Wl,--export-all -Wl,--allow-undefined \
 *         -o dsp_example.wasm dsp_example.c
 */

#include <stdint.h>
#include <stddef.h>
#include <math.h>

#define WASM_EXPORT __attribute__((visibility("default")))

#define PI 3.14159265358979323846

// 简单的增益处理
WASM_EXPORT
void apply_gain(float* buffer, size_t length, float gain_db) {
    float gain_linear = 1.0f;
    if (gain_db != 0.0f) {
        gain_linear = 1.0f;
        // 简单的 dB 转线性（避免依赖 math.h 的 pow）
        float db = gain_db;
        if (db > 0) {
            for (int i = 0; i < (int)(db * 10); i++) {
                gain_linear *= 1.000115f; // 近似 10^(0.1/20)
            }
        } else {
            gain_linear = 1.0f;
            for (int i = 0; i < (int)(-db * 10); i++) {
                gain_linear /= 1.000115f;
            }
        }
    }
    
    for (size_t i = 0; i < length; i++) {
        buffer[i] *= gain_linear;
    }
}

// 软削波
WASM_EXPORT
void soft_clip(float* buffer, size_t length, float threshold) {
    if (threshold <= 0.0f) threshold = 0.95f;
    
    for (size_t i = 0; i < length; i++) {
        float x = buffer[i];
        if (x > threshold) {
            buffer[i] = threshold + (x - threshold) * 0.3f;
        } else if (x < -threshold) {
            buffer[i] = -threshold + (x + threshold) * 0.3f;
        }
    }
}

// 计算 RMS
WASM_EXPORT
float compute_rms(const float* buffer, size_t length) {
    if (length == 0) return 0.0f;
    
    double sum = 0.0;
    for (size_t i = 0; i < length; i++) {
        sum += (double)buffer[i] * (double)buffer[i];
    }
    return (float)sqrt(sum / (double)length);
}

// 归一化
WASM_EXPORT
void normalize(float* buffer, size_t length, float target_peak) {
    if (length == 0 || target_peak <= 0.0f) return;
    
    float peak = 0.0f;
    for (size_t i = 0; i < length; i++) {
        float abs_val = buffer[i] >= 0 ? buffer[i] : -buffer[i];
        if (abs_val > peak) peak = abs_val;
    }
    
    if (peak > 0.0f) {
        float gain = target_peak / peak;
        for (size_t i = 0; i < length; i++) {
            buffer[i] *= gain;
        }
    }
}

// 简单的一阶低通滤波器
typedef struct {
    float alpha;
    float y_prev;
} LowPassFilter;

WASM_EXPORT
void lpf_init(LowPassFilter* filter, float sample_rate, float cutoff_freq) {
    if (sample_rate <= 0.0f || cutoff_freq <= 0.0f) {
        filter->alpha = 0.1f;
    } else {
        float dt = 1.0f / sample_rate;
        float rc = 1.0f / (2.0f * PI * cutoff_freq);
        filter->alpha = dt / (rc + dt);
    }
    filter->y_prev = 0.0f;
}

WASM_EXPORT
void lpf_process(LowPassFilter* filter, float* buffer, size_t length) {
    float alpha = filter->alpha;
    float y = filter->y_prev;
    
    for (size_t i = 0; i < length; i++) {
        y = y + alpha * (buffer[i] - y);
        buffer[i] = y;
    }
    
    filter->y_prev = y;
}

// 内存分配（简单的 bump allocator）
static char heap[1024 * 1024]; // 1MB heap
static size_t heap_ptr = 0;

WASM_EXPORT
void* malloc(size_t size) {
    // 对齐到 8 字节
    size = (size + 7) & ~7;
    
    if (heap_ptr + size > sizeof(heap)) {
        return (void*)0;
    }
    
    void* ptr = &heap[heap_ptr];
    heap_ptr += size;
    return ptr;
}

WASM_EXPORT
void free(void* ptr) {
    // 简单实现：不释放内存
}
