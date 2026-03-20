"""Routes batch processing — POST /batch/preset, /batch/design, /batch/clone."""

import io
import asyncio
import zipfile
import logging

import soundfile as sf
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import StreamingResponse

from config import (
    LANGUAGE_MAP, PRESET_VOICES, BATCH_RATE_LIMIT, CLONE_RATE_LIMIT,
    GENERATION_BATCH_TIMEOUT, limiter, resolve_language,
)
from schemas import BatchPresetRequest, BatchDesignRequest
from models import (
    load_preset_voice_model, load_voice_design_model, load_clone_base_model,
)
from voices import custom_voices, get_custom_voice_prompt, get_prompt
from generation import with_generation_lock

logger = logging.getLogger("voxqwen")

router = APIRouter()


@router.post("/batch/preset", tags=["Batch Processing"])
@limiter.limit(BATCH_RATE_LIMIT)
async def batch_preset_voice(request: Request, data: BatchPresetRequest):
    """
    Batch Preset - Genere plusieurs audios avec la meme voix.

    Retourne : fichier ZIP
    """
    logger.info(f"POST /batch/preset: {len(data.texts)} textes, voice={data.voice}")

    try:
        if len(data.texts) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 textes par requete")

        for i, text in enumerate(data.texts):
            if not text or not text.strip():
                raise HTTPException(status_code=400, detail=f"Texte {i+1} est vide")

        first_text = data.texts[0] if data.texts else ""
        language_full = resolve_language(data.language, first_text)

        is_native = data.voice in PRESET_VOICES
        is_custom = data.voice in custom_voices

        if not is_native and not is_custom:
            all_voices = list(PRESET_VOICES.keys()) + list(custom_voices.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Voix '{data.voice}' inconnue. Disponibles : {', '.join(all_voices)}"
            )

        async def do_batch():
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, text in enumerate(data.texts):
                    if data.language == "auto":
                        lang = resolve_language("auto", text)
                    else:
                        lang = language_full

                    if is_native:
                        mdl = load_preset_voice_model()
                        wavs, sr = await asyncio.to_thread(
                            mdl.generate_custom_voice,
                            text=text,
                            language=lang,
                            speaker=data.voice,
                        )
                    else:
                        voice_data = custom_voices[data.voice]
                        meta = voice_data["meta"]
                        pi = get_custom_voice_prompt(data.voice)

                        if pi is None:
                            raise HTTPException(
                                status_code=500,
                                detail=f"Impossible de charger la voix '{data.voice}'"
                            )

                        if meta.get("source") == "design" and isinstance(pi, dict) and pi.get("type") == "design":
                            tts_model = load_voice_design_model()
                            wavs, sr = await asyncio.to_thread(
                                tts_model.generate_voice_design,
                                text=text,
                                language=lang,
                                instruct=pi["voice_description"],
                            )
                        else:
                            model_size = meta.get("model", "1.7B")
                            tts_model = load_clone_base_model(model_size)
                            wavs, sr = await asyncio.to_thread(
                                tts_model.generate_voice_clone,
                                text=text,
                                language=lang,
                                voice_clone_prompt=pi,
                            )

                    audio_buffer = io.BytesIO()
                    sf.write(audio_buffer, wavs[0], sr, format="WAV")
                    audio_buffer.seek(0)
                    zf.writestr(f"{i+1:03d}.wav", audio_buffer.getvalue())

            zip_buffer.seek(0)
            return zip_buffer

        batch_timeout = min(len(data.texts) * 60 + 60, GENERATION_BATCH_TIMEOUT)
        zip_buffer = await with_generation_lock(
            do_batch(), timeout=batch_timeout, endpoint="/batch/preset"
        )

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=batch_preset_{data.voice.lower()}.zip"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/design", tags=["Batch Processing"])
@limiter.limit(BATCH_RATE_LIMIT)
async def batch_voice_design(request: Request, data: BatchDesignRequest):
    """
    Batch Voice Design - Genere plusieurs audios avec une voix decrite en texte.

    Retourne : fichier ZIP
    """
    logger.info(f"POST /batch/design: {len(data.texts)} textes, voice={data.voice_instruct!r}")

    try:
        if len(data.texts) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 textes par requete")

        for i, text in enumerate(data.texts):
            if not text or not text.strip():
                raise HTTPException(status_code=400, detail=f"Texte {i+1} est vide")

        first_text = data.texts[0] if data.texts else ""
        language_full = resolve_language(data.language, first_text)

        async def do_batch():
            mdl = load_voice_design_model()
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, text in enumerate(data.texts):
                    lang = resolve_language("auto", text) if data.language == "auto" else language_full
                    wavs, sr = await asyncio.to_thread(
                        mdl.generate_voice_design,
                        text=text,
                        language=lang,
                        instruct=data.voice_instruct or "Voix naturelle et claire",
                    )
                    audio_buffer = io.BytesIO()
                    sf.write(audio_buffer, wavs[0], sr, format="WAV")
                    audio_buffer.seek(0)
                    zf.writestr(f"{i+1:03d}.wav", audio_buffer.getvalue())
            zip_buffer.seek(0)
            return zip_buffer

        batch_timeout = min(len(data.texts) * 60 + 60, GENERATION_BATCH_TIMEOUT)
        zip_buffer = await with_generation_lock(
            do_batch(), timeout=batch_timeout, endpoint="/batch/design"
        )

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=batch_design.zip"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/clone", tags=["Batch Processing"])
@limiter.limit(CLONE_RATE_LIMIT)
async def batch_voice_clone(
    request: Request,
    texts: str = Form(..., description="Textes a synthetiser, separes par des sauts de ligne"),
    prompt_id: str = Form(..., description="ID du prompt cree via /clone/prompt (requis)"),
    language: str = Form("fr", description="Langue : fr, en, zh, ja, ko, de, ru, pt, es, it, auto"),
):
    """
    Batch Voice Clone - Genere plusieurs audios avec une voix clonee.

    Retourne : fichier ZIP
    """
    logger.info(f"POST /batch/clone: voice=clone(prompt={prompt_id})")

    try:
        text_list = [t.strip() for t in texts.split("\n") if t.strip()]

        if not text_list:
            raise HTTPException(status_code=400, detail="Aucun texte valide fourni")

        if len(text_list) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 textes par requete")

        prompt_data = get_prompt(prompt_id)
        if not prompt_data:
            raise HTTPException(
                status_code=404,
                detail=f"Prompt '{prompt_id}' non trouve"
            )

        model_size = prompt_data["model"]
        first_text = text_list[0] if text_list else ""
        language_full = resolve_language(language, first_text)

        async def do_batch():
            tts_model = load_clone_base_model(model_size)
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, text in enumerate(text_list):
                    lang = resolve_language("auto", text) if language == "auto" else language_full
                    wavs, sr = await asyncio.to_thread(
                        tts_model.generate_voice_clone,
                        text=text,
                        language=lang,
                        voice_clone_prompt=prompt_data["prompt_items"],
                    )
                    audio_buffer = io.BytesIO()
                    sf.write(audio_buffer, wavs[0], sr, format="WAV")
                    audio_buffer.seek(0)
                    zf.writestr(f"{i+1:03d}.wav", audio_buffer.getvalue())
            zip_buffer.seek(0)
            return zip_buffer

        batch_timeout = min(len(text_list) * 60 + 60, GENERATION_BATCH_TIMEOUT)
        zip_buffer = await with_generation_lock(
            do_batch(), timeout=batch_timeout, endpoint="/batch/clone"
        )

        prompt_name = prompt_data.get("name", "clone")
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=batch_clone_{prompt_name}.zip"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
