VOCAL_KEY_MAP = {
    "de_clipping": "vocal_declip",
    "de_pop": "vocal_depop",
    "de_essing": "vocal_de_ess",
    "bass_enhance": "vocal_bass_enhance",
    "clarity": "vocal_air_texture",
    "air_texture": "vocal_air_texture",
    "formant_repair": "vocal_formant_repair",
    "breath_enhance": "vocal_breath_enhance",
    "ai_repair": "vocal_ai_repair",
    "exciter": "vocal_exciter",
    "compressor": "vocal_compressor",
    "spatial": "vocal_spatial",
    "warmth": "vocal_warmth",
    "de_esser_advanced": "vocal_de_esser_advanced",
    "ai_repair_enhanced": "vocal_ai_repair_enhanced",
    "ai_repair_enhanced_lite": "vocal_ai_repair_enhanced_lite",
    "loudness_optimize": "vocal_loudness",
    "smart_compressor": "vocal_smart_compressor",
    "transient_aware": "vocal_transient_aware",
    "resonance_suppress": "vocal_resonance_suppress",
    "ai_repair_adaptive": "vocal_ai_repair_adaptive",
    "exciter_improved": "vocal_exciter_improved",
    "de_esser_improved": "vocal_de_esser_improved",
}

INST_KEY_MAP = {
    "de_clipping": "inst_declip",
    "de_pop": "inst_depop",
    "noise_reduction": "inst_noise_reduction",
    "dynamic_range": "inst_dynamic",
    "spatial_enhance": "inst_spatial",
    "warmth": "inst_warmth",
    "timbre_protect": "inst_timbre_protect",
    "stereo_enhance": "inst_stereo_enhance",
    "loudness_optimize": "inst_loudness",
    "exciter": "inst_exciter",
    "compressor": "inst_compressor",
    "de_esser_advanced": "inst_de_esser_advanced",
    "ai_repair_enhanced": "inst_ai_repair_enhanced",
    "ai_repair_enhanced_lite": "inst_ai_repair_enhanced_lite",
    "exciter_lite": "inst_exciter_lite",
    "compressor_lite": "inst_compressor_lite",
    "transient": "inst_transient",
    "resonance": "inst_resonance",
    "bass_enhance": "inst_bass_enhance",
    "air_texture": "inst_air_texture",
    "clarity": "inst_clarity",
}

DUAL_REPAIR_PARAM_KEYS = set(VOCAL_KEY_MAP.values()) | set(INST_KEY_MAP.values()) | {
    "vocal_ratio", "accompaniment_ratio", "mastering_style", "algorithm_version", "speed",
}

SINGLE_REPAIR_PARAM_KEYS = {
    "de_clipping", "noise_reduction", "de_essing", "de_crackle", "de_pop",
    "harmonic_enhance", "dynamic_range", "softness", "presence_boost",
    "bass_enhance", "spatial_enhance", "transient_repair", "warmth", "clarity",
    "algorithm_version",
    "declip", "depop", "de_ess", "formant_repair", "breath_enhance",
    "ai_repair", "air_texture", "dynamic", "spatial", "loudness",
    "exciter", "compressor", "stereo_enhance", "mastering_style",
    "de_esser_advanced", "ai_repair_enhanced", "ai_repair_enhanced_lite",
}


def flatten_vocal_params(vocal_params: dict) -> dict:
    return {flat_key: vocal_params[src_key]
            for src_key, flat_key in VOCAL_KEY_MAP.items()
            if src_key in vocal_params}


def flatten_inst_params(inst_params: dict) -> dict:
    return {flat_key: inst_params[src_key]
            for src_key, flat_key in INST_KEY_MAP.items()
            if src_key in inst_params}