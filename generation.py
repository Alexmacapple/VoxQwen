"""
Semaphore GPU et gestion de la generation TTS.

Dependances : config.py, models.py
"""

import asyncio
import time
import logging

import torch
from fastapi import HTTPException

from config import GENERATION_TIMEOUT, GENERATION_QUEUE_TIMEOUT, GPU_CLEANUP_DELAY
import models as _models_module

logger = logging.getLogger("voxqwen")

# ── Etat de generation ───────────────────────────────────────────────────────

_generation_lock = asyncio.Semaphore(1)
_generation_active = False
_generation_started_at: float | None = None
_generation_endpoint: str | None = None
_generation_stats = {
    "total": 0,
    "completed": 0,
    "timeouts": 0,
    "rejected_503": 0,
}


# ── Fonction principale ─────────────────────────────────────────────────────


async def with_generation_lock(coro, timeout: int | None = None, endpoint: str = ""):
    """
    Execute une coroutine de generation avec :
    - Semaphore (1 seule generation a la fois)
    - Timeout sur l'acquisition (503 si occupe)
    - Timeout sur la generation (504 si blocage)
    - empty_cache() uniquement apres succes (pas apres timeout)
    """
    global _generation_active, _generation_started_at, _generation_endpoint
    t = timeout or GENERATION_TIMEOUT

    # 1. Acquisition du verrou (max QUEUE_TIMEOUT secondes)
    try:
        await asyncio.wait_for(
            _generation_lock.acquire(),
            timeout=GENERATION_QUEUE_TIMEOUT
        )
    except asyncio.TimeoutError:
        _generation_stats["rejected_503"] += 1
        logger.warning(f"TTS generation REJECTED (503): endpoint={endpoint}")
        raise HTTPException(
            status_code=503,
            detail="Moteur TTS occupe. Reessayez dans quelques secondes."
        )

    # 2. Execution avec timeout
    _generation_stats["total"] += 1
    _generation_active = True
    _generation_started_at = time.time()
    _generation_endpoint = endpoint
    logger.info(f"TTS generation start: endpoint={endpoint}, timeout={t}s")
    try:
        result = await asyncio.wait_for(coro, timeout=t)
        # 3. Nettoyage memoire GPU UNIQUEMENT apres succes
        try:
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception:
            pass
        _generation_stats["completed"] += 1
        elapsed = time.time() - _generation_started_at if _generation_started_at else 0
        logger.info(f"TTS generation end: endpoint={endpoint}, elapsed={elapsed:.1f}s")
        return result
    except asyncio.TimeoutError:
        _generation_stats["timeouts"] += 1
        logger.error(f"TTS generation TIMEOUT: endpoint={endpoint}, timeout={t}s")
        # Deferred GPU cleanup
        if not _models_module._gpu_cleanup_scheduled:
            _models_module._gpu_cleanup_scheduled = True
            loop = asyncio.get_running_loop()
            loop.call_later(GPU_CLEANUP_DELAY, _models_module._deferred_gpu_cleanup, endpoint)
            logger.info(f"GPU cleanup planifie dans {GPU_CLEANUP_DELAY}s")
        raise HTTPException(
            status_code=504,
            detail=f"Generation interrompue (timeout {t}s)."
        )
    finally:
        _generation_active = False
        _generation_started_at = None
        _generation_endpoint = None
        _generation_lock.release()
