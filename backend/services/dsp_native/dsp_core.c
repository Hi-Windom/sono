/*
 * DSP Core Library - C implementation for accelerated audio processing
 * Optimized for ARM/Termux environments
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <complex.h>

#ifdef __ARM_NEON
#include <arm_neon.h>
#endif

#define PI 3.14159265358979323846
#define TWO_PI 6.28318530717958647692

/* FFT structure */
typedef struct {
    int n;
    int *bit_reverse;
    double *cos_table;
    double *sin_table;
} FFTContext;

/* Initialize FFT context */
FFTContext* fft_init(int n) {
    FFTContext *ctx = (FFTContext*)malloc(sizeof(FFTContext));
    ctx->n = n;
    ctx->bit_reverse = (int*)malloc(n * sizeof(int));
    ctx->cos_table = (double*)malloc(n * sizeof(double));
    ctx->sin_table = (double*)malloc(n * sizeof(double));

    /* Bit reversal table */
    int bits = 0;
    int temp = n;
    while (temp > 1) {
        bits++;
        temp >>= 1;
    }

    for (int i = 0; i < n; i++) {
        int j = 0;
        for (int k = 0; k < bits; k++) {
            j = (j << 1) | ((i >> k) & 1);
        }
        ctx->bit_reverse[i] = j;
    }

    /* Twiddle factors */
    for (int i = 0; i < n / 2; i++) {
        double angle = -TWO_PI * i / n;
        ctx->cos_table[i] = cos(angle);
        ctx->sin_table[i] = sin(angle);
    }

    return ctx;
}

/* Free FFT context */
void fft_free(FFTContext *ctx) {
    if (ctx) {
        free(ctx->bit_reverse);
        free(ctx->cos_table);
        free(ctx->sin_table);
        free(ctx);
    }
}

/* In-place complex FFT */
void fft_execute(FFTContext *ctx, double *real, double *imag) {
    int n = ctx->n;
    double *temp_real = (double*)malloc(n * sizeof(double));
    double *temp_imag = (double*)malloc(n * sizeof(double));

    /* Bit reversal permutation */
    for (int i = 0; i < n; i++) {
        temp_real[i] = real[ctx->bit_reverse[i]];
        temp_imag[i] = imag[ctx->bit_reverse[i]];
    }

    /* Cooley-Tukey FFT */
    for (int stage = 1; stage < n; stage <<= 1) {
        int step = stage << 1;
        for (int group = 0; group < stage; group++) {
            int idx = group * n / step;
            double wr = ctx->cos_table[idx];
            double wi = ctx->sin_table[idx];

            for (int pair = group; pair < n; pair += step) {
                int match = pair + stage;
                double tr = temp_real[match] * wr - temp_imag[match] * wi;
                double ti = temp_real[match] * wi + temp_imag[match] * wr;

                temp_real[match] = temp_real[pair] - tr;
                temp_imag[match] = temp_imag[pair] - ti;
                temp_real[pair] += tr;
                temp_imag[pair] += ti;
            }
        }
    }

    memcpy(real, temp_real, n * sizeof(double));
    memcpy(imag, temp_imag, n * sizeof(double));

    free(temp_real);
    free(temp_imag);
}

/* Inverse FFT */
void ifft_execute(FFTContext *ctx, double *real, double *imag) {
    int n = ctx->n;

    /* Conjugate */
    for (int i = 0; i < n; i++) {
        imag[i] = -imag[i];
    }

    fft_execute(ctx, real, imag);

    /* Conjugate and scale */
    double scale = 1.0 / n;
    for (int i = 0; i < n; i++) {
        real[i] *= scale;
        imag[i] *= -imag[i] * scale;
    }
}

/* STFT - Short Time Fourier Transform */
int stft_execute(const float *input, int input_len,
                 float *output_real, float *output_imag,
                 int n_fft, int hop_length,
                 const float *window) {
    int n_frames = (input_len - n_fft) / hop_length + 1;
    int fft_bins = n_fft / 2 + 1;

    FFTContext *ctx = fft_init(n_fft);

    double *frame_real = (double*)malloc(n_fft * sizeof(double));
    double *frame_imag = (double*)malloc(n_fft * sizeof(double));

    for (int i = 0; i < n_frames; i++) {
        int start = i * hop_length;

        /* Apply window and convert to double */
        for (int j = 0; j < n_fft; j++) {
            frame_real[j] = input[start + j] * window[j];
            frame_imag[j] = 0.0;
        }

        fft_execute(ctx, frame_real, frame_imag);

        /* Store output (only positive frequencies) */
        for (int j = 0; j < fft_bins; j++) {
            output_real[i * fft_bins + j] = (float)frame_real[j];
            output_imag[i * fft_bins + j] = (float)frame_imag[j];
        }
    }

    free(frame_real);
    free(frame_imag);
    fft_free(ctx);

    return n_frames;
}

/* ISTFT - Inverse Short Time Fourier Transform */
int istft_execute(const float *input_real, const float *input_imag,
                  float *output, int output_len,
                  int n_fft, int hop_length,
                  const float *window) {
    int n_frames = (output_len - n_fft) / hop_length + 1;
    int fft_bins = n_fft / 2 + 1;

    FFTContext *ctx = fft_init(n_fft);

    double *frame_real = (double*)malloc(n_fft * sizeof(double));
    double *frame_imag = (double*)malloc(n_fft * sizeof(double));

    /* Clear output */
    memset(output, 0, output_len * sizeof(float));

    float *window_sum = (float*)calloc(output_len, sizeof(float));

    for (int i = 0; i < n_frames; i++) {
        int start = i * hop_length;

        /* Load input (positive frequencies) */
        for (int j = 0; j < fft_bins; j++) {
            frame_real[j] = input_real[i * fft_bins + j];
            frame_imag[j] = input_imag[i * fft_bins + j];
        }

        /* Mirror negative frequencies */
        for (int j = fft_bins; j < n_fft; j++) {
            frame_real[j] = frame_real[n_fft - j];
            frame_imag[j] = -frame_imag[n_fft - j];
        }

        ifft_execute(ctx, frame_real, frame_imag);

        /* Overlap-add with window */
        for (int j = 0; j < n_fft; j++) {
            output[start + j] += (float)(frame_real[j] * window[j]);
            window_sum[start + j] += window[j] * window[j];
        }
    }

    /* Normalize by window sum */
    for (int i = 0; i < output_len; i++) {
        if (window_sum[i] > 1e-10f) {
            output[i] /= window_sum[i];
        }
    }

    free(frame_real);
    free(frame_imag);
    free(window_sum);
    fft_free(ctx);

    return n_frames;
}

/* Fast FIR filter using FFT convolution */
void fir_filter_fft(const float *input, float *output, int len,
                    const float *kernel, int kernel_len) {
    int n_fft = 1;
    while (n_fft < len + kernel_len - 1) {
        n_fft <<= 1;
    }

    FFTContext *ctx = fft_init(n_fft);

    double *in_real = (double*)calloc(n_fft, sizeof(double));
    double *in_imag = (double*)calloc(n_fft, sizeof(double));
    double *kern_real = (double*)calloc(n_fft, sizeof(double));
    double *kern_imag = (double*)calloc(n_fft, sizeof(double));

    /* Load input and kernel */
    for (int i = 0; i < len; i++) {
        in_real[i] = input[i];
    }
    for (int i = 0; i < kernel_len; i++) {
        kern_real[i] = kernel[i];
    }

    /* FFT both */
    fft_execute(ctx, in_real, in_imag);
    fft_execute(ctx, kern_real, kern_imag);

    /* Multiply in frequency domain */
    for (int i = 0; i < n_fft; i++) {
        double a = in_real[i], b = in_imag[i];
        double c = kern_real[i], d = kern_imag[i];
        in_real[i] = a * c - b * d;
        in_imag[i] = a * d + b * c;
    }

    /* IFFT */
    ifft_execute(ctx, in_real, in_imag);

    /* Copy result */
    for (int i = 0; i < len; i++) {
        output[i] = (float)in_real[i];
    }

    free(in_real);
    free(in_imag);
    free(kern_real);
    free(kern_imag);
    fft_free(ctx);
}

/* Vectorized compressor with lookahead */
void compressor_process(const float *input, float *output, int len,
                        float threshold, float ratio,
                        float attack_ms, float release_ms,
                        int sample_rate) {
    float attack_coeff = (float)exp(-1.0 / (attack_ms * 0.001 * sample_rate));
    float release_coeff = (float)exp(-1.0 / (release_ms * 0.001 * sample_rate));

    float envelope = 0.0f;
    float threshold_lin = (float)pow(10.0, threshold / 20.0);

    for (int i = 0; i < len; i++) {
        float abs_sample = fabsf(input[i]);

        /* Envelope follower */
        if (abs_sample > envelope) {
            envelope = attack_coeff * envelope + (1.0f - attack_coeff) * abs_sample;
        } else {
            envelope = release_coeff * envelope + (1.0f - release_coeff) * abs_sample;
        }

        /* Gain computation */
        float gain = 1.0f;
        if (envelope > threshold_lin) {
            float over_db = 20.0f * log10f(envelope / threshold_lin);
            float compressed_db = over_db / ratio;
            gain = powf(10.0f, (compressed_db - over_db) / 20.0f);
        }

        output[i] = input[i] * gain;
    }
}

/* Multi-band compressor */
void multiband_compressor(const float *input, float *output, int len,
                          const float *low_band, const float *mid_band, const float *high_band,
                          int sample_rate) {
    /* This is a simplified version - full implementation would need filter banks */
    float *low_out = (float*)malloc(len * sizeof(float));
    float *mid_out = (float*)malloc(len * sizeof(float));
    float *high_out = (float*)malloc(len * sizeof(float));

    /* Compress each band */
    compressor_process(low_band, low_out, len, -20.0f, 3.0f, 10.0f, 100.0f, sample_rate);
    compressor_process(mid_band, mid_out, len, -18.0f, 2.5f, 5.0f, 80.0f, sample_rate);
    compressor_process(high_band, high_out, len, -16.0f, 2.0f, 3.0f, 60.0f, sample_rate);

    /* Sum bands */
    for (int i = 0; i < len; i++) {
        output[i] = low_out[i] + mid_out[i] + high_out[i];
    }

    free(low_out);
    free(mid_out);
    free(high_out);
}

/* Peak limiter with lookahead */
void peak_limiter(const float *input, float *output, int len,
                  float threshold_db, float attack_ms, float release_ms,
                  int sample_rate) {
    float threshold = powf(10.0f, threshold_db / 20.0f);
    float attack_coeff = expf(-1.0f / (attack_ms * 0.001f * sample_rate));
    float release_coeff = expf(-1.0f / (release_ms * 0.001f * sample_rate));

    float envelope = 0.0f;

    for (int i = 0; i < len; i++) {
        float abs_sample = fabsf(input[i]);

        /* Envelope follower */
        if (abs_sample > envelope) {
            envelope = attack_coeff * envelope + (1.0f - attack_coeff) * abs_sample;
        } else {
            envelope = release_coeff * envelope + (1.0f - release_coeff) * abs_sample;
        }

        /* Gain reduction */
        float gain = 1.0f;
        if (envelope > threshold) {
            gain = threshold / envelope;
        }

        output[i] = input[i] * gain;
    }
}

/* Vector addition with NEON optimization */
void vector_add(const float *a, const float *b, float *out, int len) {
#ifdef __ARM_NEON
    int i = 0;
    for (; i <= len - 4; i += 4) {
        float32x4_t va = vld1q_f32(&a[i]);
        float32x4_t vb = vld1q_f32(&b[i]);
        float32x4_t vout = vaddq_f32(va, vb);
        vst1q_f32(&out[i], vout);
    }
    for (; i < len; i++) {
        out[i] = a[i] + b[i];
    }
#else
    for (int i = 0; i < len; i++) {
        out[i] = a[i] + b[i];
    }
#endif
}

/* Vector multiplication with NEON optimization */
void vector_mul(const float *a, const float *b, float *out, int len) {
#ifdef __ARM_NEON
    int i = 0;
    for (; i <= len - 4; i += 4) {
        float32x4_t va = vld1q_f32(&a[i]);
        float32x4_t vb = vld1q_f32(&b[i]);
        float32x4_t vout = vmulq_f32(va, vb);
        vst1q_f32(&out[i], vout);
    }
    for (; i < len; i++) {
        out[i] = a[i] * b[i];
    }
#else
    for (int i = 0; i < len; i++) {
        out[i] = a[i] * b[i];
    }
#endif
}

/* Scalar multiplication with NEON optimization */
void vector_scale(const float *input, float scale, float *output, int len) {
#ifdef __ARM_NEON
    int i = 0;
    float32x4_t vscale = vdupq_n_f32(scale);
    for (; i <= len - 4; i += 4) {
        float32x4_t vin = vld1q_f32(&input[i]);
        float32x4_t vout = vmulq_f32(vin, vscale);
        vst1q_f32(&output[i], vout);
    }
    for (; i < len; i++) {
        output[i] = input[i] * scale;
    }
#else
    for (int i = 0; i < len; i++) {
        output[i] = input[i] * scale;
    }
#endif
}

/* Hann window generation */
void generate_hann_window(float *window, int len) {
    for (int i = 0; i < len; i++) {
        window[i] = 0.5f - 0.5f * cosf(TWO_PI * i / (len - 1));
    }
}

/* RMS computation with NEON optimization */
float compute_rms(const float *input, int len) {
    float sum = 0.0f;

#ifdef __ARM_NEON
    int i = 0;
    float32x4_t vsum = vdupq_n_f32(0.0f);
    for (; i <= len - 4; i += 4) {
        float32x4_t vin = vld1q_f32(&input[i]);
        vsum = vmlaq_f32(vsum, vin, vin);
    }
    float32x2_t vsum2 = vadd_f32(vget_low_f32(vsum), vget_high_f32(vsum));
    sum = vget_lane_f32(vpadd_f32(vsum2, vsum2), 0);
    for (; i < len; i++) {
        sum += input[i] * input[i];
    }
#else
    for (int i = 0; i < len; i++) {
        sum += input[i] * input[i];
    }
#endif

    return sqrtf(sum / len);
}
