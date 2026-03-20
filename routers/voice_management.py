"""Routes gestion des voix — GET/POST/DELETE /voices, /voices/custom."""

import io
import os
import asyncio
import tempfile
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import JSONResponse

from config import (
    LANGUAGE_MAP, PRESET_VOICES, CUSTOM_VOICES_DIR, CLONE_RATE_LIMIT, limiter,
)
from models import load_clone_base_model, load_voice_design_model
from voices import (
    custom_voices, validate_voice_name, load_custom_voices,
    list_custom_voices, get_custom_voice_prompt, save_custom_voice,
    delete_custom_voice,
)
from generation import with_generation_lock

logger = logging.getLogger("voxqwen")

router = APIRouter()


@router.get("/voices", tags=["Synthese vocale"])
async def list_voices():
    """Liste toutes les voix disponibles (natives + personnalisees)."""
    native_voices = [
        {"name": name, "type": "native", **info}
        for name, info in PRESET_VOICES.items()
    ]
    custom = list_custom_voices()
    all_voices = native_voices + custom

    return {
        "voices": all_voices,
        "count": len(all_voices),
        "native_count": len(native_voices),
        "custom_count": len(custom),
        "note": "Toutes les voix supportent les 10 langues"
    }


@router.post("/voices/custom", tags=["Synthese vocale"])
@limiter.limit(CLONE_RATE_LIMIT)
async def create_custom_voice(
    request: Request,
    name: str = Form(..., description="Nom unique de la voix (3-50 chars, alphanum + tirets)"),
    source: str = Form(..., description="Source : 'clone' ou 'design'"),
    description: str = Form("", description="Description de la voix (max 200 chars)"),
    reference_audio: Optional[UploadFile] = File(None, description="Audio de reference (requis si source=clone)"),
    reference_text: str = Form("", description="Transcription de l'audio (requis si source=clone)"),
    model: str = Form("1.7B", description="Modele : '1.7B' (qualite) ou '0.6B' (rapide)"),
    voice_description: str = Form("", description="Description textuelle de la voix (requis si source=design)"),
    language: str = Form("fr", description="Langue : fr, en, zh, ja, ko, de, ru, pt, es, it"),
):
    """
    Cree une voix personnalisee persistante.

    Deux modes :
    - **source=clone** : Clone une voix depuis un audio de reference
    - **source=design** : Cree une voix depuis une description textuelle

    Retourne : name, type, source, created_at
    """
    tmp_path = None
    try:
        if not validate_voice_name(name):
            raise HTTPException(
                status_code=400,
                detail=f"Nom invalide. Regles : 3-50 chars, alphanum + tirets, pas de nom reserve ({', '.join(PRESET_VOICES.keys())})"
            )

        if name in custom_voices:
            raise HTTPException(
                status_code=400,
                detail=f"Une voix personnalisee '{name}' existe deja"
            )

        if source not in ("clone", "design"):
            raise HTTPException(
                status_code=400,
                detail="source doit etre 'clone' ou 'design'"
            )

        if model not in ("1.7B", "0.6B"):
            raise HTTPException(
                status_code=400,
                detail=f"model doit etre '1.7B' ou '0.6B', pas '{model}'"
            )

        if len(description) > 200:
            description = description[:200]

        lang_full = LANGUAGE_MAP.get(language, "French")

        if source == "clone":
            if not reference_audio or not reference_audio.filename:
                raise HTTPException(
                    status_code=400,
                    detail="reference_audio est requis pour source=clone"
                )
            if not reference_text or not reference_text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="reference_text est requis pour source=clone"
                )

            audio_bytes = await reference_audio.read()
            suffix = Path(reference_audio.filename).suffix or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            import torchaudio
            waveform, sample_rate = torchaudio.load(tmp_path)
            duration = waveform.shape[1] / sample_rate

            if duration < 1:
                raise HTTPException(status_code=400, detail=f"Audio trop court : {duration:.1f}s (min: 1s)")
            if duration > 30:
                raise HTTPException(status_code=400, detail=f"Audio trop long : {duration:.1f}s (max: 30s)")

            tts_model = load_clone_base_model(model)

            async def do_clone_prompt():
                return await asyncio.to_thread(
                    tts_model.create_voice_clone_prompt,
                    ref_audio=tmp_path,
                    ref_text=reference_text,
                )

            prompt_items = await with_generation_lock(
                do_clone_prompt(), timeout=120, endpoint="/voices/custom(clone)"
            )

        else:
            # Mode design
            if not voice_description or not voice_description.strip():
                raise HTTPException(
                    status_code=400,
                    detail="voice_description est requis pour source=design"
                )

            async def do_design_test():
                tts_mdl = load_voice_design_model()
                return await asyncio.to_thread(
                    tts_mdl.generate_voice_design,
                    text="Test de voix.",
                    language=lang_full,
                    instruct=voice_description,
                )

            wavs, sr = await with_generation_lock(
                do_design_test(), timeout=120, endpoint="/voices/custom(design)"
            )

            prompt_items = {
                "type": "design",
                "voice_description": voice_description,
                "language": lang_full,
            }

        meta = save_custom_voice(
            name=name,
            prompt_items=prompt_items,
            source=source,
            model=model,
            description=description,
            language=language,
        )

        logger.info(f"Voix custom creee: {name} (source={source})")

        return JSONResponse({
            "status": "created",
            "voice": {
                "name": name,
                "type": "custom",
                "source": source,
                "description": description,
                "model": model,
                "created_at": meta["created_at"],
            }
        }, status_code=201)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.get("/voices/custom/{name}", tags=["Synthese vocale"])
async def get_custom_voice_details(name: str):
    """Details d'une voix personnalisee."""
    if name not in custom_voices:
        raise HTTPException(
            status_code=404,
            detail=f"Voix personnalisee '{name}' non trouvee"
        )

    voice_data = custom_voices[name]
    meta = voice_data["meta"]

    prompt_file = CUSTOM_VOICES_DIR / name / "prompt.pt"
    file_size = prompt_file.stat().st_size if prompt_file.exists() else 0

    return {
        "name": name,
        "type": "custom",
        **{k: v for k, v in meta.items() if k != "name"},
        "file_size_bytes": file_size,
        "loaded_in_memory": voice_data["prompt_items"] is not None,
    }


@router.delete("/voices/custom/{name}", tags=["Synthese vocale"])
async def delete_custom_voice_route(name: str):
    """Supprime une voix personnalisee."""
    if name in PRESET_VOICES:
        raise HTTPException(
            status_code=403,
            detail=f"Impossible de supprimer la voix native '{name}'"
        )

    if not delete_custom_voice(name):
        raise HTTPException(
            status_code=404,
            detail=f"Voix personnalisee '{name}' non trouvee"
        )

    logger.warning(f"Voix custom supprimee: {name}")

    return {
        "status": "deleted",
        "name": name,
    }


@router.post("/voices/reload", tags=["Synthese vocale"])
async def reload_custom_voices_route():
    """Recharge les voix personnalisees depuis le disque."""
    load_custom_voices()
    return {
        "status": "reloaded",
        "count": len(custom_voices),
    }
