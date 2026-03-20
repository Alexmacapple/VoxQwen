"""Routes clonage vocal — POST /clone, /clone/prompt, GET/DELETE prompts."""

import io
import os
import asyncio
import tempfile
import logging
from pathlib import Path
from typing import Optional

import soundfile as sf
from fastapi import APIRouter, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse

from config import LANGUAGE_MAP, CLONE_RATE_LIMIT, limiter
from models import load_clone_base_model
from voices import get_prompt, store_prompt, delete_prompt, list_prompts
from generation import with_generation_lock

logger = logging.getLogger("voxqwen")

router = APIRouter()


@router.post("/clone", tags=["Synthese vocale"])
@limiter.limit(CLONE_RATE_LIMIT)
async def voice_clone(
    request: Request,
    text: str = Form(..., description="Texte a synthetiser"),
    reference_audio: Optional[UploadFile] = File(None, description="Audio de reference (1-30 sec). Requis si pas de prompt_id."),
    reference_text: str = Form("", description="Transcription de l'audio de reference (REQUIS pour le clonage)"),
    language: str = Form("fr", description="Langue cible"),
    model: str = Form("1.7B", description="Modele : '1.7B' (qualite) ou '0.6B' (rapide)"),
    prompt_id: str = Form("", description="ID d'un prompt existant (si fourni, reference_audio est ignore)"),
):
    """
    Voice Clone - Clone une voix depuis un audio de reference ou un prompt existant.

    Retourne : fichier WAV
    """
    logger.info(f"POST /clone: voice=clone, text_len={len(text)}")

    tmp_path = None
    try:
        if model not in ("1.7B", "0.6B"):
            raise HTTPException(
                status_code=400,
                detail=f"model doit etre '1.7B' ou '0.6B', pas '{model}'"
            )

        lang_full = LANGUAGE_MAP.get(language, "French")

        # Mode 1: Utiliser un prompt existant
        if prompt_id:
            prompt_data = get_prompt(prompt_id)
            if not prompt_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Prompt '{prompt_id}' non trouve"
                )

            if prompt_data["model"] != model:
                raise HTTPException(
                    status_code=400,
                    detail=f"Le prompt a ete cree avec le modele {prompt_data['model']}, pas {model}"
                )

            tts_model = load_clone_base_model(model)

            async def do_generate_prompt():
                return await asyncio.to_thread(
                    tts_model.generate_voice_clone,
                    text=text,
                    language=lang_full,
                    voice_clone_prompt=prompt_data["prompt_items"],
                )

            wavs, sr = await with_generation_lock(
                do_generate_prompt(), timeout=90, endpoint="/clone"
            )

        # Mode 2: Traiter l'audio de reference a la volee
        else:
            if not reference_audio or not reference_audio.filename:
                raise HTTPException(
                    status_code=400,
                    detail="reference_audio requis si prompt_id n'est pas fourni"
                )

            if not reference_text or not reference_text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="reference_text est obligatoire. Fournissez la transcription exacte de l'audio de reference."
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
                raise HTTPException(status_code=400, detail=f"Audio trop court: {duration:.1f}s (min: 1s)")
            if duration > 30:
                raise HTTPException(status_code=400, detail=f"Audio trop long: {duration:.1f}s (max: 30s)")

            tts_model = load_clone_base_model(model)

            async def do_generate_ref():
                return await asyncio.to_thread(
                    tts_model.generate_voice_clone,
                    text=text,
                    language=lang_full,
                    ref_audio=tmp_path,
                    ref_text=reference_text,
                )

            wavs, sr = await with_generation_lock(
                do_generate_ref(), timeout=90, endpoint="/clone"
            )

        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)

        return StreamingResponse(
            audio_buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=voice_clone.wav"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/clone/prompt", tags=["Synthese vocale"])
@limiter.limit(CLONE_RATE_LIMIT)
async def create_clone_prompt(
    request: Request,
    reference_audio: UploadFile = File(..., description="Audio de reference (1-30 sec)"),
    reference_text: str = Form(..., description="Transcription de l'audio de reference (REQUIS)"),
    model: str = Form("1.7B", description="Modele : '1.7B' (qualite) ou '0.6B' (rapide)"),
    name: Optional[str] = Form(None, description="Nom pour identifier le prompt (ex : 'voix_yves')"),
    x_vector_only: bool = Form(False, description="Si True, retourne uniquement l'embedding x-vector sans stocker le prompt"),
):
    """
    Cree un prompt reutilisable pour Voice Clone.

    Retourne : prompt_id, name, model, created_at
    """
    tmp_path = None
    try:
        if model not in ("1.7B", "0.6B"):
            raise HTTPException(
                status_code=400,
                detail=f"model doit etre '1.7B' ou '0.6B', pas '{model}'"
            )

        if not reference_audio.filename:
            raise HTTPException(status_code=400, detail="Fichier audio requis")

        audio_bytes = await reference_audio.read()

        suffix = Path(reference_audio.filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        import torchaudio
        waveform, sample_rate = torchaudio.load(tmp_path)
        duration = waveform.shape[1] / sample_rate

        if duration < 1:
            raise HTTPException(status_code=400, detail=f"Audio trop court: {duration:.1f}s (min: 1s)")
        if duration > 30:
            raise HTTPException(status_code=400, detail=f"Audio trop long: {duration:.1f}s (max: 30s)")

        tts_model = load_clone_base_model(model)

        async def do_create_prompt():
            return await asyncio.to_thread(
                tts_model.create_voice_clone_prompt,
                ref_audio=tmp_path,
                ref_text=reference_text,
            )

        prompt_items = await with_generation_lock(
            do_create_prompt(), timeout=60, endpoint="/clone/prompt"
        )

        os.unlink(tmp_path)
        tmp_path = None

        # Mode x_vector_only
        if x_vector_only:
            x_vector_data = None

            def serialize_value(v):
                """Convertit une valeur en format JSON-serialisable."""
                if hasattr(v, 'tolist'):
                    return v.tolist()
                elif hasattr(v, 'cpu'):
                    return v.cpu().numpy().tolist()
                elif isinstance(v, (list, tuple)):
                    return [serialize_value(item) for item in v]
                elif isinstance(v, dict):
                    return {k: serialize_value(val) for k, val in v.items()}
                elif hasattr(v, '__dict__'):
                    return {k: serialize_value(val) for k, val in vars(v).items() if not k.startswith('_')}
                else:
                    return str(v) if not isinstance(v, (int, float, str, bool, type(None))) else v

            if isinstance(prompt_items, dict):
                x_vector_data = {k: serialize_value(v) for k, v in prompt_items.items()}
            elif isinstance(prompt_items, (list, tuple)):
                x_vector_data = [serialize_value(item) for item in prompt_items]
            elif hasattr(prompt_items, '__dict__'):
                x_vector_data = {k: serialize_value(v) for k, v in vars(prompt_items).items() if not k.startswith('_')}
            else:
                x_vector_data = serialize_value(prompt_items)

            return JSONResponse({
                "mode": "x_vector_only",
                "model": model,
                "duration_seconds": duration,
                "x_vector": x_vector_data,
            })

        prompt_id = store_prompt(prompt_items, model, name)
        prompt_data = get_prompt(prompt_id)

        logger.info(f"Prompt clone cree: {prompt_id} (model={model})")

        return JSONResponse({
            "prompt_id": prompt_id,
            "name": name,
            "model": model,
            "created_at": prompt_data["created_at"].isoformat(),
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.get("/clone/prompts", tags=["Synthese vocale"])
async def list_clone_prompts():
    """Liste tous les prompts de clonage vocal en cache."""
    prompts = list_prompts()
    return {
        "prompts": prompts,
        "count": len(prompts),
        "warning": "Les prompts sont stockes en memoire et perdus au redemarrage du serveur.",
    }


@router.delete("/clone/prompts/{prompt_id}", tags=["Synthese vocale"])
async def delete_clone_prompt(prompt_id: str):
    """Supprime un prompt de clonage vocal du cache."""
    if delete_prompt(prompt_id):
        return {
            "status": "deleted",
            "prompt_id": prompt_id,
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt '{prompt_id}' non trouve"
        )
