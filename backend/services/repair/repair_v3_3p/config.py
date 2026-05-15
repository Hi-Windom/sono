DEFAULT_PARAMS = {
    "spectral_naturalize": 0.0,
    "noise_floor_shape": 0.0,
    "harmonic_deregularize": 0.0,
    "phase_naturalize": 0.0,
    "transient_protect": 0.0,
    "dynamic_naturalize": 0.0,
    "f0_guided_depth": 0.0,
    "perceptual_weight": 0.0,
}

PRESETS = {
    "anti-detect": {
        "spectral_naturalize": 0.85,
        "noise_floor_shape": 0.7,
        "harmonic_deregularize": 0.8,
        "phase_naturalize": 0.75,
        "transient_protect": 0.3,
        "dynamic_naturalize": 0.4,
        "f0_guided_depth": 0.6,
        "perceptual_weight": 0.7,
    },
    "hifi-pure": {
        "spectral_naturalize": 0.4,
        "noise_floor_shape": 0.2,
        "harmonic_deregularize": 0.15,
        "phase_naturalize": 0.3,
        "transient_protect": 0.8,
        "dynamic_naturalize": 0.3,
        "f0_guided_depth": 0.3,
        "perceptual_weight": 0.4,
    },
    "vocal": {
        "spectral_naturalize": 0.6,
        "noise_floor_shape": 0.4,
        "harmonic_deregularize": 0.5,
        "phase_naturalize": 0.4,
        "transient_protect": 0.7,
        "dynamic_naturalize": 0.5,
        "f0_guided_depth": 0.8,
        "perceptual_weight": 0.6,
    },
}

ERB_N_BANDS = 32
HOP_LENGTH = 512
N_FFT = 2048
DESKTOP_WORKING_SR = 48000
