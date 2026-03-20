"""Routes administration — GET /models/status, /generation/status, POST /models/preload."""

import time
import logging

import torch
from fastapi import APIRouter

from config import (
    DEVICE, MODELS_DIR, CUSTOM_VOICES_DIR,
    GENERATION_QUEUE_TIMEOUT, GENERATION_TIMEOUT,
)
import models as _models_module
from models import (
    load_voice_design_model, load_voice_clone_model,
    load_preset_voice_model, load_clone_base_model,
    _get_gpu_memory_info,
)
from voices import voice_clone_prompts, custom_voices
import generation as _gen_module

logger = logging.getLogger("voxqwen")

router = APIRouter()


@router.get("/models/status", tags=["Informations"])
async def models_status():
    """Verifie le statut des modeles charges et des voix."""
    return {
        "voice_design_loaded": _models_module.voice_design_model is not None,
        "voice_clone_loaded": _models_module.voice_clone_model is not None,
        "preset_voice_loaded": _models_module.preset_voice_model is not None,
        "clone_1_7b_loaded": _models_module.clone_model_1_7b is not None,
        "clone_0_6b_loaded": _models_module.clone_model_0_6b is not None,
        "prompts_cached": len(voice_clone_prompts),
        "custom_voices_count": len(custom_voices),
        "custom_voices_loaded_in_memory": sum(1 for v in custom_voices.values() if v["prompt_items"] is not None),
        "device": DEVICE,
        "mps_available": torch.backends.mps.is_available(),
        "cuda_available": torch.cuda.is_available(),
        "models_dir": str(MODELS_DIR),
        "custom_voices_dir": str(CUSTOM_VOICES_DIR),
        "gpu_memory": _get_gpu_memory_info(),
    }


@router.get("/generation/status", tags=["Monitoring"])
async def generation_status():
    """Etat du moteur de generation en temps reel."""
    elapsed = None
    if _gen_module._generation_started_at:
        elapsed = round(time.time() - _gen_module._generation_started_at, 1)

    return {
        "busy": _gen_module._generation_active,
        "elapsed_seconds": elapsed,
        "endpoint": _gen_module._generation_endpoint,
        "queue_timeout": GENERATION_QUEUE_TIMEOUT,
        "generation_timeout": GENERATION_TIMEOUT,
        "stats": dict(_gen_module._generation_stats),
        "gpu_memory": _get_gpu_memory_info(),
    }


@router.post("/models/preload", tags=["Informations"])
async def preload_models(
    design: bool = False,
    clone: bool = False,
    preset: bool = True,
    clone_1_7b: bool = False,
    clone_0_6b: bool = False,
):
    """Pre-charge les modeles en memoire."""
    loaded = []

    if preset:
        load_preset_voice_model()
        loaded.append("preset_voice (0.6B-CustomVoice)")

    if design:
        load_voice_design_model()
        loaded.append("voice_design (1.7B-VoiceDesign)")

    if clone:
        load_voice_clone_model()
        loaded.append("voice_clone (1.7B-CustomVoice)")

    if clone_1_7b:
        load_clone_base_model("1.7B")
        loaded.append("clone_1_7b (1.7B-Base)")

    if clone_0_6b:
        load_clone_base_model("0.6B")
        loaded.append("clone_0_6b (0.6B-Base)")

    return {
        "status": "success",
        "loaded": loaded,
        "device": DEVICE
    }
