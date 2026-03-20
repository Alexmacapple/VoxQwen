"""Routes MCP — /mcp/* routes + helpers documentation."""

import io
import os
import base64
import asyncio
import tempfile
import logging

import soundfile as sf
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from config import (
    DEVICE, API_VERSION, LANGUAGE_MAP, PRESET_VOICES,
    MCP_RATE_LIMIT, limiter, langdetect_available, resolve_language,
)
from schemas import (
    MCPPresetRequest, MCPDesignRequest, MCPCloneRequest,
    MCPCreatePromptRequest, MCPPresetInstructRequest,
    MCPAudioResponse, MCPPromptResponse,
)
from models import (
    load_preset_voice_model, load_voice_design_model,
    load_voice_clone_model, load_clone_base_model,
)
import models as _models_module
from voices import (
    custom_voices, voice_clone_prompts,
    get_custom_voice_prompt, list_custom_voices,
    get_prompt, store_prompt,
)
from generation import with_generation_lock

logger = logging.getLogger("voxqwen")

router = APIRouter()


@router.post("/mcp/preset", response_model=MCPAudioResponse, tags=["MCP Tools"])
@limiter.limit(MCP_RATE_LIMIT)
async def mcp_preset_voice(request: Request, data: MCPPresetRequest):
    """[MCP Tool] Genere un audio avec une voix preregle."""
    async def do_generate():
        language_full = resolve_language(data.language, data.text)

        if data.voice in PRESET_VOICES:
            mdl = load_preset_voice_model()
            wavs, sr = await asyncio.to_thread(
                mdl.generate_custom_voice,
                text=data.text,
                language=language_full,
                speaker=data.voice,
            )
            m_used = "0.6B-CustomVoice"

        elif data.voice in custom_voices:
            voice_data = custom_voices[data.voice]
            meta = voice_data["meta"]
            pi = get_custom_voice_prompt(data.voice)

            if pi is None:
                raise HTTPException(
                    status_code=500,
                    detail={"error": f"Impossible de charger la voix '{data.voice}'", "code": "VOICE_LOAD_ERROR"}
                )

            if meta.get("source") == "design" and isinstance(pi, dict) and pi.get("type") == "design":
                tts_model = load_voice_design_model()
                wavs, sr = await asyncio.to_thread(
                    tts_model.generate_voice_design,
                    text=data.text,
                    language=language_full,
                    instruct=pi["voice_description"],
                )
                m_used = "1.7B-VoiceDesign"
            else:
                model_size = meta.get("model", "1.7B")
                tts_model = load_clone_base_model(model_size)
                wavs, sr = await asyncio.to_thread(
                    tts_model.generate_voice_clone,
                    text=data.text,
                    language=language_full,
                    voice_clone_prompt=pi,
                )
                m_used = f"{model_size}-Base"
        else:
            all_voices = list(PRESET_VOICES.keys()) + list(custom_voices.keys())
            raise HTTPException(
                status_code=404,
                detail={
                    "error": f"Voix '{data.voice}' non trouvee",
                    "code": "VOICE_NOT_FOUND",
                    "suggestion": f"Voix disponibles: {', '.join(all_voices[:10])}"
                }
            )

        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)
        audio_b64 = base64.b64encode(audio_buffer.read()).decode('utf-8')
        duration_ms = int(len(wavs[0]) / sr * 1000)
        return wavs, sr, audio_b64, duration_ms, m_used

    try:
        _, _, audio_b64, duration_ms, model_used = await with_generation_lock(
            do_generate(), timeout=60, endpoint="/mcp/preset"
        )
        return MCPAudioResponse(
            audio_base64=audio_b64,
            format="wav",
            sample_rate=24000,
            duration_ms=duration_ms,
            voice_used=data.voice,
            model_used=model_used,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "code": "GENERATION_ERROR"})


@router.post("/mcp/design", response_model=MCPAudioResponse, tags=["MCP Tools"])
@limiter.limit(MCP_RATE_LIMIT)
async def mcp_voice_design(request: Request, data: MCPDesignRequest):
    """[MCP Tool] Genere un audio avec une voix decrite en langage naturel."""
    async def do_generate():
        mdl = load_voice_design_model()
        language_full = resolve_language(data.language, data.text)
        wavs, sr = await asyncio.to_thread(
            mdl.generate_voice_design,
            text=data.text,
            language=language_full,
            instruct=data.voice_description,
        )
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)
        audio_b64 = base64.b64encode(audio_buffer.read()).decode('utf-8')
        duration_ms = int(len(wavs[0]) / sr * 1000)
        return sr, audio_b64, duration_ms

    try:
        sr, audio_b64, duration_ms = await with_generation_lock(
            do_generate(), timeout=90, endpoint="/mcp/design"
        )
        return MCPAudioResponse(
            audio_base64=audio_b64,
            format="wav",
            sample_rate=sr,
            duration_ms=duration_ms,
            voice_used=f"design:{data.voice_description[:30]}",
            model_used="1.7B-VoiceDesign",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "code": "GENERATION_ERROR"})


@router.post("/mcp/clone", response_model=MCPAudioResponse, tags=["MCP Tools"])
@limiter.limit(MCP_RATE_LIMIT)
async def mcp_voice_clone(request: Request, data: MCPCloneRequest):
    """[MCP Tool] Genere un audio avec une voix clonee."""
    prompt_data = get_prompt(data.prompt_id)
    if not prompt_data:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Prompt '{data.prompt_id}' non trouve",
                "code": "PROMPT_NOT_FOUND",
                "suggestion": "Les prompts sont volatils. Recreez-le via /mcp/clone/prompt"
            }
        )

    model_size = prompt_data["model"]

    async def do_generate():
        tts_model = load_clone_base_model(model_size)
        language_full = resolve_language(data.language, data.text)
        wavs, sr = await asyncio.to_thread(
            tts_model.generate_voice_clone,
            text=data.text,
            language=language_full,
            voice_clone_prompt=prompt_data["prompt_items"],
        )
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)
        audio_b64 = base64.b64encode(audio_buffer.read()).decode('utf-8')
        duration_ms = int(len(wavs[0]) / sr * 1000)
        return sr, audio_b64, duration_ms

    try:
        sr, audio_b64, duration_ms = await with_generation_lock(
            do_generate(), timeout=90, endpoint="/mcp/clone"
        )
        return MCPAudioResponse(
            audio_base64=audio_b64,
            format="wav",
            sample_rate=sr,
            duration_ms=duration_ms,
            voice_used=f"clone:{data.prompt_id[:8]}",
            model_used=f"{model_size}-Base",
            warning="Prompt stocke en memoire, perdu au redemarrage.",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "code": "GENERATION_ERROR"})


@router.post("/mcp/clone/prompt", response_model=MCPPromptResponse, tags=["MCP Tools"])
@limiter.limit(MCP_RATE_LIMIT)
async def mcp_create_clone_prompt(request: Request, data: MCPCreatePromptRequest):
    """[MCP Tool] Cree un prompt reutilisable pour clonage vocal."""
    tmp_path = None
    try:
        try:
            audio_bytes = base64.b64decode(data.reference_audio_base64)
        except Exception:
            raise HTTPException(
                status_code=422,
                detail={"error": "Base64 invalide", "code": "INVALID_BASE64"}
            )

        if len(audio_bytes) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=422,
                detail={"error": f"Audio trop grand: {len(audio_bytes) / 1024 / 1024:.1f}MB > 5MB", "code": "AUDIO_TOO_LARGE"}
            )

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        import torchaudio
        waveform, sample_rate = torchaudio.load(tmp_path)
        duration = waveform.shape[1] / sample_rate

        if duration < 1:
            raise HTTPException(status_code=422, detail={"error": f"Audio trop court: {duration:.1f}s (min: 1s)", "code": "AUDIO_TOO_SHORT"})
        if duration > 30:
            raise HTTPException(status_code=422, detail={"error": f"Audio trop long: {duration:.1f}s (max: 30s)", "code": "AUDIO_TOO_LONG"})

        async def do_create_prompt():
            tts_model = load_clone_base_model(data.model)
            return await asyncio.to_thread(
                tts_model.create_voice_clone_prompt,
                ref_audio=tmp_path,
                ref_text=data.reference_text,
            )

        prompt_items = await with_generation_lock(
            do_create_prompt(), timeout=60, endpoint="/mcp/clone/prompt"
        )

        prompt_id = store_prompt(prompt_items, data.model, data.name)
        prompt_data_stored = get_prompt(prompt_id)

        return MCPPromptResponse(
            prompt_id=prompt_id,
            name=data.name,
            model=data.model,
            created_at=prompt_data_stored["created_at"].isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "code": "PROMPT_CREATION_ERROR"})
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/mcp/preset/instruct", response_model=MCPAudioResponse, tags=["MCP Tools"])
@limiter.limit(MCP_RATE_LIMIT)
async def mcp_preset_instruct(request: Request, data: MCPPresetInstructRequest):
    """[MCP Tool] Genere un audio avec controle emotionnel/style."""
    if data.voice not in PRESET_VOICES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Voix '{data.voice}' non supportee pour instruct",
                "code": "VOICE_NOT_SUPPORTED",
                "suggestion": f"Voix natives: {', '.join(PRESET_VOICES.keys())}"
            }
        )

    async def do_generate():
        mdl = load_voice_clone_model()  # 1.7B-CustomVoice
        language_full = resolve_language(data.language, data.text)
        wavs, sr = await asyncio.to_thread(
            mdl.generate_custom_voice,
            text=data.text,
            language=language_full,
            speaker=data.voice,
            instruct=data.instruct if data.instruct else "",
        )
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)
        audio_b64 = base64.b64encode(audio_buffer.read()).decode('utf-8')
        duration_ms = int(len(wavs[0]) / sr * 1000)
        return sr, audio_b64, duration_ms

    try:
        sr, audio_b64, duration_ms = await with_generation_lock(
            do_generate(), timeout=60, endpoint="/mcp/preset/instruct"
        )
        return MCPAudioResponse(
            audio_base64=audio_b64,
            format="wav",
            sample_rate=sr,
            duration_ms=duration_ms,
            voice_used=data.voice,
            model_used="1.7B-CustomVoice",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "code": "GENERATION_ERROR"})


@router.get("/mcp/voices", tags=["MCP Tools"])
def mcp_get_voices():
    """[MCP Tool] Liste toutes les voix disponibles."""
    native = [{"name": name, "type": "native", **info} for name, info in PRESET_VOICES.items()]
    custom = list_custom_voices()
    return {
        "voices": native + custom,
        "count": len(native) + len(custom),
        "native_count": len(native),
        "custom_count": len(custom),
    }


@router.get("/mcp/languages", tags=["MCP Tools"])
def mcp_get_languages():
    """[MCP Tool] Liste les langues supportees."""
    return {
        "languages": [{"code": code, "name": name} for code, name in LANGUAGE_MAP.items()],
        "count": len(LANGUAGE_MAP),
        "auto_detection": langdetect_available,
    }


@router.get("/mcp/status", tags=["MCP Tools"])
def mcp_get_status(request: Request):
    """[MCP Tool] Statut du serveur MCP et des modeles."""
    mcp_server = getattr(request.app.state, "mcp_server", None)
    return {
        "mcp_enabled": mcp_server is not None,
        "version": API_VERSION,
        "device": DEVICE,
        "models": {
            "voice_design_loaded": _models_module.voice_design_model is not None,
            "voice_clone_loaded": _models_module.voice_clone_model is not None,
            "preset_voice_loaded": _models_module.preset_voice_model is not None,
            "clone_1_7b_loaded": _models_module.clone_model_1_7b is not None,
            "clone_0_6b_loaded": _models_module.clone_model_0_6b is not None,
        },
        "voices": {
            "native_count": len(PRESET_VOICES),
            "custom_count": len(custom_voices),
        },
        "prompts_cached": len(voice_clone_prompts),
    }


# ── MCP Documentation helpers ───────────────────────────────────────────────


def get_mcp_tools_from_server(mcp_server) -> list:
    """Recupere la liste des outils MCP depuis le serveur FastAPI-MCP."""
    if mcp_server is None:
        return []

    tools = []
    try:
        for tool in mcp_server.get_tools():
            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                "category": categorize_tool(tool.name),
            })
    except Exception as e:
        logger.warning(f"Erreur introspection MCP: {e}")
    return tools


def categorize_tool(name: str) -> str:
    """Categorise un outil MCP par son nom."""
    if "voice" in name or "preset" in name or "design" in name or "clone" in name:
        return "Synthese"
    elif "status" in name or "model" in name:
        return "Avance"
    else:
        return "Gestion"


def get_mcp_tools_list() -> list:
    """Retourne la liste des outils MCP avec leurs metadonnees."""
    return [
        # Categorie: Synthese
        {
            "name": "tts_preset_voice",
            "description": "Genere un audio avec une voix preregle (native ou personnalisee)",
            "category": "Synthese",
            "parameters": [
                {"name": "text", "type": "string", "required": True, "description": "Texte a synthetiser"},
                {"name": "voice", "type": "string", "required": False, "description": "Nom de la voix (defaut: Serena)"},
                {"name": "language", "type": "string", "required": False, "description": "Code langue (defaut: fr)"},
            ],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_preset_voice",
      "arguments": {
        "text": "Bonjour le monde",
        "voice": "Serena",
        "language": "fr"
      }
    },
    "id": 1
  }' ''',
            "response_example": '''{
  "jsonrpc": "2.0",
  "result": {
    "content": [{
      "type": "text",
      "text": "{\\"audio_base64\\":\\"UklGRiQA...\\",\\"sample_rate\\":24000}"
    }]
  },
  "id": 1
}''',
        },
        {
            "name": "tts_voice_design",
            "description": "Genere un audio avec une voix decrite en langage naturel",
            "category": "Synthese",
            "parameters": [
                {"name": "text", "type": "string", "required": True, "description": "Texte a synthetiser"},
                {"name": "voice_description", "type": "string", "required": True, "description": "Description de la voix (ex: 'Voix feminine douce')"},
                {"name": "language", "type": "string", "required": False, "description": "Code langue (defaut: fr)"},
            ],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_voice_design",
      "arguments": {
        "text": "Bienvenue dans notre application",
        "voice_description": "Voix masculine grave et chaleureuse",
        "language": "fr"
      }
    },
    "id": 1
  }' ''',
            "response_example": None,
        },
        {
            "name": "tts_voice_clone",
            "description": "Genere un audio avec une voix clonee (necessite un prompt_id)",
            "category": "Synthese",
            "parameters": [
                {"name": "text", "type": "string", "required": True, "description": "Texte a synthetiser"},
                {"name": "prompt_id", "type": "string", "required": True, "description": "ID du prompt cree via tts_create_clone_prompt"},
                {"name": "language", "type": "string", "required": False, "description": "Code langue (defaut: fr)"},
            ],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_voice_clone",
      "arguments": {
        "text": "Ceci est ma voix clonee",
        "prompt_id": "abc123-def456-...",
        "language": "fr"
      }
    },
    "id": 1
  }' ''',
            "response_example": None,
        },
        # Categorie: Gestion
        {
            "name": "tts_get_voices",
            "description": "Liste toutes les voix disponibles (natives + personnalisees)",
            "category": "Gestion",
            "parameters": [],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_get_voices",
      "arguments": {}
    },
    "id": 1
  }' ''',
            "response_example": '''{
  "jsonrpc": "2.0",
  "result": {
    "content": [{
      "type": "text",
      "text": "{\\"voices\\":[{\\"name\\":\\"Serena\\",\\"type\\":\\"native\\"},...],\\"count\\":9}"
    }]
  },
  "id": 1
}''',
        },
        {
            "name": "tts_get_languages",
            "description": "Liste les langues supportees par l'API",
            "category": "Gestion",
            "parameters": [],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_get_languages",
      "arguments": {}
    },
    "id": 1
  }' ''',
            "response_example": None,
        },
        # Categorie: Avance
        {
            "name": "tts_create_clone_prompt",
            "description": "Cree un prompt reutilisable pour clonage vocal a partir d'un audio",
            "category": "Avance",
            "parameters": [
                {"name": "reference_audio_base64", "type": "string", "required": True, "description": "Audio de reference encode en base64"},
                {"name": "reference_text", "type": "string", "required": True, "description": "Transcription exacte de l'audio"},
                {"name": "model", "type": "string", "required": False, "description": "'1.7B' (qualite) ou '0.6B' (rapide)"},
                {"name": "name", "type": "string", "required": False, "description": "Nom pour identifier le prompt"},
            ],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_create_clone_prompt",
      "arguments": {
        "reference_audio_base64": "UklGRiQA...",
        "reference_text": "Bonjour, je suis la voix de reference.",
        "model": "1.7B",
        "name": "ma_voix"
      }
    },
    "id": 1
  }' ''',
            "response_example": '''{
  "jsonrpc": "2.0",
  "result": {
    "content": [{
      "type": "text",
      "text": "{\\"prompt_id\\":\\"abc123-def456\\",\\"name\\":\\"ma_voix\\"}"
    }]
  },
  "id": 1
}''',
        },
        {
            "name": "tts_preset_instruct",
            "description": "Synthese avec voix native et controle emotionnel/style",
            "category": "Avance",
            "parameters": [
                {"name": "text", "type": "string", "required": True, "description": "Texte a synthetiser"},
                {"name": "voice", "type": "string", "required": False, "description": "Nom de la voix native"},
                {"name": "instruct", "type": "string", "required": False, "description": "Instruction pour l'emotion/style"},
                {"name": "language", "type": "string", "required": False, "description": "Code langue"},
            ],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_preset_instruct",
      "arguments": {
        "text": "Je suis tellement content de vous voir !",
        "voice": "Serena",
        "instruct": "Ton joyeux et excite",
        "language": "fr"
      }
    },
    "id": 1
  }' ''',
            "response_example": None,
        },
        {
            "name": "tts_get_model_status",
            "description": "Retourne le statut des modeles charges et des ressources",
            "category": "Avance",
            "parameters": [],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_get_model_status",
      "arguments": {}
    },
    "id": 1
  }' ''',
            "response_example": None,
        },
    ]


def get_voices_for_template() -> dict:
    """Retourne les donnees de voix formatees pour le template."""
    native = [
        {"name": name, "gender": info["gender"], "native_lang": info["native_lang"]}
        for name, info in PRESET_VOICES.items()
    ]
    custom = list_custom_voices()

    return {
        "native": native,
        "custom": custom,
        "native_count": len(native),
        "custom_count": len(custom),
    }


def get_models_status_for_template() -> dict:
    """Retourne le statut des modeles pour le template."""
    return {
        "voice_design_loaded": _models_module.voice_design_model is not None,
        "voice_clone_loaded": _models_module.voice_clone_model is not None,
        "preset_voice_loaded": _models_module.preset_voice_model is not None,
        "clone_1_7b_loaded": _models_module.clone_model_1_7b is not None,
        "clone_0_6b_loaded": _models_module.clone_model_0_6b is not None,
        "prompts_cached": len(voice_clone_prompts),
    }


@router.get("/mcp/docs", response_class=HTMLResponse, include_in_schema=False)
async def mcp_docs(request: Request):
    """Page de documentation MCP dynamique."""
    templates = getattr(request.app.state, "templates", None)
    mcp_server = getattr(request.app.state, "mcp_server", None)

    if templates is None:
        return HTMLResponse(
            content="<h1>Erreur</h1><p>Templates non disponibles. Creez le dossier templates/</p>",
            status_code=500
        )

    # Utiliser les outils dynamiques si MCP est actif, sinon fallback sur la liste statique
    tools = get_mcp_tools_from_server(mcp_server) if mcp_server else get_mcp_tools_list()

    return templates.TemplateResponse("mcp_docs.html", {
        "request": request,
        "version": API_VERSION,
        "device": DEVICE,
        "mcp_enabled": mcp_server is not None,
        "tools": tools,
        "voices": get_voices_for_template(),
        "models": get_models_status_for_template(),
        "server_url": str(request.base_url).rstrip("/"),
    })
