"""
Configuration VoxQwen — constantes, device, mappings, logging, rate limiting.

Aucune dependance sur les autres modules du projet.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import torch
from slowapi import Limiter
from slowapi.util import get_remote_address

# ── Paths ────────────────────────────────────────────────────────────────────

MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

CUSTOM_VOICES_DIR = Path(__file__).parent / "voices" / "custom"
CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)

# ── Version ──────────────────────────────────────────────────────────────────

API_VERSION = "1.4.0"

# ── Device detection ─────────────────────────────────────────────────────────

if torch.backends.mps.is_available():
    DEVICE = "mps"
elif torch.cuda.is_available():
    DEVICE = "cuda:0"
else:
    DEVICE = "cpu"

# ── Timeouts ─────────────────────────────────────────────────────────────────

GENERATION_TIMEOUT = int(os.getenv("VOXQWEN_GENERATION_TIMEOUT", "120"))
GENERATION_QUEUE_TIMEOUT = int(os.getenv("VOXQWEN_QUEUE_TIMEOUT", "5"))
GENERATION_BATCH_TIMEOUT = int(os.getenv("VOXQWEN_BATCH_TIMEOUT", "600"))
GPU_CLEANUP_DELAY = int(os.getenv("VOXQWEN_GPU_CLEANUP_DELAY", "30"))

# ── Rate Limiting ────────────────────────────────────────────────────────────

MCP_RATE_LIMIT = os.getenv("VOXQWEN_RATE_LIMIT", "10/minute")
TTS_RATE_LIMIT = os.getenv("VOXQWEN_TTS_RATE_LIMIT", "10/minute")
BATCH_RATE_LIMIT = os.getenv("VOXQWEN_BATCH_RATE_LIMIT", "2/minute")
CLONE_RATE_LIMIT = os.getenv("VOXQWEN_CLONE_RATE_LIMIT", "5/minute")

limiter = Limiter(key_func=get_remote_address)

# ── Cache prompts ────────────────────────────────────────────────────────────

MAX_CLONE_PROMPTS = int(os.getenv("VOXQWEN_MAX_PROMPTS", "100"))
PROMPT_TTL_HOURS = int(os.getenv("VOXQWEN_PROMPT_TTL_HOURS", "24"))

# ── Detection automatique de langue ─────────────────────────────────────────

langdetect_available = False
try:
    from langdetect import detect as langdetect_detect  # noqa: F401
    langdetect_available = True
except ImportError:
    langdetect_detect = None  # type: ignore[assignment]

# ── Voix prereglees ─────────────────────────────────────────────────────────

PRESET_VOICES = {
    "Vivian": {"gender": "Femme", "native_lang": "Chinois", "description": "Voix féminine jeune, vive et légèrement incisive"},
    "Serena": {"gender": "Femme", "native_lang": "Chinois", "description": "Voix féminine jeune, chaleureuse et douce"},
    "Uncle_Fu": {"gender": "Homme", "native_lang": "Chinois", "description": "Voix masculine mature avec un timbre grave et velouté"},
    "Dylan": {"gender": "Homme", "native_lang": "Chinois (Pékin)", "description": "Voix masculine jeune de Pékin, claire et naturelle"},
    "Eric": {"gender": "Homme", "native_lang": "Chinois (Sichuan)", "description": "Voix masculine enjouée de Chengdu, légèrement rauque"},
    "Ryan": {"gender": "Homme", "native_lang": "Anglais", "description": "Voix masculine dynamique avec un rythme soutenu"},
    "Aiden": {"gender": "Homme", "native_lang": "Anglais", "description": "Voix masculine américaine ensoleillée avec des médiums clairs"},
    "Ono_Anna": {"gender": "Femme", "native_lang": "Japonais", "description": "Voix féminine espiègle avec un timbre léger et agile"},
    "Sohee": {"gender": "Femme", "native_lang": "Coréen", "description": "Voix féminine chaleureuse avec une riche émotion"},
}

# ── Mapping langues ──────────────────────────────────────────────────────────

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

# ── Fonctions utilitaires langue ─────────────────────────────────────────────


def detect_language(text: str) -> str:
    """Detecte automatiquement la langue d'un texte."""
    if not langdetect_available or langdetect_detect is None:
        return "fr"
    try:
        detected = langdetect_detect(text)
        return LANGDETECT_TO_CODE.get(detected, "fr")
    except Exception:
        return "fr"


def resolve_language(language: str, text: str = "") -> str:
    """Resout le code langue en nom complet, avec support pour 'auto'."""
    if language == "auto":
        detected_code = detect_language(text)
        return LANGUAGE_MAP.get(detected_code, "French")
    return LANGUAGE_MAP.get(language, "French")


# ── Logging ──────────────────────────────────────────────────────────────────


def setup_logging():
    """Configure le logging avec rotation fichier + console."""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    json_formatter = logging.Formatter(
        '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    )
    console_formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_dir / "voxqwen.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)

    voxqwen_logger = logging.getLogger("voxqwen")
    voxqwen_logger.setLevel(logging.INFO)
    # Eviter les doublons si setup_logging() est appele plusieurs fois
    if not voxqwen_logger.handlers:
        voxqwen_logger.addHandler(file_handler)
        voxqwen_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return voxqwen_logger
