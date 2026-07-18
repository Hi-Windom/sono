/**
 * WASM DSP 核心模块
 *
 * 纯 C 实现，无标准库依赖，可编译为 WebAssembly。
 * 包含常用 DSP 算法：增益、软削波、RMS、归一化、低通/高通滤波、
 * 降噪基础、STFT 辅助函数等。
 *
 * 构建命令：
 *   clang --target=wasm32 -O3 -nostdlib -Wl,--no-entry \
 *         -Wl,--export-all -Wl,--allow-undefined \
 *         -o dsp_core.wasm dsp_core.c
 */

#include <stdint.h>
#include <stddef.h>

#define WASM_EXPORT __attribute__((visibility("default")))
#define PI 3.14159265358979323846f

static float wasm_sqrtf(float x) {
    if (x <= 0.0f) return 0.0f;
    float guess = x * 0.5f;
    for (int i = 0; i < 10; i++) {
        guess = 0.5f * (guess + x / guess);
    }
    return guess;
}

static float wasm_fabsf(float x) {
    return x < 0.0f ? -x : x;
}

static float wasm_pow10(float x) {
    float result = 1.0f;
    if (x > 0) {
        for (int i = 0; i < (int)(x * 1000.0f); i++) {
            result *= 1.00230523807788f;
        }
    } else {
        for (int i = 0; i < (int)(-x * 1000.0f); i++) {
            result /= 1.00230523807788f;
        }
    }
    return result;
}

static float wasm_sinf(float x) {
    while (x > PI) x -= 2.0f * PI;
    while (x < -PI) x += 2.0f * PI;
    float x2 = x * x;
    float x3 = x2 * x;
    float x5 = x3 * x2;
    float x7 = x5 * x2;
    return x - x3 / 6.0f + x5 / 120.0f - x7 / 5040.0f;
}

static float wasm_cosf(float x) {
    while (x > PI) x -= 2.0f * PI;
    while (x < -PI) x += 2.0f * PI;
    float x2 = x * x;
    float x4 = x2 * x2;
    float x6 = x4 * x2;
    return 1.0f - x2 / 2.0f + x4 / 24.0f - x6 / 720.0f;
}

WASM_EXPORT
void apply_gain(float* buffer, size_t length, float gain_db) {
    if (gain_db == 0.0f) return;
    float gain_linear = wasm_pow10(gain_db / 20.0f);
    for (size_t i = 0; i < length; i++) {
        buffer[i] *= gain_linear;
    }
}

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

WASM_EXPORT
float compute_rms(const float* buffer, size_t length) {
    if (length == 0) return 0.0f;
    double sum = 0.0;
    for (size_t i = 0; i < length; i++) {
        sum += (double)buffer[i] * (double)buffer[i];
    }
    return (float)wasm_sqrtf((float)(sum / (double)length));
}

WASM_EXPORT
float compute_peak(const float* buffer, size_t length) {
    if (length == 0) return 0.0f;
    float peak = 0.0f;
    for (size_t i = 0; i < length; i++) {
        float abs_val = wasm_fabsf(buffer[i]);
        if (abs_val > peak) peak = abs_val;
    }
    return peak;
}

WASM_EXPORT
void normalize(float* buffer, size_t length, float target_peak) {
    if (length == 0 || target_peak <= 0.0f) return;
    float peak = 0.0f;
    for (size_t i = 0; i < length; i++) {
        float abs_val = wasm_fabsf(buffer[i]);
        if (abs_val > peak) peak = abs_val;
    }
    if (peak > 0.0f) {
        float gain = target_peak / peak;
        for (size_t i = 0; i < length; i++) {
            buffer[i] *= gain;
        }
    }
}

WASM_EXPORT
void dc_offset(float* buffer, size_t length, float offset) {
    for (size_t i = 0; i < length; i++) {
        buffer[i] += offset;
    }
}

WASM_EXPORT
void remove_dc(float* buffer, size_t length) {
    if (length == 0) return;
    double sum = 0.0;
    for (size_t i = 0; i < length; i++) {
        sum += buffer[i];
    }
    float dc = (float)(sum / (double)length);
    for (size_t i = 0; i < length; i++) {
        buffer[i] -= dc;
    }
}

WASM_EXPORT
void reverse_audio(float* buffer, size_t length) {
    for (size_t i = 0; i < length / 2; i++) {
        float tmp = buffer[i];
        buffer[i] = buffer[length - 1 - i];
        buffer[length - 1 - i] = tmp;
    }
}

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

typedef struct {
    float alpha;
    float x_prev;
    float y_prev;
} HighPassFilter;

WASM_EXPORT
void hpf_init(HighPassFilter* filter, float sample_rate, float cutoff_freq) {
    if (sample_rate <= 0.0f || cutoff_freq <= 0.0f) {
        filter->alpha = 0.1f;
    } else {
        float dt = 1.0f / sample_rate;
        float rc = 1.0f / (2.0f * PI * cutoff_freq);
        filter->alpha = rc / (rc + dt);
    }
    filter->x_prev = 0.0f;
    filter->y_prev = 0.0f;
}

WASM_EXPORT
void hpf_process(HighPassFilter* filter, float* buffer, size_t length) {
    float alpha = filter->alpha;
    float x_prev = filter->x_prev;
    float y_prev = filter->y_prev;
    for (size_t i = 0; i < length; i++) {
        float x = buffer[i];
        float y = alpha * (y_prev + x - x_prev);
        x_prev = x;
        y_prev = y;
        buffer[i] = y;
    }
    filter->x_prev = x_prev;
    filter->y_prev = y_prev;
}

WASM_EXPORT
void fade_in(float* buffer, size_t length, size_t fade_samples) {
    if (fade_samples == 0 || fade_samples > length) fade_samples = length;
    for (size_t i = 0; i < fade_samples; i++) {
        buffer[i] *= (float)i / (float)fade_samples;
    }
}

WASM_EXPORT
void fade_out(float* buffer, size_t length, size_t fade_samples) {
    if (fade_samples == 0 || fade_samples > length) fade_samples = length;
    for (size_t i = 0; i < fade_samples; i++) {
        buffer[length - 1 - i] *= (float)i / (float)fade_samples;
    }
}

WASM_EXPORT
void mix_buffers(float* dest, const float* src, size_t length, float mix_ratio) {
    for (size_t i = 0; i < length; i++) {
        dest[i] = dest[i] * (1.0f - mix_ratio) + src[i] * mix_ratio;
    }
}

WASM_EXPORT
float dot_product(const float* a, const float* b, size_t length) {
    double sum = 0.0;
    for (size_t i = 0; i < length; i++) {
        sum += (double)a[i] * (double)b[i];
    }
    return (float)sum;
}

WASM_EXPORT
void vector_scale(float* buffer, size_t length, float scalar) {
    for (size_t i = 0; i < length; i++) {
        buffer[i] *= scalar;
    }
}

WASM_EXPORT
void vector_add(float* dest, const float* src, size_t length) {
    for (size_t i = 0; i < length; i++) {
        dest[i] += src[i];
    }
}

WASM_EXPORT
void vector_sub(float* dest, const float* src, size_t length) {
    for (size_t i = 0; i < length; i++) {
        dest[i] -= src[i];
    }
}

WASM_EXPORT
void vector_mul(float* dest, const float* src, size_t length) {
    for (size_t i = 0; i < length; i++) {
        dest[i] *= src[i];
    }
}

static char heap[4 * 1024 * 1024];
static size_t heap_ptr = 0;

WASM_EXPORT
void* malloc(size_t size) {
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
}

WASM_EXPORT
size_t memory_used(void) {
    return heap_ptr;
}

WASM_EXPORT
size_t memory_total(void) {
    return sizeof(heap);
}

WASM_EXPORT
void memory_reset(void) {
    heap_ptr = 0;
}
