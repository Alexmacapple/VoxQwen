"""Routes sante et informations — GET /, /health, /languages."""

import logging

import torch
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import (
    DEVICE, API_VERSION, LANGUAGE_MAP, MODELS_DIR, CUSTOM_VOICES_DIR,
)
from schemas import LanguagesResponse

logger = logging.getLogger("voxqwen")

router = APIRouter()


@router.get("/", tags=["Sante"])
async def root():
    """Verification de l'etat du serveur."""
    return {
        "status": "ok",
        "service": "TTS-Alex",
        "device": DEVICE,
        "models": {
            "voice_design": "1.7B-VoiceDesign",
            "voice_clone": "1.7B-Base (qualite) / 0.6B-Base (rapide)",
            "preset_voice": "0.6B-CustomVoice",
            "preset_instruct": "1.7B-CustomVoice",
        }
    }


@router.get("/health", tags=["Monitoring"], include_in_schema=False)
async def health_probe():
    """Probe de sante pour monitoring."""
    healthy = True
    checks = {}
    try:
        if DEVICE == "mps":
            if hasattr(torch.mps, "current_allocated_memory"):
                _ = torch.mps.current_allocated_memory()
            checks["gpu"] = "ok"
        elif DEVICE.startswith("cuda"):
            _ = torch.cuda.memory_allocated()
            checks["gpu"] = "ok"
        else:
            checks["gpu"] = "cpu"
    except Exception:
        checks["gpu"] = "error"
        healthy = False
    checks["models_dir"] = "ok" if MODELS_DIR.exists() else "missing"
    if not MODELS_DIR.exists():
        healthy = False
    checks["voices_dir"] = "ok" if CUSTOM_VOICES_DIR.exists() else "missing"
    return JSONResponse(
        content={"status": "healthy" if healthy else "unhealthy", "version": API_VERSION, "device": DEVICE, "checks": checks},
        status_code=200 if healthy else 503,
    )


@router.get("/languages", response_model=LanguagesResponse, tags=["Informations"])
async def list_languages():
    """Liste les langues supportees et les modeles disponibles."""
    return {
        "languages": [
            {"code": code, "name": name}
            for code, name in LANGUAGE_MAP.items()
        ],
        "count": len(LANGUAGE_MAP),
        "models": {
            "voice_design": "1.7B-VoiceDesign",
            "voice_clone": "1.7B-Base / 0.6B-Base",
            "preset_voice": "0.6B-CustomVoice",
            "preset_instruct": "1.7B-CustomVoice",
        },
        "device": DEVICE
    }
