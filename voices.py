"""
Gestion des voix — natives, custom persistantes, prompts volatils.

Dependances : config.py, models.py
"""

import gc
import re
import json
import uuid
import shutil
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import torch

from config import (
    PRESET_VOICES, CUSTOM_VOICES_DIR, DEVICE,
    MAX_CLONE_PROMPTS, PROMPT_TTL_HOURS,
)
from models import _try_empty_gpu_cache

logger = logging.getLogger("voxqwen")

# ── Donnees en memoire ───────────────────────────────────────────────────────

# Cache des prompts de clonage vocal (in-memory, volatile)
voice_clone_prompts: Dict[str, Dict[str, Any]] = {}

# Voix personnalisees persistantes (chargees depuis disque)
custom_voices: Dict[str, Dict[str, Any]] = {}


# ── Prompts storage ─────────────────────────────────────────────────────────


def _cleanup_expired_prompts():
    """Supprime les prompts expires (> TTL)."""
    now = datetime.now()
    cutoff = PROMPT_TTL_HOURS * 3600
    expired = [pid for pid, data in voice_clone_prompts.items()
               if (now - data["created_at"]).total_seconds() > cutoff]
    for pid in expired:
        del voice_clone_prompts[pid]
    if expired:
        gc.collect()
        _try_empty_gpu_cache()
        logger.info(f"{len(expired)} prompt(s) expire(s) supprime(s)")


def _enforce_prompt_limit():
    """Supprime les prompts les plus anciens si la limite est depassee."""
    removed = 0
    while len(voice_clone_prompts) > MAX_CLONE_PROMPTS:
        oldest = min(voice_clone_prompts, key=lambda k: voice_clone_prompts[k]["created_at"])
        del voice_clone_prompts[oldest]
        removed += 1
    if removed:
        gc.collect()
        _try_empty_gpu_cache()
        logger.info(f"{removed} prompt(s) evince(s) (limite {MAX_CLONE_PROMPTS})")


def store_prompt(prompt_items: Any, model: str, name: Optional[str] = None) -> str:
    """Stocke un prompt de clonage vocal et retourne son ID."""
    prompt_id = str(uuid.uuid4())
    voice_clone_prompts[prompt_id] = {
        "prompt_items": prompt_items,
        "model": model,
        "name": name,
        "created_at": datetime.now(),
    }
    _cleanup_expired_prompts()
    _enforce_prompt_limit()
    return prompt_id


def get_prompt(prompt_id: str) -> Optional[Dict[str, Any]]:
    """Recupere un prompt stocke par son ID."""
    return voice_clone_prompts.get(prompt_id)


def delete_prompt(prompt_id: str) -> bool:
    """Supprime un prompt stocke."""
    if prompt_id in voice_clone_prompts:
        del voice_clone_prompts[prompt_id]
        gc.collect()
        _try_empty_gpu_cache()
        return True
    return False


def list_prompts() -> list:
    """Liste tous les prompts stockes."""
    return [
        {
            "prompt_id": pid,
            "name": data.get("name"),
            "model": data["model"],
            "created_at": data["created_at"].isoformat(),
        }
        for pid, data in voice_clone_prompts.items()
    ]


# ── Validation voix ─────────────────────────────────────────────────────────


def validate_voice_name(name: str) -> bool:
    """Valide le nom d'une voix personnalisee."""
    if not name or len(name) < 3 or len(name) > 50:
        return False
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return False
    if name in PRESET_VOICES:
        return False
    return True


def get_native_voice_names() -> set:
    """Retourne les noms des voix natives (reserves)."""
    return set(PRESET_VOICES.keys())


# ── Custom voices (persistantes) ────────────────────────────────────────────


def load_custom_voices():
    """Charge les metadonnees des voix personnalisees depuis le disque."""
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
            logger.error(f"Erreur chargement voix {voice_dir.name}: {e}")


def get_custom_voice_prompt(name: str):
    """Recupere les embeddings d'une voix personnalisee (lazy loading)."""
    if name not in custom_voices:
        return None

    voice_data = custom_voices[name]

    # Lazy loading: charger les embeddings si pas encore en memoire
    if voice_data["prompt_items"] is None:
        prompt_file = CUSTOM_VOICES_DIR / name / "prompt.pt"
        if prompt_file.exists():
            try:
                voice_data["prompt_items"] = torch.load(prompt_file, map_location=DEVICE, weights_only=False)
            except Exception as e:
                logger.error(f"Erreur chargement embeddings {name}: {e}")
                return None

    return voice_data["prompt_items"]


def save_custom_voice(name: str, prompt_items: Any, source: str, model: str,
                      description: str = "", language: str = "fr") -> Dict[str, Any]:
    """Sauvegarde une voix personnalisee sur disque."""
    voice_dir = CUSTOM_VOICES_DIR / name
    voice_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "name": name,
        "source": source,
        "model": model,
        "description": description,
        "language": language,
        "created_at": datetime.now().isoformat(),
        "version": "1.0",
    }

    meta_file = voice_dir / "meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    prompt_file = voice_dir / "prompt.pt"
    tmp_file = voice_dir / "prompt.pt.tmp"
    torch.save(prompt_items, tmp_file)
    tmp_file.rename(prompt_file)

    custom_voices[name] = {
        "meta": meta,
        "prompt_items": prompt_items,
    }

    return meta


def delete_custom_voice(name: str) -> bool:
    """Supprime une voix personnalisee du disque et de la memoire."""
    if name not in custom_voices:
        return False

    voice_dir = CUSTOM_VOICES_DIR / name
    if voice_dir.exists():
        shutil.rmtree(voice_dir)

    del custom_voices[name]
    gc.collect()
    _try_empty_gpu_cache()
    return True


def list_custom_voices() -> list:
    """Liste toutes les voix personnalisees."""
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
