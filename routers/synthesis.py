"""Routes synthese vocale — POST /design, /preset, /preset/instruct."""

import io
import asyncio
import logging

import soundfile as sf
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import StreamingResponse

from config import (
    LANGUAGE_MAP, PRESET_VOICES, TTS_RATE_LIMIT, limiter,
)
from schemas import DesignRequest
from models import (
    load_voice_design_model, load_preset_voice_model,
    load_voice_clone_model, load_clone_base_model,
)
from voices import custom_voices, get_custom_voice_prompt
from generation import with_generation_lock

logger = logging.getLogger("voxqwen")

router = APIRouter()


@router.post("/design", tags=["Synthese vocale"])
@limiter.limit(TTS_RATE_LIMIT)
async def voice_design(request: Request, data: DesignRequest):
    """
    Voice Design - Genere un audio avec une voix decrite en texte.

    Exemples de voice_instruct :
    - "Voix feminine douce et chaleureuse"
    - "Voix masculine grave et posee"
    - "Jeune fille riant, voix enjouee"

    Retourne : fichier WAV
    """
    logger.info(f"POST /design: voice_instruct={data.voice_instruct!r}, text_len={len(data.text)}")

    async def do_generate():
        model = load_voice_design_model()
        language = LANGUAGE_MAP.get(data.language, "French")
        wavs, sr = await asyncio.to_thread(
            model.generate_voice_design,
            text=data.text,
            language=language,
            instruct=data.voice_instruct or "Voix naturelle et claire",
        )
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)
        return audio_buffer

    try:
        audio_buffer = await with_generation_lock(
            do_generate(), timeout=90, endpoint="/design"
        )
        return StreamingResponse(
            audio_buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=voice_design.wav"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preset", tags=["Synthese vocale"])
@limiter.limit(TTS_RATE_LIMIT)
async def preset_voice(
    request: Request,
    text: str = Form(..., min_length=1, max_length=10000, description="Texte a synthetiser"),
    voice: str = Form("Serena", description="Nom de la voix (native ou personnalisee)"),
    language: str = Form("fr", description="Langue : fr, en, zh, ja, ko, de, ru, pt, es, it")
):
    """
    Preset Voice - Genere un audio avec une voix preregle ou personnalisee.

    Retourne : fichier WAV
    """
    logger.info(f"POST /preset: voice={voice}, text_len={len(text)}")

    async def do_generate():
        language_full = LANGUAGE_MAP.get(language, "French")

        if voice in PRESET_VOICES:
            mdl = load_preset_voice_model()
            wavs, sr = await asyncio.to_thread(
                mdl.generate_custom_voice,
                text=text,
                language=language_full,
                speaker=voice,
            )

        elif voice in custom_voices:
            voice_data = custom_voices[voice]
            meta = voice_data["meta"]
            pi = get_custom_voice_prompt(voice)

            if pi is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"Impossible de charger les embeddings de la voix '{voice}'"
                )

            if meta.get("source") == "design" and isinstance(pi, dict) and pi.get("type") == "design":
                tts_model = load_voice_design_model()
                wavs, sr = await asyncio.to_thread(
                    tts_model.generate_voice_design,
                    text=text,
                    language=language_full,
                    instruct=pi["voice_description"],
                )
            else:
                model_size = meta.get("model", "1.7B")
                tts_model = load_clone_base_model(model_size)
                wavs, sr = await asyncio.to_thread(
                    tts_model.generate_voice_clone,
                    text=text,
                    language=language_full,
                    voice_clone_prompt=pi,
                )

        else:
            all_voices = list(PRESET_VOICES.keys()) + list(custom_voices.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Voix '{voice}' inconnue. Disponibles : {', '.join(all_voices)}"
            )

        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)
        return audio_buffer

    try:
        audio_buffer = await with_generation_lock(
            do_generate(), timeout=60, endpoint="/preset"
        )
        return StreamingResponse(
            audio_buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"attachment; filename=preset_{voice.lower()}.wav"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preset/instruct", tags=["Synthese vocale"])
@limiter.limit(TTS_RATE_LIMIT)
async def preset_voice_with_instruct(
    request: Request,
    text: str = Form(..., min_length=1, max_length=10000, description="Texte a synthetiser"),
    voice: str = Form("Serena", description="Nom de la voix (native uniquement pour instruct)"),
    instruct: str = Form("", description="Instruction pour controler l'emotion/style"),
    language: str = Form("fr", description="Langue : fr, en, zh, ja, ko, de, ru, pt, es, it")
):
    """
    Preset Voice avec controle emotionnel - Genere un audio avec une voix preregle
    et controle fin des emotions/styles via instructions.

    Utilise le modele 1.7B-CustomVoice (plus lourd mais plus expressif).

    Retourne : fichier WAV
    """
    # Validation hors semaphore
    if voice not in PRESET_VOICES:
        if voice in custom_voices:
            raise HTTPException(
                status_code=400,
                detail=f"La voix personnalisee '{voice}' ne supporte pas /preset/instruct. Utilisez /preset."
            )
        raise HTTPException(
            status_code=400,
            detail=f"Voix '{voice}' inconnue. Disponibles : {', '.join(PRESET_VOICES.keys())}"
        )

    async def do_generate():
        mdl = load_voice_clone_model()  # 1.7B-CustomVoice
        language_full = LANGUAGE_MAP.get(language, "French")
        wavs, sr = await asyncio.to_thread(
            mdl.generate_custom_voice,
            text=text,
            language=language_full,
            speaker=voice,
            instruct=instruct if instruct else "",
        )
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)
        return audio_buffer

    try:
        audio_buffer = await with_generation_lock(
            do_generate(), timeout=60, endpoint="/preset/instruct"
        )
        return StreamingResponse(
            audio_buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"attachment; filename=preset_instruct_{voice.lower()}.wav"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
