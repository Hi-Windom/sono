DEFAULT_PARAMS = {
    "spectral_naturalize": 0.0,
    "noise_floor_shape": 0.0,
    "harmonic_deregularize": 0.0,
    "phase_naturalize": 0.0,
    "transient_protect": 0.0,
    "dynamic_naturalize": 0.0,
}

ERB_N_BANDS = 28
HOP_LENGTH = 512
N_FFT = 2048
DESKTOP_WORKING_SR = 48000

PRESETS = {
    "anti-detect": {
        "spectral_naturalize": 0.7,
        "noise_floor_shape": 0.6,
        "harmonic_deregularize": 0.5,
        "phase_naturalize": 0.8,
        "transient_protect": 0.3,
        "dynamic_naturalize": 0.4,
    },
    "hifi-pure": {
        "spectral_naturalize": 0.3,
        "noise_floor_shape": 0.2,
        "harmonic_deregularize": 0.1,
        "phase_naturalize": 0.4,
        "transient_protect": 0.9,
        "dynamic_naturalize": 0.2,
    },
    "vocal": {
        "spectral_naturalize": 0.5,
        "noise_floor_shape": 0.4,
        "harmonic_deregularize": 0.3,
        "phase_naturalize": 0.6,
        "transient_protect": 0.7,
        "dynamic_naturalize": 0.5,
    },
}