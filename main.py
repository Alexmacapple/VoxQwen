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
import re
import json
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import torch
import soundfile as sf
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# Détection automatique de langue (lazy import)
langdetect_available = False
try:
    from langdetect import detect as langdetect_detect
    langdetect_available = True
except ImportError:
    pass

# Configuration
MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# Version API
API_VERSION = "1.3.0"

# Répertoire des voix personnalisées persistantes
CUSTOM_VOICES_DIR = Path(__file__).parent / "voices" / "custom"
CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)

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

# Cache des prompts de clonage vocal (in-memory, volatile)
# Structure: {prompt_id: {"prompt_items": [...], "model": "1.7B", "created_at": datetime}}
voice_clone_prompts: Dict[str, Dict[str, Any]] = {}

# Voix personnalisées persistantes (chargées depuis disque)
# Structure: {name: {"meta": {...}, "prompt_items": ... ou None si pas encore chargé}}
custom_voices: Dict[str, Dict[str, Any]] = {}

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
- **Voix Personnalisées** : Sauvegarder vos voix créées de façon persistante
- **Batch Processing** : Générer plusieurs audios en une seule requête (ZIP)
- **Auto Language** : Détection automatique de la langue (language="auto")
- **Tokenizer API** : Encoder/décoder du texte en tokens
- **MCP Support** : Intégration Model Context Protocol pour Claude Code

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

**+ Détection automatique** : Utilisez `language="auto"` pour une détection automatique.

## Documentation MCP

Pour l'intégration avec Claude Code via MCP, consultez [/mcp/docs](/mcp/docs).
""",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Montage des fichiers statiques
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates Jinja2
templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None

# ==============================================================================
# MODELS
# ==============================================================================

class DesignRequest(BaseModel):
    """Requête pour Voice Design."""
    text: str = Field(..., min_length=1, max_length=10000, description="Texte à synthétiser")
    voice_instruct: str = Field("", description="Description de la voix en langage naturel")
    language: str = Field("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it, auto")


class BatchPresetRequest(BaseModel):
    """Requête pour batch preset voice."""
    texts: List[str] = Field(..., min_length=1, max_length=100, description="Liste de textes à synthétiser (max 100)")
    voice: str = Field("Serena", description="Nom de la voix (native ou personnalisée)")
    language: str = Field("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it, auto")


class BatchDesignRequest(BaseModel):
    """Requête pour batch voice design."""
    texts: List[str] = Field(..., min_length=1, max_length=100, description="Liste de textes à synthétiser (max 100)")
    voice_instruct: str = Field("", description="Description de la voix en langage naturel")
    language: str = Field("fr", description="Langue: fr, en, zh, ja, ko, de, ru, pt, es, it, auto")


class TokenizeRequest(BaseModel):
    """Requête pour tokenizer encode."""
    text: str = Field(..., min_length=1, description="Texte à encoder")


class DetokenizeRequest(BaseModel):
    """Requête pour tokenizer decode."""
    tokens: List[int] = Field(..., min_length=1, description="Liste de tokens à décoder")


class LanguagesResponse(BaseModel):
    """Réponse pour la liste des langues."""
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

# Mapping inverse pour langdetect -> code API
LANGDETECT_TO_CODE = {
    "fr": "fr",
    "en": "en",
    "zh-cn": "zh",
    "zh-tw": "zh",
    "ja": "ja",
    "ko": "ko",
    "de": "de",
    "ru": "ru",
    "pt": "pt",
    "es": "es",
    "it": "it",
}


def detect_language(text: str) -> str:
    """
    Détecte automatiquement la langue d'un texte.

    Args:
        text: Texte à analyser

    Returns:
        Code langue (fr, en, zh, etc.) ou "fr" par défaut
    """
    if not langdetect_available:
        return "fr"  # Fallback si langdetect non installé

    try:
        detected = langdetect_detect(text)
        # Convertir le code langdetect vers notre code API
        return LANGDETECT_TO_CODE.get(detected, "fr")
    except Exception:
        return "fr"  # Fallback en cas d'erreur


def resolve_language(language: str, text: str = "") -> str:
    """
    Résout le code langue en nom complet, avec support pour "auto".

    Args:
        language: Code langue ou "auto"
        text: Texte pour détection automatique (si language="auto")

    Returns:
        Nom complet de la langue (French, English, etc.)
    """
    if language == "auto":
        detected_code = detect_language(text)
        return LANGUAGE_MAP.get(detected_code, "French")
    return LANGUAGE_MAP.get(language, "French")


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

def store_prompt(prompt_items: Any, model: str, name: Optional[str] = None) -> str:
    """
    Stocke un prompt de clonage vocal et retourne son ID.

    ⚠️ IMPORTANT: Les prompts sont stockes en MEMOIRE uniquement.
    Ils sont perdus au redemarrage du serveur.

    Args:
        prompt_items: Resultat de create_voice_clone_prompt()
        model: Taille du modele utilise ("1.7B" ou "0.6B")
        name: Nom optionnel pour identifier le prompt (ex: "voix_yves")

    Returns:
        prompt_id: UUID unique pour ce prompt
    """
    prompt_id = str(uuid.uuid4())
    voice_clone_prompts[prompt_id] = {
        "prompt_items": prompt_items,
        "model": model,
        "name": name,
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

    ⚠️ IMPORTANT: Les prompts sont stockes en MEMOIRE uniquement.
    Ils sont perdus au redemarrage du serveur.

    Returns:
        Liste des prompts avec leurs metadonnees (sans prompt_items)
    """
    return [
        {
            "prompt_id": pid,
            "name": data.get("name"),
            "model": data["model"],
            "created_at": data["created_at"].isoformat(),
        }
        for pid, data in voice_clone_prompts.items()
    ]


# ==============================================================================
# CUSTOM VOICES MANAGEMENT (Persistantes)
# ==============================================================================

def validate_voice_name(name: str) -> bool:
    """
    Valide le nom d'une voix personnalisée.

    Règles :
    - 3 à 50 caractères
    - Alphanumérique + tirets + underscores uniquement
    - Pas de noms réservés (voix natives)

    Returns:
        True si valide, False sinon
    """
    if not name or len(name) < 3 or len(name) > 50:
        return False
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return False
    if name in PRESET_VOICES:
        return False
    return True


def get_native_voice_names() -> set:
    """Retourne les noms des voix natives (réservés)."""
    return set(PRESET_VOICES.keys())


def load_custom_voices():
    """
    Charge les métadonnées des voix personnalisées depuis le disque.
    Les embeddings (prompt.pt) sont chargés en lazy loading.
    """
    global custom_voices
    custom_voices = {}

    if not CUSTOM_VOICES_DIR.exists():
        return

    for voice_dir in CUSTOM_VOICES_DIR.iterdir():
        if not voice_dir.is_dir():
            continue

        meta_file = voice_dir / "meta.json"
        if not meta_file.exists():
            continue

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            custom_voices[voice_dir.name] = {
                "meta": meta,
                "prompt_items": None,  # Lazy loading
            }
        except Exception as e:
            print(f"Erreur chargement voix {voice_dir.name}: {e}")


def get_custom_voice_prompt(name: str):
    """
    Récupère les embeddings d'une voix personnalisée (lazy loading).

    Args:
        name: Nom de la voix

    Returns:
        Les prompt_items ou None si non trouvé
    """
    if name not in custom_voices:
        return None

    voice_data = custom_voices[name]

    # Lazy loading: charger les embeddings si pas encore en mémoire
    if voice_data["prompt_items"] is None:
        prompt_file = CUSTOM_VOICES_DIR / name / "prompt.pt"
        if prompt_file.exists():
            try:
                voice_data["prompt_items"] = torch.load(prompt_file, map_location=DEVICE)
            except Exception as e:
                print(f"Erreur chargement embeddings {name}: {e}")
                return None

    return voice_data["prompt_items"]


def save_custom_voice(name: str, prompt_items: Any, source: str, model: str,
                      description: str = "", language: str = "fr") -> Dict[str, Any]:
    """
    Sauvegarde une voix personnalisée sur disque.

    Args:
        name: Nom de la voix (validé au préalable)
        prompt_items: Embeddings de la voix
        source: "clone" ou "design"
        model: "1.7B" ou "0.6B"
        description: Description optionnelle
        language: Langue de la voix

    Returns:
        Les métadonnées de la voix créée
    """
    voice_dir = CUSTOM_VOICES_DIR / name
    voice_dir.mkdir(parents=True, exist_ok=True)

    # Métadonnées
    meta = {
        "name": name,
        "source": source,
        "model": model,
        "description": description,
        "language": language,
        "created_at": datetime.now().isoformat(),
        "version": "1.0",
    }

    # Sauvegarder meta.json
    meta_file = voice_dir / "meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # Sauvegarder prompt.pt (atomic write)
    prompt_file = voice_dir / "prompt.pt"
    tmp_file = voice_dir / "prompt.pt.tmp"
    torch.save(prompt_items, tmp_file)
    tmp_file.rename(prompt_file)

    # Mettre en cache
    custom_voices[name] = {
        "meta": meta,
        "prompt_items": prompt_items,
    }

    return meta


def delete_custom_voice(name: str) -> bool:
    """
    Supprime une voix personnalisée du disque et de la mémoire.

    Args:
        name: Nom de la voix

    Returns:
        True si supprimée, False si non trouvée
    """
    if name not in custom_voices:
        return False

    voice_dir = CUSTOM_VOICES_DIR / name
    if voice_dir.exists():
        shutil.rmtree(voice_dir)

    del custom_voices[name]
    return True


def list_custom_voices() -> list:
    """
    Liste toutes les voix personnalisées.

    Returns:
        Liste des métadonnées des voix custom
    """
    return [
        {
            "name": name,
            "type": "custom",
            **{k: v for k, v in data["meta"].items() if k != "name"}
        }
        for name, data in custom_voices.items()
    ]


def get_all_voice_names() -> set:
    """Retourne tous les noms de voix (natives + custom)."""
    return get_native_voice_names() | set(custom_voices.keys())


# ==============================================================================
# ROUTES
# ==============================================================================

@app.get("/", tags=["Santé"])
async def root():
    """Vérification de l'état du serveur."""
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


@app.get("/languages", response_model=LanguagesResponse, tags=["Informations"])
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


@app.post("/design", tags=["Synthèse vocale"])
async def voice_design(request: DesignRequest):
    """
    Voice Design - Génère un audio avec une voix décrite en texte.

    Exemples de voice_instruct :
    - "Voix féminine douce et chaleureuse"
    - "Voix masculine grave et posée"
    - "Jeune fille riant, voix enjouée"

    Retourne : fichier WAV
    """
    try:
        model = load_voice_design_model()

        # Convertir code langue en nom complet
        language = LANGUAGE_MAP.get(request.language, "French")

        # Generer l'audio
        wavs, sr = model.generate_voice_design(
            text=request.text,
            language=language,
            instruct=request.voice_instruct or "Voix naturelle et claire",
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


@app.post("/clone", tags=["Synthèse vocale"])
async def voice_clone(
    text: str = Form(..., description="Texte à synthétiser"),
    reference_audio: Optional[UploadFile] = File(None, description="Audio de référence (1-30 sec). Requis si pas de prompt_id."),
    reference_text: str = Form("", description="Transcription de l'audio de référence (REQUIS pour le clonage)"),
    language: str = Form("fr", description="Langue cible"),
    model: str = Form("1.7B", description="Modèle : '1.7B' (qualité) ou '0.6B' (rapide)"),
    prompt_id: str = Form("", description="ID d'un prompt existant (si fourni, reference_audio est ignoré)"),
):
    """
    Voice Clone - Clone une voix depuis un audio de référence ou un prompt existant.

    Deux modes d'utilisation :
    1. Avec reference_audio + reference_text : L'audio est traité à chaque requête (plus lent)
    2. Avec prompt_id : Réutilise un prompt créé via /clone/prompt (plus rapide)

    **IMPORTANT** : reference_text est obligatoire quand on utilise reference_audio.
    C'est la transcription exacte de ce qui est dit dans l'audio de référence.

    L'audio de référence doit faire entre 1 et 30 secondes.
    Formats supportés : WAV, MP3, FLAC, OGG

    Retourne : fichier WAV
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


@app.post("/clone/prompt", tags=["Synthèse vocale"])
async def create_clone_prompt(
    reference_audio: UploadFile = File(..., description="Audio de référence (1-30 sec)"),
    reference_text: str = Form(..., description="Transcription de l'audio de référence (REQUIS)"),
    model: str = Form("1.7B", description="Modèle : '1.7B' (qualité) ou '0.6B' (rapide)"),
    name: Optional[str] = Form(None, description="Nom pour identifier le prompt (ex : 'voix_yves')"),
    x_vector_only: bool = Form(False, description="Si True, retourne uniquement l'embedding x-vector sans stocker le prompt"),
):
    """
    Crée un prompt réutilisable pour Voice Clone.

    Utile pour générer plusieurs phrases avec la même voix
    sans retraiter l'audio de référence à chaque fois.

    **IMPORTANT** : reference_text est obligatoire.
    C'est la transcription exacte de ce qui est dit dans l'audio de référence.

    ⚠️ **ATTENTION** : Les prompts sont stockés en MÉMOIRE uniquement.
    Ils sont perdus au redémarrage du serveur.
    Conservez votre fichier audio source pour recréer le prompt si nécessaire.

    Le prompt est stocké en mémoire et peut être réutilisé via son prompt_id
    dans la route /clone.

    **Mode x_vector_only** : Si activé, retourne uniquement les embeddings (x-vector)
    sans stocker le prompt. Utile pour l'analyse ou le stockage externe des embeddings.

    Retourne :
    - prompt_id : UUID unique pour ce prompt (sauf si x_vector_only=True)
    - name : Nom du prompt (si fourni)
    - model : Modèle utilisé
    - created_at : Date de création
    - x_vector : Embeddings (si x_vector_only=True)
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

        # Mode x_vector_only : retourner uniquement les embeddings
        if x_vector_only:
            # Extraire les x-vectors si disponibles dans prompt_items
            # La structure dépend de l'implémentation de Qwen3-TTS
            x_vector_data = None

            def serialize_value(v):
                """Convertit une valeur en format JSON-sérialisable."""
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
                # Pour les objets comme VoiceClonePromptItem
                x_vector_data = {k: serialize_value(v) for k, v in vars(prompt_items).items() if not k.startswith('_')}
            else:
                x_vector_data = serialize_value(prompt_items)

            return JSONResponse({
                "mode": "x_vector_only",
                "model": model,
                "duration_seconds": duration,
                "x_vector": x_vector_data,
            })

        # Stocker le prompt
        prompt_id = store_prompt(prompt_items, model, name)
        prompt_data = get_prompt(prompt_id)

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


@app.get("/clone/prompts", tags=["Synthèse vocale"])
async def list_clone_prompts():
    """
    Liste tous les prompts de clonage vocal en cache.

    ⚠️ **ATTENTION** : Les prompts sont stockés en MÉMOIRE uniquement.
    Ils sont perdus au redémarrage du serveur.

    Retourne :
    - prompts : Liste des prompts avec leurs métadonnées (prompt_id, name, model, created_at)
    - count : Nombre total de prompts
    - warning : Rappel que les prompts sont volatils
    """
    prompts = list_prompts()
    return {
        "prompts": prompts,
        "count": len(prompts),
        "warning": "Les prompts sont stockés en mémoire et perdus au redémarrage du serveur.",
    }


@app.delete("/clone/prompts/{prompt_id}", tags=["Synthèse vocale"])
async def delete_clone_prompt(prompt_id: str):
    """
    Supprime un prompt de clonage vocal du cache.

    Paramètres :
        prompt_id : UUID du prompt à supprimer

    Retourne :
    - status : "deleted" si supprimé
    - prompt_id : UUID du prompt supprimé
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


@app.get("/voices", tags=["Synthèse vocale"])
async def list_voices():
    """
    Liste toutes les voix disponibles (natives + personnalisées).

    - 9 voix natives préréglées (Vivian, Serena, etc.)
    - Voix personnalisées créées via POST /voices/custom
    """
    # Voix natives
    native_voices = [
        {"name": name, "type": "native", **info}
        for name, info in PRESET_VOICES.items()
    ]

    # Voix personnalisées
    custom = list_custom_voices()

    all_voices = native_voices + custom

    return {
        "voices": all_voices,
        "count": len(all_voices),
        "native_count": len(native_voices),
        "custom_count": len(custom),
        "note": "Toutes les voix supportent les 10 langues"
    }


@app.post("/voices/custom", tags=["Synthèse vocale"])
async def create_custom_voice(
    name: str = Form(..., description="Nom unique de la voix (3-50 chars, alphanum + tirets)"),
    source: str = Form(..., description="Source : 'clone' ou 'design'"),
    description: str = Form("", description="Description de la voix (max 200 chars)"),
    # Pour source=clone
    reference_audio: Optional[UploadFile] = File(None, description="Audio de référence (requis si source=clone)"),
    reference_text: str = Form("", description="Transcription de l'audio (requis si source=clone)"),
    model: str = Form("1.7B", description="Modèle : '1.7B' (qualité) ou '0.6B' (rapide)"),
    # Pour source=design
    voice_description: str = Form("", description="Description textuelle de la voix (requis si source=design)"),
    language: str = Form("fr", description="Langue : fr, en, zh, ja, ko, de, ru, pt, es, it"),
):
    """
    Crée une voix personnalisée persistante.

    Deux modes :
    - **source=clone** : Clone une voix depuis un audio de référence
    - **source=design** : Crée une voix depuis une description textuelle

    La voix est sauvegardée sur disque et disponible après redémarrage.
    Elle apparaît dans GET /voices et peut être utilisée dans POST /preset.

    Retourne :
    - name : Nom de la voix créée
    - type : "custom"
    - source : "clone" ou "design"
    - created_at : Date de création
    """
    tmp_path = None
    try:
        # Valider le nom
        if not validate_voice_name(name):
            raise HTTPException(
                status_code=400,
                detail=f"Nom invalide. Règles : 3-50 chars, alphanum + tirets, pas de nom réservé ({', '.join(PRESET_VOICES.keys())})"
            )

        # Vérifier que le nom n'existe pas déjà
        if name in custom_voices:
            raise HTTPException(
                status_code=400,
                detail=f"Une voix personnalisée '{name}' existe déjà"
            )

        # Valider la source
        if source not in ("clone", "design"):
            raise HTTPException(
                status_code=400,
                detail="source doit être 'clone' ou 'design'"
            )

        # Valider le modèle
        if model not in ("1.7B", "0.6B"):
            raise HTTPException(
                status_code=400,
                detail=f"model doit être '1.7B' ou '0.6B', pas '{model}'"
            )

        # Limiter la description
        if len(description) > 200:
            description = description[:200]

        # Convertir code langue en nom complet
        lang_full = LANGUAGE_MAP.get(language, "French")

        if source == "clone":
            # Mode clonage
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

            # Lire et sauvegarder l'audio temporairement
            audio_bytes = await reference_audio.read()
            suffix = Path(reference_audio.filename).suffix or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            # Vérifier la durée
            import torchaudio
            waveform, sample_rate = torchaudio.load(tmp_path)
            duration = waveform.shape[1] / sample_rate

            if duration < 1:
                raise HTTPException(status_code=400, detail=f"Audio trop court : {duration:.1f}s (min: 1s)")
            if duration > 30:
                raise HTTPException(status_code=400, detail=f"Audio trop long : {duration:.1f}s (max: 30s)")

            # Charger le modèle et créer le prompt
            tts_model = load_clone_base_model(model)
            prompt_items = tts_model.create_voice_clone_prompt(
                ref_audio=tmp_path,
                ref_text=reference_text,
            )

        else:
            # Mode design
            if not voice_description or not voice_description.strip():
                raise HTTPException(
                    status_code=400,
                    detail="voice_description est requis pour source=design"
                )

            # Charger le modèle Voice Design
            tts_model = load_voice_design_model()

            # Générer un audio court pour extraire les embeddings
            # Note: Voice Design ne crée pas de prompt réutilisable directement,
            # on génère un échantillon et on stocke la description pour régénérer
            wavs, sr = tts_model.generate_voice_design(
                text="Test de voix.",
                language=lang_full,
                instruct=voice_description,
            )

            # Pour Voice Design, on stocke la description comme "prompt"
            # car il n'y a pas d'embeddings extractibles
            prompt_items = {
                "type": "design",
                "voice_description": voice_description,
                "language": lang_full,
            }

        # Sauvegarder la voix
        meta = save_custom_voice(
            name=name,
            prompt_items=prompt_items,
            source=source,
            model=model,
            description=description,
            language=language,
        )

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


@app.get("/voices/custom/{name}", tags=["Synthèse vocale"])
async def get_custom_voice_details(name: str):
    """
    Détails d'une voix personnalisée.

    Retourne les métadonnées complètes de la voix.
    """
    if name not in custom_voices:
        raise HTTPException(
            status_code=404,
            detail=f"Voix personnalisée '{name}' non trouvée"
        )

    voice_data = custom_voices[name]
    meta = voice_data["meta"]

    # Calculer la taille du fichier prompt.pt
    prompt_file = CUSTOM_VOICES_DIR / name / "prompt.pt"
    file_size = prompt_file.stat().st_size if prompt_file.exists() else 0

    return {
        "name": name,
        "type": "custom",
        **{k: v for k, v in meta.items() if k != "name"},
        "file_size_bytes": file_size,
        "loaded_in_memory": voice_data["prompt_items"] is not None,
    }


@app.delete("/voices/custom/{name}", tags=["Synthèse vocale"])
async def delete_custom_voice_route(name: str):
    """
    Supprime une voix personnalisée.

    La voix est supprimée du disque et de la mémoire.
    Les voix natives ne peuvent pas être supprimées.

    Retourne :
    - status : "deleted"
    - name : Nom de la voix supprimée
    """
    # Vérifier que ce n'est pas une voix native
    if name in PRESET_VOICES:
        raise HTTPException(
            status_code=403,
            detail=f"Impossible de supprimer la voix native '{name}'"
        )

    if not delete_custom_voice(name):
        raise HTTPException(
            status_code=404,
            detail=f"Voix personnalisée '{name}' non trouvée"
        )

    return {
        "status": "deleted",
        "name": name,
    }


@app.post("/preset", tags=["Synthèse vocale"])
async def preset_voice(
    text: str = Form(..., min_length=1, max_length=10000, description="Texte à synthétiser"),
    voice: str = Form("Serena", description="Nom de la voix (native ou personnalisée)"),
    language: str = Form("fr", description="Langue : fr, en, zh, ja, ko, de, ru, pt, es, it")
):
    """
    Preset Voice - Génère un audio avec une voix préréglée ou personnalisée.

    Accepte les voix natives (Vivian, Serena, etc.) et les voix personnalisées
    créées via POST /voices/custom.

    Pour les voix natives : utilise le modèle 0.6B (rapide).
    Pour les voix custom : utilise le modèle avec lequel elles ont été créées.

    Retourne : fichier WAV
    """
    try:
        # Convertir code langue en nom complet
        language_full = LANGUAGE_MAP.get(language, "French")

        # Vérifier si c'est une voix native
        if voice in PRESET_VOICES:
            model = load_preset_voice_model()
            wavs, sr = model.generate_custom_voice(
                text=text,
                language=language_full,
                speaker=voice,
            )

        # Vérifier si c'est une voix personnalisée
        elif voice in custom_voices:
            voice_data = custom_voices[voice]
            meta = voice_data["meta"]
            prompt_items = get_custom_voice_prompt(voice)

            if prompt_items is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"Impossible de charger les embeddings de la voix '{voice}'"
                )

            # Si c'est une voix design, régénérer avec la description
            if meta.get("source") == "design" and isinstance(prompt_items, dict) and prompt_items.get("type") == "design":
                tts_model = load_voice_design_model()
                wavs, sr = tts_model.generate_voice_design(
                    text=text,
                    language=language_full,
                    instruct=prompt_items["voice_description"],
                )
            else:
                # Voix clonée : utiliser le prompt
                model_size = meta.get("model", "1.7B")
                tts_model = load_clone_base_model(model_size)
                wavs, sr = tts_model.generate_voice_clone(
                    text=text,
                    language=language_full,
                    voice_clone_prompt=prompt_items,
                )

        else:
            all_voices = list(PRESET_VOICES.keys()) + list(custom_voices.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Voix '{voice}' inconnue. Disponibles : {', '.join(all_voices)}"
            )

        # Sauvegarder en mémoire
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


@app.post("/preset/instruct", tags=["Synthèse vocale"])
async def preset_voice_with_instruct(
    text: str = Form(..., min_length=1, max_length=10000, description="Texte à synthétiser"),
    voice: str = Form("Serena", description="Nom de la voix (native uniquement pour instruct)"),
    instruct: str = Form("", description="Instruction pour contrôler l'émotion/style (ex : 'Ton joyeux et excité', 'Chuchotant doucement')"),
    language: str = Form("fr", description="Langue : fr, en, zh, ja, ko, de, ru, pt, es, it")
):
    """
    Preset Voice avec contrôle émotionnel - Génère un audio avec une voix préréglée
    et contrôle fin des émotions/styles via instructions.

    Utilise le modèle 1.7B-CustomVoice (plus lourd mais plus expressif).

    **Note** : Cette route ne supporte que les voix natives. Pour les voix personnalisées,
    utilisez POST /preset.

    Exemples d'instructions :
    - Émotions : "Ton joyeux et excité", "Triste et mélancolique", "En colère"
    - Styles : "Chuchotant doucement", "Parlant très vite", "Très dramatique"
    - Scénarios : "Commentateur sportif énergique", "Présentation professionnelle"

    Voix disponibles : Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

    Retourne : fichier WAV
    """
    try:
        # Vérifier que la voix existe (natives uniquement pour instruct)
        if voice not in PRESET_VOICES:
            if voice in custom_voices:
                raise HTTPException(
                    status_code=400,
                    detail=f"La voix personnalisée '{voice}' ne supporte pas /preset/instruct. Utilisez /preset."
                )
            raise HTTPException(
                status_code=400,
                detail=f"Voix '{voice}' inconnue. Disponibles : {', '.join(PRESET_VOICES.keys())}"
            )

        model = load_voice_clone_model()  # 1.7B-CustomVoice

        # Convertir code langue en nom complet
        language_full = LANGUAGE_MAP.get(language, "French")

        # Générer l'audio avec instruction
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language_full,
            speaker=voice,
            instruct=instruct if instruct else "",
        )

        # Sauvegarder en mémoire
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


@app.get("/models/status", tags=["Informations"])
async def models_status():
    """Vérifie le statut des modèles chargés et des voix."""
    return {
        "voice_design_loaded": voice_design_model is not None,
        "voice_clone_loaded": voice_clone_model is not None,  # 1.7B-CustomVoice
        "preset_voice_loaded": preset_voice_model is not None,  # 0.6B-CustomVoice
        "clone_1_7b_loaded": clone_model_1_7b is not None,  # 1.7B-Base
        "clone_0_6b_loaded": clone_model_0_6b is not None,  # 0.6B-Base
        "prompts_cached": len(voice_clone_prompts),
        "custom_voices_count": len(custom_voices),
        "custom_voices_loaded_in_memory": sum(1 for v in custom_voices.values() if v["prompt_items"] is not None),
        "device": DEVICE,
        "mps_available": torch.backends.mps.is_available(),
        "cuda_available": torch.cuda.is_available(),
        "models_dir": str(MODELS_DIR),
        "custom_voices_dir": str(CUSTOM_VOICES_DIR),
    }


@app.post("/models/preload", tags=["Informations"])
async def preload_models(
    design: bool = False,
    clone: bool = False,
    preset: bool = True,
    clone_1_7b: bool = False,
    clone_0_6b: bool = False,
):
    """
    Pré-charge les modèles en mémoire.

    Utile pour éviter le temps de chargement au premier appel.
    Par défaut, charge le modèle preset (le plus léger).

    Paramètres :
        design : Charger 1.7B-VoiceDesign
        clone : Charger 1.7B-CustomVoice (pour /preset/instruct)
        preset : Charger 0.6B-CustomVoice (pour /preset)
        clone_1_7b : Charger 1.7B-Base (pour /clone haute qualité)
        clone_0_6b : Charger 0.6B-Base (pour /clone rapide)
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
# BATCH PROCESSING
# ==============================================================================

@app.post("/batch/preset", tags=["Batch Processing"])
async def batch_preset_voice(request: BatchPresetRequest):
    """
    Batch Preset - Génère plusieurs audios avec la même voix.

    Accepte une liste de textes et retourne un fichier ZIP contenant
    tous les fichiers WAV numérotés (001.wav, 002.wav, etc.).

    Maximum : 100 textes par requête.

    Retourne : fichier ZIP
    """
    try:
        # Valider le nombre de textes
        if len(request.texts) > 100:
            raise HTTPException(
                status_code=400,
                detail="Maximum 100 textes par requête"
            )

        # Vérifier que tous les textes sont non vides
        for i, text in enumerate(request.texts):
            if not text or not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Texte {i+1} est vide"
                )

        # Résoudre la langue (support auto)
        first_text = request.texts[0] if request.texts else ""
        language_full = resolve_language(request.language, first_text)

        # Vérifier si c'est une voix native ou custom
        is_native = request.voice in PRESET_VOICES
        is_custom = request.voice in custom_voices

        if not is_native and not is_custom:
            all_voices = list(PRESET_VOICES.keys()) + list(custom_voices.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Voix '{request.voice}' inconnue. Disponibles : {', '.join(all_voices)}"
            )

        # Créer le ZIP en mémoire
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, text in enumerate(request.texts):
                # Résoudre la langue pour chaque texte si auto
                if request.language == "auto":
                    lang = resolve_language("auto", text)
                else:
                    lang = language_full

                # Générer l'audio
                if is_native:
                    model = load_preset_voice_model()
                    wavs, sr = model.generate_custom_voice(
                        text=text,
                        language=lang,
                        speaker=request.voice,
                    )
                else:
                    # Voix personnalisée
                    voice_data = custom_voices[request.voice]
                    meta = voice_data["meta"]
                    prompt_items = get_custom_voice_prompt(request.voice)

                    if prompt_items is None:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Impossible de charger la voix '{request.voice}'"
                        )

                    if meta.get("source") == "design" and isinstance(prompt_items, dict) and prompt_items.get("type") == "design":
                        tts_model = load_voice_design_model()
                        wavs, sr = tts_model.generate_voice_design(
                            text=text,
                            language=lang,
                            instruct=prompt_items["voice_description"],
                        )
                    else:
                        model_size = meta.get("model", "1.7B")
                        tts_model = load_clone_base_model(model_size)
                        wavs, sr = tts_model.generate_voice_clone(
                            text=text,
                            language=lang,
                            voice_clone_prompt=prompt_items,
                        )

                # Sauvegarder dans le ZIP
                audio_buffer = io.BytesIO()
                sf.write(audio_buffer, wavs[0], sr, format="WAV")
                audio_buffer.seek(0)

                filename = f"{i+1:03d}.wav"
                zf.writestr(filename, audio_buffer.getvalue())

        zip_buffer.seek(0)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=batch_preset_{request.voice.lower()}.zip"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch/design", tags=["Batch Processing"])
async def batch_voice_design(request: BatchDesignRequest):
    """
    Batch Voice Design - Génère plusieurs audios avec une voix décrite en texte.

    Accepte une liste de textes et retourne un fichier ZIP contenant
    tous les fichiers WAV numérotés (001.wav, 002.wav, etc.).

    Maximum : 100 textes par requête.

    Retourne : fichier ZIP
    """
    try:
        # Valider le nombre de textes
        if len(request.texts) > 100:
            raise HTTPException(
                status_code=400,
                detail="Maximum 100 textes par requête"
            )

        # Vérifier que tous les textes sont non vides
        for i, text in enumerate(request.texts):
            if not text or not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Texte {i+1} est vide"
                )

        model = load_voice_design_model()

        # Résoudre la langue (support auto)
        first_text = request.texts[0] if request.texts else ""
        language_full = resolve_language(request.language, first_text)

        # Créer le ZIP en mémoire
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, text in enumerate(request.texts):
                # Résoudre la langue pour chaque texte si auto
                if request.language == "auto":
                    lang = resolve_language("auto", text)
                else:
                    lang = language_full

                # Générer l'audio
                wavs, sr = model.generate_voice_design(
                    text=text,
                    language=lang,
                    instruct=request.voice_instruct or "Voix naturelle et claire",
                )

                # Sauvegarder dans le ZIP
                audio_buffer = io.BytesIO()
                sf.write(audio_buffer, wavs[0], sr, format="WAV")
                audio_buffer.seek(0)

                filename = f"{i+1:03d}.wav"
                zf.writestr(filename, audio_buffer.getvalue())

        zip_buffer.seek(0)

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


@app.post("/batch/clone", tags=["Batch Processing"])
async def batch_voice_clone(
    texts: str = Form(..., description="Textes à synthétiser, séparés par des sauts de ligne (\\n)"),
    prompt_id: str = Form(..., description="ID du prompt créé via /clone/prompt (requis)"),
    language: str = Form("fr", description="Langue : fr, en, zh, ja, ko, de, ru, pt, es, it, auto"),
):
    """
    Batch Voice Clone - Génère plusieurs audios avec une voix clonée.

    Nécessite un prompt_id créé via POST /clone/prompt.
    Les textes sont séparés par des sauts de ligne.

    Maximum : 100 textes par requête.

    Retourne : fichier ZIP
    """
    tmp_path = None
    try:
        # Parser les textes (séparés par newline)
        text_list = [t.strip() for t in texts.split("\n") if t.strip()]

        if not text_list:
            raise HTTPException(
                status_code=400,
                detail="Aucun texte valide fourni"
            )

        if len(text_list) > 100:
            raise HTTPException(
                status_code=400,
                detail="Maximum 100 textes par requête"
            )

        # Récupérer le prompt
        prompt_data = get_prompt(prompt_id)
        if not prompt_data:
            raise HTTPException(
                status_code=404,
                detail=f"Prompt '{prompt_id}' non trouvé"
            )

        model_size = prompt_data["model"]
        tts_model = load_clone_base_model(model_size)

        # Résoudre la langue (support auto)
        first_text = text_list[0] if text_list else ""
        language_full = resolve_language(language, first_text)

        # Créer le ZIP en mémoire
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, text in enumerate(text_list):
                # Résoudre la langue pour chaque texte si auto
                if language == "auto":
                    lang = resolve_language("auto", text)
                else:
                    lang = language_full

                # Générer l'audio avec le prompt
                wavs, sr = tts_model.generate_voice_clone(
                    text=text,
                    language=lang,
                    voice_clone_prompt=prompt_data["prompt_items"],
                )

                # Sauvegarder dans le ZIP
                audio_buffer = io.BytesIO()
                sf.write(audio_buffer, wavs[0], sr, format="WAV")
                audio_buffer.seek(0)

                filename = f"{i+1:03d}.wav"
                zf.writestr(filename, audio_buffer.getvalue())

        zip_buffer.seek(0)

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


# ==============================================================================
# TOKENIZER API
# ==============================================================================

@app.post("/tokenizer/encode", tags=["Tokenizer"])
async def tokenizer_encode(request: TokenizeRequest):
    """
    Encode un texte en tokens.

    Utilise le tokenizer de Qwen3-TTS pour convertir du texte en liste de tokens.

    Retourne :
    - text : Le texte original
    - tokens : Liste des IDs de tokens
    - count : Nombre de tokens
    """
    try:
        # Charger n'importe quel modèle pour accéder au tokenizer
        # Le modèle preset est le plus léger
        model = load_preset_voice_model()

        # Accéder au tokenizer via le processor
        tokenizer = None
        if hasattr(model, 'processor') and hasattr(model.processor, 'tokenizer'):
            tokenizer = model.processor.tokenizer
        elif hasattr(model, 'tokenizer'):
            tokenizer = model.tokenizer

        if tokenizer is None:
            raise HTTPException(
                status_code=500,
                detail="Tokenizer non disponible sur ce modèle"
            )

        tokens = tokenizer.encode(request.text)

        return {
            "text": request.text,
            "tokens": tokens,
            "count": len(tokens),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tokenizer/decode", tags=["Tokenizer"])
async def tokenizer_decode(request: DetokenizeRequest):
    """
    Décode une liste de tokens en texte.

    Utilise le tokenizer de Qwen3-TTS pour convertir des tokens en texte.

    Retourne :
    - tokens : La liste de tokens originale
    - text : Le texte décodé
    - count : Nombre de tokens
    """
    try:
        # Charger n'importe quel modèle pour accéder au tokenizer
        model = load_preset_voice_model()

        # Accéder au tokenizer via le processor
        tokenizer = None
        if hasattr(model, 'processor') and hasattr(model.processor, 'tokenizer'):
            tokenizer = model.processor.tokenizer
        elif hasattr(model, 'tokenizer'):
            tokenizer = model.tokenizer

        if tokenizer is None:
            raise HTTPException(
                status_code=500,
                detail="Tokenizer non disponible sur ce modèle"
            )

        text = tokenizer.decode(request.tokens)

        return {
            "tokens": request.tokens,
            "text": text,
            "count": len(request.tokens),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# MCP DOCUMENTATION
# ==============================================================================

def get_mcp_tools_list() -> list:
    """Retourne la liste des outils MCP avec leurs métadonnées."""
    return [
        # Catégorie: Synthèse
        {
            "name": "tts_preset_voice",
            "description": "Génère un audio avec une voix préréglée (native ou personnalisée)",
            "category": "Synthèse",
            "parameters": [
                {"name": "text", "type": "string", "required": True, "description": "Texte à synthétiser"},
                {"name": "voice", "type": "string", "required": False, "description": "Nom de la voix (défaut: Serena)"},
                {"name": "language", "type": "string", "required": False, "description": "Code langue (défaut: fr)"},
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
            "description": "Génère un audio avec une voix décrite en langage naturel",
            "category": "Synthèse",
            "parameters": [
                {"name": "text", "type": "string", "required": True, "description": "Texte à synthétiser"},
                {"name": "voice_description", "type": "string", "required": True, "description": "Description de la voix (ex: 'Voix féminine douce')"},
                {"name": "language", "type": "string", "required": False, "description": "Code langue (défaut: fr)"},
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
            "description": "Génère un audio avec une voix clonée (nécessite un prompt_id)",
            "category": "Synthèse",
            "parameters": [
                {"name": "text", "type": "string", "required": True, "description": "Texte à synthétiser"},
                {"name": "prompt_id", "type": "string", "required": True, "description": "ID du prompt créé via tts_create_clone_prompt"},
                {"name": "language", "type": "string", "required": False, "description": "Code langue (défaut: fr)"},
            ],
            "curl_example": '''curl -X POST "http://localhost:8060/mcp" \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "tts_voice_clone",
      "arguments": {
        "text": "Ceci est ma voix clonée",
        "prompt_id": "abc123-def456-...",
        "language": "fr"
      }
    },
    "id": 1
  }' ''',
            "response_example": None,
        },
        # Catégorie: Gestion
        {
            "name": "tts_get_voices",
            "description": "Liste toutes les voix disponibles (natives + personnalisées)",
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
            "description": "Liste les langues supportées par l'API",
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
        # Catégorie: Avancé
        {
            "name": "tts_create_clone_prompt",
            "description": "Crée un prompt réutilisable pour clonage vocal à partir d'un audio",
            "category": "Avancé",
            "parameters": [
                {"name": "reference_audio_base64", "type": "string", "required": True, "description": "Audio de référence encodé en base64"},
                {"name": "reference_text", "type": "string", "required": True, "description": "Transcription exacte de l'audio"},
                {"name": "model", "type": "string", "required": False, "description": "'1.7B' (qualité) ou '0.6B' (rapide)"},
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
        "reference_text": "Bonjour, je suis la voix de référence.",
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
            "description": "Synthèse avec voix native et contrôle émotionnel/style",
            "category": "Avancé",
            "parameters": [
                {"name": "text", "type": "string", "required": True, "description": "Texte à synthétiser"},
                {"name": "voice", "type": "string", "required": False, "description": "Nom de la voix native"},
                {"name": "instruct", "type": "string", "required": False, "description": "Instruction pour l'émotion/style"},
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
        "instruct": "Ton joyeux et excité",
        "language": "fr"
      }
    },
    "id": 1
  }' ''',
            "response_example": None,
        },
        {
            "name": "tts_get_model_status",
            "description": "Retourne le statut des modèles chargés et des ressources",
            "category": "Avancé",
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
    """Retourne les données de voix formatées pour le template."""
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
    """Retourne le statut des modèles pour le template."""
    return {
        "voice_design_loaded": voice_design_model is not None,
        "voice_clone_loaded": voice_clone_model is not None,
        "preset_voice_loaded": preset_voice_model is not None,
        "clone_1_7b_loaded": clone_model_1_7b is not None,
        "clone_0_6b_loaded": clone_model_0_6b is not None,
        "prompts_cached": len(voice_clone_prompts),
    }


@app.get("/mcp/docs", response_class=HTMLResponse, include_in_schema=False)
async def mcp_docs(request: Request):
    """
    Page de documentation MCP interactive.

    Affiche les instructions d'installation pour Claude Code,
    le statut du serveur et un guide d'intégration avec exemples curl.
    """
    if templates is None:
        return HTMLResponse(
            content="<h1>Erreur</h1><p>Templates non disponibles. Créez le dossier templates/</p>",
            status_code=500
        )

    return templates.TemplateResponse("mcp_docs.html", {
        "request": request,
        "version": API_VERSION,
        "device": DEVICE,
        "tools": get_mcp_tools_list(),
        "voices": get_voices_for_template(),
        "models": get_models_status_for_template(),
    })


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    import uvicorn

    # Charger les voix personnalisées au démarrage
    load_custom_voices()
    custom_count = len(custom_voices)

    langdetect_status = "Oui" if langdetect_available else "Non (pip install langdetect)"

    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║                     TTS-ALEX v{API_VERSION}                      ║
    ║          API locale Qwen3-TTS pour Mac Studio            ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Appareil : {DEVICE:<44} ║
    ║  MPS disponible : {str(torch.backends.mps.is_available()):<38} ║
    ║  CUDA disponible : {str(torch.cuda.is_available()):<37} ║
    ║  Voix natives : 9                                        ║
    ║  Voix personnalisées : {custom_count:<33} ║
    ║  Auto-détection langue : {langdetect_status:<30} ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Routes principales :                                    ║
    ║    POST /preset           - Synthèse avec voix           ║
    ║    POST /preset/instruct  - Voix + émotions (1.7B)       ║
    ║    POST /design           - Voice Design                 ║
    ║    POST /clone            - Voice Clone                  ║
    ║    POST /clone/prompt     - Créer prompt réutilisable    ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Batch & Tokenizer (v1.2) :                              ║
    ║    POST /batch/preset     - Batch preset (ZIP)           ║
    ║    POST /batch/design     - Batch design (ZIP)           ║
    ║    POST /batch/clone      - Batch clone (ZIP)            ║
    ║    POST /tokenizer/encode - Texte → tokens               ║
    ║    POST /tokenizer/decode - Tokens → texte               ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Documentation :                                         ║
    ║    http://localhost:8060/docs      - Swagger UI          ║
    ║    http://localhost:8060/mcp/docs  - MCP Documentation   ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=8060)
