"""
TTS-Alex - Qwen3-TTS Local API

Assembleur : lifespan, app, MCP, uvicorn.
Zero logique metier — tout est dans config, models, voices, generation, routers.

Usage:
    python main.py
    # API sur http://localhost:8060
"""

import gc
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from fastapi_mcp import FastApiMCP

from config import (
    API_VERSION, DEVICE, STATIC_DIR, TEMPLATES_DIR,
    MCP_RATE_LIMIT, limiter, setup_logging,
)
import models as _models_module
from models import _try_empty_gpu_cache
from voices import load_custom_voices, custom_voices
from generation import _generation_active
from routers import register_all

# ── Logging ──────────────────────────────────────────────────────────────────

logger = setup_logging()

# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Startup et shutdown de l'application."""
    load_custom_voices()
    logger.info(f"VoxQwen v{API_VERSION} | device={DEVICE} | voix_custom={len(custom_voices)}")
    yield
    logger.info("Arret en cours...")
    if _generation_active:
        logger.warning("Generation en cours, attente max 30s...")
        from generation import _generation_active as _ga
        for _ in range(30):
            await asyncio.sleep(1)
            # Re-lire depuis le module car la valeur change
            import generation as _gen_mod
            if not _gen_mod._generation_active:
                logger.info("Generation terminee, arret propre")
                break
        else:
            logger.warning("Timeout attente generation, arret force")
    # Cleanup GPU
    _models_module.voice_design_model = None
    _models_module.voice_clone_model = None
    _models_module.preset_voice_model = None
    _models_module.clone_model_1_7b = None
    _models_module.clone_model_0_6b = None
    _try_empty_gpu_cache()
    gc.collect()
    logger.info("GPU cleanup termine")


# ── Application FastAPI ──────────────────────────────────────────────────────

app = FastAPI(
    title="Qwen3-TTS API",
    description="""
API locale de synthese vocale basee sur **Qwen3-TTS** (Alibaba), optimisee pour Mac Studio (Apple Silicon/MPS).

## Fonctionnalites

- **Voice Design** : Generer une voix a partir d'une description textuelle
- **Voice Clone** : Cloner une voix a partir d'un echantillon audio de reference
- **Preset Voices** : 9 voix prereglees avec controle emotionnel optionnel
- **Voix Personnalisees** : Sauvegarder vos voix creees de facon persistante
- **Batch Processing** : Generer plusieurs audios en une seule requete (ZIP)
- **Auto Language** : Detection automatique de la langue (language="auto")
- **Tokenizer API** : Encoder/decoder du texte en tokens
- **MCP Support** : Integration Model Context Protocol pour Claude Code

## Modeles utilises

| Modele | Usage |
|--------|-------|
| `0.6B-CustomVoice` | Voix prereglees (rapide) |
| `0.6B-Base` | Clonage vocal (rapide) |
| `1.7B-VoiceDesign` | Creation de voix par description |
| `1.7B-CustomVoice` | Voix prereglees + emotions |
| `1.7B-Base` | Clonage vocal (haute qualite) |

## Langues supportees

Francais, Anglais, Chinois, Japonais, Coreen, Allemand, Russe, Portugais, Espagnol, Italien

**+ Detection automatique** : Utilisez `language="auto"` pour une detection automatique.

## Documentation MCP

Pour l'integration avec Claude Code via MCP, consultez [/mcp/docs](/mcp/docs).
""",
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Rate Limiter State
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    """Handler pour les erreurs de rate limiting."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "code": "RATE_LIMIT_EXCEEDED",
            "detail": str(exc.detail),
            "retry_after": 60,
        }
    )


# ── Routeurs ─────────────────────────────────────────────────────────────────

register_all(app)

# ── Static files + Templates ────────────────────────────────────────────────

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None
app.state.templates = templates

# ── MCP — APRES register_all (doit voir toutes les routes) ──────────────────

mcp_server = FastApiMCP(
    app,
    name="VoxQwen",
    description=f"API de synthese vocale Qwen3-TTS v{API_VERSION} pour Mac Studio. Voice Design, Voice Clone, 9 voix prereglees.",
    include_tags=["MCP Tools"],
)
mcp_server.mount()
app.state.mcp_server = mcp_server

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logger.info(f"VoxQwen v{API_VERSION} | device={DEVICE} | docs=http://localhost:8060/docs")
    uvicorn.run(app, host="0.0.0.0", port=8060)
