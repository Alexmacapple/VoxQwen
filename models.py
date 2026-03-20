"""
Chargement et gestion des modeles TTS — lazy loading, cleanup GPU.

Dependances : config.py
"""

import gc
import logging

import torch

from config import DEVICE, MODELS_DIR, GPU_CLEANUP_DELAY

logger = logging.getLogger("voxqwen")

# ── Variables globales modeles (charges a la demande) ────────────────────────

voice_design_model = None
voice_clone_model = None   # 1.7B-CustomVoice pour /preset/instruct
preset_voice_model = None

# Modeles Base pour clonage (avec create_voice_clone_prompt)
clone_model_1_7b = None  # 1.7B-Base
clone_model_0_6b = None  # 0.6B-Base

_gpu_cleanup_scheduled = False

# ── GPU Cache ────────────────────────────────────────────────────────────────


def _try_empty_gpu_cache():
    """Tente de vider le cache GPU (safe, ignore les erreurs)."""
    try:
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        elif torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _deferred_gpu_cleanup(endpoint: str):
    """Nettoie la VRAM GPU apres un timeout."""
    global _gpu_cleanup_scheduled
    try:
        _try_empty_gpu_cache()
        gc.collect()
        logger.info(f"GPU cleanup differe OK (post-timeout {endpoint})")
    except Exception as e:
        logger.warning(f"GPU cleanup differe echoue: {e}")
    finally:
        _gpu_cleanup_scheduled = False


def _get_gpu_memory_info() -> dict:
    """Retourne les infos memoire GPU si disponibles."""
    info = {"device": DEVICE, "available": False}
    try:
        if DEVICE == "mps":
            if hasattr(torch.mps, "current_allocated_memory"):
                info["allocated_mb"] = round(torch.mps.current_allocated_memory() / 1024 / 1024, 1)
                info["available"] = True
            if hasattr(torch.mps, "driver_allocated_memory"):
                info["driver_allocated_mb"] = round(torch.mps.driver_allocated_memory() / 1024 / 1024, 1)
        elif DEVICE.startswith("cuda"):
            info["allocated_mb"] = round(torch.cuda.memory_allocated() / 1024 / 1024, 1)
            info["reserved_mb"] = round(torch.cuda.memory_reserved() / 1024 / 1024, 1)
            info["available"] = True
    except Exception:
        pass
    return info


# ── Chargeurs de modeles ─────────────────────────────────────────────────────


def load_voice_design_model():
    """Charge le modele Voice Design."""
    global voice_design_model
    if voice_design_model is None:
        logger.info("Chargement Voice Design...")

        from qwen_tts import Qwen3TTSModel

        model_path = MODELS_DIR / "1.7B-VoiceDesign"
        voice_design_model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=DEVICE,
            dtype=torch.float16,
        )
        logger.info(f"Voice Design charge ({DEVICE})")
    return voice_design_model


def load_voice_clone_model():
    """Charge le modele Voice Clone."""
    global voice_clone_model
    if voice_clone_model is None:
        logger.info("Chargement Voice Clone...")

        from qwen_tts import Qwen3TTSModel

        model_path = MODELS_DIR / "1.7B-CustomVoice"
        voice_clone_model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=DEVICE,
            dtype=torch.float16,
        )
        logger.info(f"Voice Clone charge ({DEVICE})")
    return voice_clone_model


def load_preset_voice_model():
    """Charge le modele Preset Voice (0.6B-CustomVoice)."""
    global preset_voice_model
    if preset_voice_model is None:
        logger.info("Chargement Preset Voice...")

        from qwen_tts import Qwen3TTSModel

        model_path = MODELS_DIR / "0.6B-CustomVoice"
        preset_voice_model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=DEVICE,
            dtype=torch.float32,
        )
        logger.info(f"Preset Voice charge ({DEVICE})")
    return preset_voice_model


def load_clone_base_model(model_size: str = "1.7B"):
    """
    Charge le modele Base pour le clonage vocal.

    Les modeles Base supportent create_voice_clone_prompt() contrairement aux CustomVoice.
    """
    global clone_model_1_7b, clone_model_0_6b

    if model_size == "1.7B":
        if clone_model_1_7b is None:
            logger.info("Chargement 1.7B-Base...")

            from qwen_tts import Qwen3TTSModel

            model_path = MODELS_DIR / "1.7B-Base"
            clone_model_1_7b = Qwen3TTSModel.from_pretrained(
                str(model_path),
                device_map=DEVICE,
                dtype=torch.float16,
            )
            logger.info(f"1.7B-Base charge ({DEVICE})")
        return clone_model_1_7b

    elif model_size == "0.6B":
        if clone_model_0_6b is None:
            logger.info("Chargement 0.6B-Base...")

            from qwen_tts import Qwen3TTSModel

            model_path = MODELS_DIR / "0.6B-Base"
            clone_model_0_6b = Qwen3TTSModel.from_pretrained(
                str(model_path),
                device_map=DEVICE,
                dtype=torch.float32,
            )
            logger.info(f"0.6B-Base charge ({DEVICE})")
        return clone_model_0_6b

    else:
        raise ValueError(f"model_size doit etre '1.7B' ou '0.6B', pas '{model_size}'")
