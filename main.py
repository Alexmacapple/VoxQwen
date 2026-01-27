"""
TTS-Alex - Qwen3-TTS Local API

API locale pour Mac Studio avec:
- Voice Design (description textuelle)
- Voice Clone (audio de reference)

Usage:
    python main.py
    # API sur http://localhost:8060
"""

import os
import io
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import torch
import soundfile as sf
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# Configuration
MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Device detection pour Mac Studio
if torch.backends.mps.is_available():
    DEVICE = "mps"
elif torch.cuda.is_available():
    DEVICE = "cuda:0"
else:
    DEVICE = "cpu"

# Modeles (charges a la demande)
voice_design_model = None
voice_clone_model = None  # 1.7B-CustomVoice pour /preset/instruct
preset_voice_model = None

# Modeles Base pour clonage (avec create_voice_clone_prompt)
clone_model_1_7b = None  # 1.7B-Base
clone_model_0_6b = None  # 0.6B-Base

# Cache des prompts de clonage vocal (in-memory)
# Structure: {prompt_id: {"prompt_items": [...], "model": "1.7B", "created_at": datetime}}
voice_clone_prompts: Dict[str, Dict[str, Any]] = {}

# Voix prereglees du modele 0.6B-CustomVoice
PRESET_VOICES = {
    "Vivian": {"gender": "Femme", "native_lang": "Chinois", "description": "Voix feminine jeune, vive et legerement incisive"},
    "Serena": {"gender": "Femme", "native_lang": "Chinois", "description": "Voix feminine jeune, chaleureuse et douce"},
    "Uncle_Fu": {"gender": "Homme", "native_lang": "Chinois", "description": "Voix masculine mature avec un timbre grave et veloute"},
    "Dylan": {"gender": "Homme", "native_lang": "Chinois (Pekin)", "description": "Voix masculine jeune de Pekin, claire et naturelle"},
    "Eric": {"gender": "Homme", "native_lang": "Chinois (Sichuan)", "description": "Voix masculine enjouee de Chengdu, legerement rauque"},
    "Ryan": {"gender": "Homme", "native_lang": "Anglais", "description": "Voix masculine dynamique avec un rythme soutenu"},
    "Aiden": {"gender": "Homme", "native_lang": "Anglais", "description": "Voix masculine americaine ensoleillee avec des mediums clairs"},
    "Ono_Anna": {"gender": "Femme", "native_lang": "Japonais", "description": "Voix feminine espiegle avec un timbre leger et agile"},
    "Sohee": {"gender": "Femme", "native_lang": "Coreen", "description": "Voix feminine chaleureuse avec une riche emotion"},
}

app = FastAPI(
    title="Qwen3-TTS API",
    description="""
API locale de synthèse vocale basée sur **Qwen3-TTS** (Alibaba), optimisée pour Mac Studio (Apple Silicon/MPS).

## Fonctionnalités

- **Voice Design** : Générer une voix à partir d'une description textuelle
- **Voice Clone** : Cloner une voix à partir d'un échantillon audio de référence
- **Preset Voices** : 9 voix préréglées avec contrôle émotionnel optionnel

## Modèles utilisés

| Modèle | Usage |
|--------|-------|
| `0.6B-CustomVoice` | Voix préréglées (rapide) |
| `0.6B-Base` | Clonage vocal (rapide) |
| `1.7B-VoiceDesign` | Création de voix par description |
| `1.7B-CustomVoice` | Voix préréglées + émotions |
| `1.7B-Base` | Clonage vocal (haute qualité) |

## Langues supportées

Français, Anglais, Chinois, Japonais, Coréen, Allemand, Russe, Portugais, Espagnol, Italien
""",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ==============================================================================
# MODELS
# ==============================================================================

class DesignRequest(BaseModel):
    """Request pour Voice Design."""
    text: str = Field(..., min_length=1, max_length=10000, description="Texte a synthetiser")
    voice_instruct: str = Field("", description="Description de la voix en langage naturel")
    language: str = Field("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it")


class LanguagesResponse(BaseModel):
    """Response pour liste des langues."""
    languages: list[dict]
    count: int
    models: dict
    device: str


# Mapping des codes langue vers noms complets (requis par Qwen3-TTS)
LANGUAGE_MAP = {
    "fr": "French",
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}


# ==============================================================================
# MODEL LOADING
# ==============================================================================

def load_voice_design_model():
    """Charge le modele Voice Design."""
    global voice_design_model
    if voice_design_model is None:
        print("=" * 60)
        print("Chargement du modele Voice Design...")
        print("Cela peut prendre quelques minutes au premier lancement.")
        print("=" * 60)

        from qwen_tts import Qwen3TTSModel

        # Chemin local du modele
        model_path = MODELS_DIR / "1.7B-VoiceDesign"

        # Pour Mac Studio (MPS), pas de flash_attention_2
        voice_design_model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=DEVICE,
            dtype=torch.float16,  # bfloat16 pas supporte sur MPS
        )
        print(f"Modele Voice Design charge sur {DEVICE}")
    return voice_design_model


def load_voice_clone_model():
    """Charge le modele Voice Clone."""
    global voice_clone_model
    if voice_clone_model is None:
        print("=" * 60)
        print("Chargement du modele Voice Clone...")
        print("Cela peut prendre quelques minutes au premier lancement.")
        print("=" * 60)

        from qwen_tts import Qwen3TTSModel

        # Chemin local du modele (CustomVoice pour le clonage)
        model_path = MODELS_DIR / "1.7B-CustomVoice"

        voice_clone_model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=DEVICE,
            dtype=torch.float16,
        )
        print(f"Modele Voice Clone charge sur {DEVICE}")
    return voice_clone_model


def load_preset_voice_model():
    """Charge le modele Preset Voice (0.6B-CustomVoice)."""
    global preset_voice_model
    if preset_voice_model is None:
        print("=" * 60)
        print("Chargement du modele Preset Voice...")
        print("Cela peut prendre quelques minutes au premier lancement.")
        print("=" * 60)

        from qwen_tts import Qwen3TTSModel

        model_path = MODELS_DIR / "0.6B-CustomVoice"

        preset_voice_model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=DEVICE,
            dtype=torch.float32,  # float32 pour MPS (float16 cause des NaN avec ce modele)
        )
        print(f"Modele Preset Voice charge sur {DEVICE}")
    return preset_voice_model


def load_clone_base_model(model_size: str = "1.7B"):
    """
    Charge le modele Base pour le clonage vocal.

    Les modeles Base supportent create_voice_clone_prompt() contrairement aux CustomVoice.

    Args:
        model_size: "1.7B" (qualite) ou "0.6B" (rapide)

    Returns:
        Le modele charge
    """
    global clone_model_1_7b, clone_model_0_6b

    if model_size == "1.7B":
        if clone_model_1_7b is None:
            print("=" * 60)
            print("Chargement du modele 1.7B-Base pour clonage...")
            print("Cela peut prendre quelques minutes au premier lancement.")
            print("=" * 60)

            from qwen_tts import Qwen3TTSModel

            model_path = MODELS_DIR / "1.7B-Base"
            clone_model_1_7b = Qwen3TTSModel.from_pretrained(
                str(model_path),
                device_map=DEVICE,
                dtype=torch.float16,
            )
            print(f"Modele 1.7B-Base charge sur {DEVICE}")
        return clone_model_1_7b

    elif model_size == "0.6B":
        if clone_model_0_6b is None:
            print("=" * 60)
            print("Chargement du modele 0.6B-Base pour clonage...")
            print("Cela peut prendre quelques minutes au premier lancement.")
            print("=" * 60)

            from qwen_tts import Qwen3TTSModel

            model_path = MODELS_DIR / "0.6B-Base"
            clone_model_0_6b = Qwen3TTSModel.from_pretrained(
                str(model_path),
                device_map=DEVICE,
                dtype=torch.float32,  # float32 pour MPS avec modele 0.6B
            )
            print(f"Modele 0.6B-Base charge sur {DEVICE}")
        return clone_model_0_6b

    else:
        raise ValueError(f"model_size doit etre '1.7B' ou '0.6B', pas '{model_size}'")


# ==============================================================================
# PROMPT STORAGE HELPERS
# ==============================================================================

def store_prompt(prompt_items: Any, model: str) -> str:
    """
    Stocke un prompt de clonage vocal et retourne son ID.

    Args:
        prompt_items: Resultat de create_voice_clone_prompt()
        model: Taille du modele utilise ("1.7B" ou "0.6B")

    Returns:
        prompt_id: UUID unique pour ce prompt
    """
    prompt_id = str(uuid.uuid4())
    voice_clone_prompts[prompt_id] = {
        "prompt_items": prompt_items,
        "model": model,
        "created_at": datetime.now(),
    }
    return prompt_id


def get_prompt(prompt_id: str) -> Optional[Dict[str, Any]]:
    """
    Recupere un prompt stocke par son ID.

    Args:
        prompt_id: UUID du prompt

    Returns:
        Le prompt ou None si non trouve
    """
    return voice_clone_prompts.get(prompt_id)


def delete_prompt(prompt_id: str) -> bool:
    """
    Supprime un prompt stocke.

    Args:
        prompt_id: UUID du prompt

    Returns:
        True si supprime, False si non trouve
    """
    if prompt_id in voice_clone_prompts:
        del voice_clone_prompts[prompt_id]
        return True
    return False


def list_prompts() -> list:
    """
    Liste tous les prompts stockes.

    Returns:
        Liste des prompts avec leurs metadonnees (sans prompt_items)
    """
    return [
        {
            "prompt_id": pid,
            "model": data["model"],
            "created_at": data["created_at"].isoformat(),
        }
        for pid, data in voice_clone_prompts.items()
    ]


# ==============================================================================
# ROUTES
# ==============================================================================

@app.get("/", tags=["Health"])
async def root():
    """Health check."""
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


@app.get("/languages", response_model=LanguagesResponse, tags=["Info"])
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


@app.post("/design", tags=["TTS"])
async def voice_design(request: DesignRequest):
    """
    Voice Design - Genere un audio avec une voix decrite en texte.

    Exemples de voice_instruct:
    - "Voix feminine douce et chaleureuse"
    - "Voix masculine grave et posee"
    - "A young girl laughing, playful voice"

    Retourne: fichier WAV
    """
    try:
        model = load_voice_design_model()

        # Convertir code langue en nom complet
        language = LANGUAGE_MAP.get(request.language, "French")

        # Generer l'audio
        wavs, sr = model.generate_voice_design(
            text=request.text,
            language=language,
            instruct=request.voice_instruct or "Natural and clear voice",
        )

        # Sauvegarder en memoire
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)

        return StreamingResponse(
            audio_buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=voice_design.wav"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clone", tags=["TTS"])
async def voice_clone(
    text: str = Form(..., description="Texte a synthetiser"),
    reference_audio: Optional[UploadFile] = File(None, description="Audio de reference (1-30 sec). Requis si pas de prompt_id."),
    reference_text: str = Form("", description="Transcription de l'audio de reference (REQUIS pour le clonage)"),
    language: str = Form("fr", description="Langue cible"),
    model: str = Form("1.7B", description="Modele: '1.7B' (qualite) ou '0.6B' (rapide)"),
    prompt_id: str = Form("", description="ID d'un prompt existant (si fourni, reference_audio est ignore)"),
):
    """
    Voice Clone - Clone une voix depuis un audio de reference ou un prompt existant.

    Deux modes d'utilisation:
    1. Avec reference_audio + reference_text: L'audio est traite a chaque requete (plus lent)
    2. Avec prompt_id: Reutilise un prompt cree via /clone/prompt (plus rapide)

    **IMPORTANT**: reference_text est obligatoire quand on utilise reference_audio.
    C'est la transcription exacte de ce qui est dit dans l'audio de reference.

    L'audio de reference doit faire entre 1 et 30 secondes.
    Formats supportes: WAV, MP3, FLAC, OGG
    Retourne: fichier WAV
    """
    tmp_path = None
    try:
        # Valider le parametre model
        if model not in ("1.7B", "0.6B"):
            raise HTTPException(
                status_code=400,
                detail=f"model doit etre '1.7B' ou '0.6B', pas '{model}'"
            )

        # Convertir code langue en nom complet
        lang_full = LANGUAGE_MAP.get(language, "French")

        # Mode 1: Utiliser un prompt existant
        if prompt_id:
            prompt_data = get_prompt(prompt_id)
            if not prompt_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Prompt '{prompt_id}' non trouve"
                )

            # Verifier que le modele correspond
            if prompt_data["model"] != model:
                raise HTTPException(
                    status_code=400,
                    detail=f"Le prompt a ete cree avec le modele {prompt_data['model']}, pas {model}"
                )

            # Charger le modele Base
            tts_model = load_clone_base_model(model)

            # Generer avec le prompt stocke
            wavs, sr = tts_model.generate_voice_clone(
                text=text,
                language=lang_full,
                voice_clone_prompt=prompt_data["prompt_items"],
            )

        # Mode 2: Traiter l'audio de reference a la volee
        else:
            # Verifier le fichier audio
            if not reference_audio or not reference_audio.filename:
                raise HTTPException(
                    status_code=400,
                    detail="reference_audio requis si prompt_id n'est pas fourni"
                )

            # Verifier la transcription (obligatoire pour le mode ICL)
            if not reference_text or not reference_text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="reference_text est obligatoire. Fournissez la transcription exacte de l'audio de reference."
                )

            # Lire l'audio de reference
            audio_bytes = await reference_audio.read()

            # Sauvegarder temporairement
            suffix = Path(reference_audio.filename).suffix or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            # Verifier la duree
            import torchaudio
            waveform, sample_rate = torchaudio.load(tmp_path)
            duration = waveform.shape[1] / sample_rate

            if duration < 1:
                raise HTTPException(status_code=400, detail=f"Audio trop court: {duration:.1f}s (min: 1s)")
            if duration > 30:
                raise HTTPException(status_code=400, detail=f"Audio trop long: {duration:.1f}s (max: 30s)")

            # Charger le modele Base (pas CustomVoice!)
            tts_model = load_clone_base_model(model)

            # Generer l'audio clone
            wavs, sr = tts_model.generate_voice_clone(
                text=text,
                language=lang_full,
                ref_audio=tmp_path,
                ref_text=reference_text,
            )

        # Sauvegarder en memoire
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


@app.post("/clone/prompt", tags=["TTS"])
async def create_clone_prompt(
    reference_audio: UploadFile = File(..., description="Audio de reference (1-30 sec)"),
    reference_text: str = Form(..., description="Transcription de l'audio de reference (REQUIS)"),
    model: str = Form("1.7B", description="Modele: '1.7B' (qualite) ou '0.6B' (rapide)"),
):
    """
    Cree un prompt reutilisable pour Voice Clone.

    Utile pour generer plusieurs phrases avec la meme voix
    sans retraiter l'audio de reference a chaque fois.

    **IMPORTANT**: reference_text est obligatoire.
    C'est la transcription exacte de ce qui est dit dans l'audio de reference.

    Le prompt est stocke en memoire et peut etre reutilise via son prompt_id
    dans la route /clone.

    Retourne:
    - prompt_id: UUID unique pour ce prompt
    - model: Modele utilise
    - created_at: Date de creation
    """
    tmp_path = None
    try:
        # Valider le parametre model
        if model not in ("1.7B", "0.6B"):
            raise HTTPException(
                status_code=400,
                detail=f"model doit etre '1.7B' ou '0.6B', pas '{model}'"
            )

        # Verifier le fichier audio
        if not reference_audio.filename:
            raise HTTPException(status_code=400, detail="Fichier audio requis")

        audio_bytes = await reference_audio.read()

        suffix = Path(reference_audio.filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # Verifier la duree
        import torchaudio
        waveform, sample_rate = torchaudio.load(tmp_path)
        duration = waveform.shape[1] / sample_rate

        if duration < 1:
            raise HTTPException(status_code=400, detail=f"Audio trop court: {duration:.1f}s (min: 1s)")
        if duration > 30:
            raise HTTPException(status_code=400, detail=f"Audio trop long: {duration:.1f}s (max: 30s)")

        # Charger le modele Base (pas CustomVoice!)
        tts_model = load_clone_base_model(model)

        # Creer le prompt
        prompt_items = tts_model.create_voice_clone_prompt(
            ref_audio=tmp_path,
            ref_text=reference_text,
        )

        # Nettoyer le fichier temporaire
        os.unlink(tmp_path)
        tmp_path = None

        # Stocker le prompt
        prompt_id = store_prompt(prompt_items, model)
        prompt_data = get_prompt(prompt_id)

        return JSONResponse({
            "prompt_id": prompt_id,
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


@app.get("/clone/prompts", tags=["TTS"])
async def list_clone_prompts():
    """
    Liste tous les prompts de clonage vocal en cache.

    Retourne:
    - prompts: Liste des prompts avec leurs metadonnees
    - count: Nombre total de prompts
    """
    prompts = list_prompts()
    return {
        "prompts": prompts,
        "count": len(prompts),
    }


@app.delete("/clone/prompts/{prompt_id}", tags=["TTS"])
async def delete_clone_prompt(prompt_id: str):
    """
    Supprime un prompt de clonage vocal du cache.

    Args:
        prompt_id: UUID du prompt a supprimer

    Retourne:
    - status: "deleted" si supprime
    - prompt_id: UUID du prompt supprime
    """
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


@app.get("/voices", tags=["TTS"])
async def list_voices():
    """
    Liste les voix prereglees disponibles (modele 0.6B-CustomVoice).

    9 voix avec leurs caracteristiques.
    """
    voices = [
        {"name": name, **info}
        for name, info in PRESET_VOICES.items()
    ]
    return {
        "voices": voices,
        "count": len(PRESET_VOICES),
        "model": "0.6B-CustomVoice",
        "note": "Toutes les voix supportent les 10 langues"
    }


@app.post("/preset", tags=["TTS"])
async def preset_voice(
    text: str = Form(..., min_length=1, max_length=10000, description="Texte a synthetiser"),
    voice: str = Form("Serena", description="Nom de la voix prereglée"),
    language: str = Form("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it")
):
    """
    Preset Voice - Genere un audio avec une voix prereglée.

    Plus rapide que Voice Design/Clone car modele plus leger (0.6B).

    Voix disponibles: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

    Retourne: fichier WAV
    """
    try:
        # Verifier que la voix existe
        if voice not in PRESET_VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voix '{voice}' inconnue. Disponibles: {', '.join(PRESET_VOICES.keys())}"
            )

        model = load_preset_voice_model()

        # Convertir code langue en nom complet
        language_full = LANGUAGE_MAP.get(language, "French")

        # Generer l'audio
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language_full,
            speaker=voice,
        )

        # Sauvegarder en memoire
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)

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


@app.post("/preset/instruct", tags=["TTS"])
async def preset_voice_with_instruct(
    text: str = Form(..., min_length=1, max_length=10000, description="Texte a synthetiser"),
    voice: str = Form("Serena", description="Nom de la voix prereglée"),
    instruct: str = Form("", description="Instruction pour controler l'emotion/style (ex: 'Ton joyeux et excite', 'Chuchotant doucement')"),
    language: str = Form("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it")
):
    """
    Preset Voice avec controle emotionnel - Genere un audio avec une voix prereglée
    et controle fin des emotions/styles via instructions.

    Utilise le modele 1.7B-CustomVoice (plus lourd mais plus expressif).

    Exemples d'instructions:
    - Emotions: "Ton joyeux et excite", "Triste et melancolique", "En colere"
    - Styles: "Chuchotant doucement", "Parlant tres vite", "Tres dramatique"
    - Scenarios: "Commentateur sportif energique", "Presentation professionnelle"

    Voix disponibles: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

    Retourne: fichier WAV
    """
    try:
        # Verifier que la voix existe
        if voice not in PRESET_VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Voix '{voice}' inconnue. Disponibles: {', '.join(PRESET_VOICES.keys())}"
            )

        model = load_voice_clone_model()  # 1.7B-CustomVoice

        # Convertir code langue en nom complet
        language_full = LANGUAGE_MAP.get(language, "French")

        # Generer l'audio avec instruction
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language_full,
            speaker=voice,
            instruct=instruct if instruct else "",
        )

        # Sauvegarder en memoire
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, wavs[0], sr, format="WAV")
        audio_buffer.seek(0)

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


@app.get("/models/status", tags=["Info"])
async def models_status():
    """Verifie le statut des modeles charges."""
    return {
        "voice_design_loaded": voice_design_model is not None,
        "voice_clone_loaded": voice_clone_model is not None,  # 1.7B-CustomVoice
        "preset_voice_loaded": preset_voice_model is not None,  # 0.6B-CustomVoice
        "clone_1_7b_loaded": clone_model_1_7b is not None,  # 1.7B-Base
        "clone_0_6b_loaded": clone_model_0_6b is not None,  # 0.6B-Base
        "prompts_cached": len(voice_clone_prompts),
        "device": DEVICE,
        "mps_available": torch.backends.mps.is_available(),
        "cuda_available": torch.cuda.is_available(),
        "models_dir": str(MODELS_DIR),
    }


@app.post("/models/preload", tags=["Info"])
async def preload_models(
    design: bool = False,
    clone: bool = False,
    preset: bool = True,
    clone_1_7b: bool = False,
    clone_0_6b: bool = False,
):
    """
    Pre-charge les modeles en memoire.

    Utile pour eviter le temps de chargement au premier appel.
    Par defaut, charge le modele preset (le plus leger).

    Args:
        design: Charger 1.7B-VoiceDesign
        clone: Charger 1.7B-CustomVoice (pour /preset/instruct)
        preset: Charger 0.6B-CustomVoice (pour /preset)
        clone_1_7b: Charger 1.7B-Base (pour /clone haute qualite)
        clone_0_6b: Charger 0.6B-Base (pour /clone rapide)
    """
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


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    import uvicorn

    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║                     TTS-ALEX                             ║
    ║          Qwen3-TTS Local API for Mac Studio              ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Device: {DEVICE:<47} ║
    ║  MPS Available: {str(torch.backends.mps.is_available()):<40} ║
    ║  CUDA Available: {str(torch.cuda.is_available()):<39} ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Routes:                                                 ║
    ║    GET  /                 - Health check                 ║
    ║    GET  /languages        - Liste des langues            ║
    ║    GET  /voices           - Voix prereglees              ║
    ║    POST /preset           - Voix prereglees (0.6B)       ║
    ║    POST /preset/instruct  - Voix + emotions (1.7B)       ║
    ║    POST /design           - Voice Design                 ║
    ║    POST /clone            - Voice Clone                  ║
    ║    POST /clone/prompt     - Creer prompt reutilisable    ║
    ║    GET  /clone/prompts    - Lister prompts caches        ║
    ║    DEL  /clone/prompts/id - Supprimer prompt             ║
    ║    GET  /models/status    - Statut des modeles           ║
    ║    POST /models/preload   - Pre-charger modeles          ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Docs: http://localhost:8060/docs                        ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=8060)
