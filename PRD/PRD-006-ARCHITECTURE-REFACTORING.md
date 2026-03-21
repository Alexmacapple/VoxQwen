# PRD-006 — Refactoring architectural

**Version** : v2.0
**Date** : 2026-03-20
**Statut** : Terminé
**Priorite** : Moyenne (post-production)
**Effort estime** : 2-3 jours (7h)
**Dependance** : PRD-004 et PRD-005 termines

---

## Contexte

`main.py` fait 2876 lignes et contient tout : 31 endpoints, 5 chargeurs de modeles, validation, gestion des voix, cache prompts, batch processing, MCP, monitoring. C'est un monolithe fonctionnel mais difficile a maintenir.

### Comparaison VoxStudio

VoxStudio a fait ce refactoring (PRD-010) : server.py est passe de ~800 lignes a ~153 lignes d'assemblage + 10 routeurs autonomes. Le meme pattern s'applique a VoxQwen.

### Principe

Ce n'est PAS un rewrite. C'est un **deplacement** de code existant dans des fichiers separes, sans changer le comportement. Chaque route garde exactement la meme signature, les memes validations, les memes reponses.

---

## Graphe de dependances verifie

Analyse complete des 30+ variables globales, 15 classes Pydantic et 31 endpoints. **Zero dependance circulaire detectee.**

```
config.py (FONDATION — aucune dependance)
    │
    ├──► models.py (DEVICE, MODELS_DIR)
    ├──► voices.py (PRESET_VOICES, CUSTOM_VOICES_DIR, DEVICE)
    ├──► generation.py (DEVICE, timeouts)
    └──► schemas.py (aucune dependance, Pydantic pur)
              │
              └──► routers/*.py (importent config, models, voices, generation, schemas)
                        │
                        └──► main.py (assemble tout, cree app, mount MCP)
```

### Risque identifie : couplage MCP

`FastApiMCP(app)` (ligne 2818) necessite que **toutes les routes soient enregistrees AVANT** `mcp_server.mount()`. Le serveur MCP introspects les routes existantes via `include_tags=["MCP Tools"]`.

**Consequence** : `mcp_server` ne peut PAS etre dans un routeur separe. Il doit etre cree dans `main.py` APRES `register_all(app)`.

---

## Architecture cible

```
VoxQwen/
├── main.py                     # Assembleur (~80 lignes) : lifespan, app, MCP, uvicorn
├── config.py                   # Configuration, constants, device, mappings
├── schemas.py                  # 15 classes Pydantic (zero dependance)
├── models.py                   # 5 chargeurs de modeles, cleanup GPU
├── voices.py                   # Voix natives + custom + prompts, persistence
├── generation.py               # Semaphore GPU, with_generation_lock, stats
├── routers/
│   ├── __init__.py             # register_all(app)
│   ├── health.py               # GET /, /health, /languages (~60 lignes)
│   ├── synthesis.py            # POST /preset, /preset/instruct, /design (~300 lignes)
│   ├── clone.py                # POST /clone, /clone/prompt, GET/DELETE prompts (~350 lignes)
│   ├── voice_management.py     # GET/POST/DELETE /voices, /voices/custom (~250 lignes)
│   ├── batch.py                # POST /batch/preset, /batch/design, /batch/clone (~270 lignes)
│   ├── admin.py                # GET /models/status, /generation/status, POST /models/preload (~100 lignes)
│   ├── tokenizer.py            # POST /tokenizer/encode, /tokenizer/decode (~90 lignes)
│   └── mcp_routes.py           # 9 routes /mcp/* + helpers (~650 lignes)
├── Documentation/              # (inchange)
├── PRD/                        # (inchange)
├── Test/                       # (inchange + nouveaux tests PRD-005)
├── models/                     # Modeles Qwen3-TTS 18 Go (gitignored)
├── voices/                     # Voix custom (gitignored)
└── logs/                       # Logs (gitignored, PRD-005)
```

---

## Repartition detaillee du code

### config.py (~150 lignes)

Lignes actuelles : 50-76, 96-98, 175-185, 372-398, plus les nouvelles constantes PRD-004

**Objets transversaux** : 3 objets ne rentrent dans aucun module metier. Voici leur placement :

| Objet | Placement | Justification |
|-------|-----------|---------------|
| `limiter` (slowapi) | `config.py` | C'est une configuration (rate limits). Les routeurs importent `from config import limiter`. `app.state.limiter = limiter` reste dans `main.py` |
| `setup_logging()` | `config.py` | C'est de l'initialisation. Appelee au debut de `main.py` : `logger = setup_logging()` |
| `langdetect_available` + try/import | `config.py` | C'est de la detection de capacite, comme `DEVICE`. Utilisee par `generation.py:detect_language()` via `from config import langdetect_available` |

```python
# config.py — Tout ce qui est constant ou configurable
from pathlib import Path
import os
import torch
import logging
from logging.handlers import RotatingFileHandler

# Paths
MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
CUSTOM_VOICES_DIR = Path(__file__).parent / "voices" / "custom"

# Version
API_VERSION = "1.4.0"

# Device detection
if torch.backends.mps.is_available():
    DEVICE = "mps"
elif torch.cuda.is_available():
    DEVICE = "cuda:0"
else:
    DEVICE = "cpu"

# Timeouts
GENERATION_TIMEOUT = int(os.getenv("VOXQWEN_GENERATION_TIMEOUT", "120"))
GENERATION_QUEUE_TIMEOUT = int(os.getenv("VOXQWEN_QUEUE_TIMEOUT", "5"))
GENERATION_BATCH_TIMEOUT = int(os.getenv("VOXQWEN_BATCH_TIMEOUT", "600"))

# Rate limiting
MCP_RATE_LIMIT = os.getenv("VOXQWEN_RATE_LIMIT", "10/minute")
TTS_RATE_LIMIT = os.getenv("VOXQWEN_TTS_RATE_LIMIT", "10/minute")
BATCH_RATE_LIMIT = os.getenv("VOXQWEN_BATCH_RATE_LIMIT", "2/minute")
CLONE_RATE_LIMIT = os.getenv("VOXQWEN_CLONE_RATE_LIMIT", "5/minute")

# Cache prompts
MAX_CLONE_PROMPTS = int(os.getenv("VOXQWEN_MAX_PROMPTS", "100"))
PROMPT_TTL_HOURS = int(os.getenv("VOXQWEN_PROMPT_TTL_HOURS", "24"))

# Voix prereglees
PRESET_VOICES = { "Vivian": {...}, "Serena": {...}, ... }

# Detection langue (lazy import)
langdetect_available = False
try:
    from langdetect import detect as langdetect_detect
    langdetect_available = True
except ImportError:
    pass

# Rate limiter (partage avec les routeurs)
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)

# Logging
def setup_logging():
    """Configure le logging avec rotation fichier + console."""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    # ... (voir PRD-005 phase 1.1 pour le code complet)
    return logging.getLogger("voxqwen")

# Langues
LANGUAGE_MAP = { "fr": "French", "en": "English", ... }
LANGDETECT_TO_CODE = { "fr": "fr", "en": "en", ... }
```

**Side effects a l'import** : detection device (appel `torch.backends.mps.is_available()`). Acceptable.

### schemas.py (~120 lignes)

Lignes actuelles : 256-371

Toutes les classes Pydantic. **Aucune ne reference de variables globales** — extraction triviale.

```python
# schemas.py
from pydantic import BaseModel, Field, field_validator

class DesignRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    voice_instruct: str = Field(..., min_length=1, max_length=2000)
    language: str = "fr"

class BatchPresetRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=100)
    voice: str = "Serena"
    language: str = "fr"

# ... 13 autres classes (MCPPresetRequest, MCPAudioResponse, etc.)
```

### models.py (~200 lignes)

Lignes actuelles : 79-86, 443-563

5 variables globales modeles + 4 fonctions de chargement + cleanup GPU.

```python
# models.py
import torch
import logging
from config import DEVICE, MODELS_DIR

logger = logging.getLogger("voxqwen")

voice_design_model = None
voice_clone_model = None
preset_voice_model = None
clone_model_1_7b = None
clone_model_0_6b = None

def load_voice_design_model():
    global voice_design_model
    if voice_design_model is not None:
        return voice_design_model
    # ... lazy import qwen_tts + chargement
    from qwen_tts import Qwen3TTSModel
    # ...

def _try_empty_gpu_cache(): ...
def _cleanup_gpu(): ...       # Decharge tous les modeles (shutdown)
```

**Dependance** : config.py (DEVICE, MODELS_DIR)

### voices.py (~250 lignes)

Lignes actuelles : 87-93, 570-828

Voix natives, voix custom, prompts volatils, validation, persistence.

```python
# voices.py
from config import PRESET_VOICES, CUSTOM_VOICES_DIR, DEVICE
from models import _try_empty_gpu_cache

voice_clone_prompts: dict = {}
custom_voices: dict = {}

def validate_voice_name(name: str) -> bool: ...
def load_custom_voices(): ...
def get_custom_voice_prompt(name: str): ...
def save_custom_voice(...): ...
def delete_custom_voice(name: str) -> bool: ...
def store_prompt(...): ...
def delete_prompt(prompt_id: str) -> bool: ...
# ...
```

**Dependances** : config.py, models.py (pour `_try_empty_gpu_cache`)

### generation.py (~100 lignes)

Lignes actuelles : 100-171, 401-436

Semaphore GPU, lock, stats, resolution langue.

```python
# generation.py
import asyncio
from config import DEVICE, GENERATION_TIMEOUT, GENERATION_QUEUE_TIMEOUT, LANGUAGE_MAP
from models import _try_empty_gpu_cache

_generation_lock = asyncio.Semaphore(1)
_generation_active = False
_generation_started_at = None
_generation_endpoint = None
_generation_stats = {"total": 0, "completed": 0, "timeouts": 0, "rejected_503": 0}

async def with_generation_lock(coro, timeout=None, endpoint=""): ...
def resolve_language(language: str, text: str = "") -> str: ...
def detect_language(text: str) -> str: ...
def _deferred_gpu_cleanup(endpoint: str): ...   # PRD-004
def _get_gpu_memory_info() -> dict: ...          # PRD-004
```

**Dependances** : config.py, models.py (pour `_try_empty_gpu_cache`)

### routers/__init__.py

```python
from fastapi import FastAPI

def register_all(app: FastAPI):
    from .health import router as health_router
    from .synthesis import router as synthesis_router
    from .clone import router as clone_router
    from .voice_management import router as voice_mgmt_router
    from .batch import router as batch_router
    from .admin import router as admin_router
    from .tokenizer import router as tokenizer_router
    from .mcp_routes import router as mcp_router

    for router in [
        health_router, synthesis_router, clone_router,
        voice_mgmt_router, batch_router, admin_router,
        tokenizer_router, mcp_router,
    ]:
        app.include_router(router)
```

### main.py (assembleur, ~80 lignes)

```python
# main.py — assembleur, zero logique metier
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi_mcp import FastApiMCP

from config import API_VERSION, DEVICE, STATIC_DIR, TEMPLATES_DIR, MCP_RATE_LIMIT
from models import _cleanup_gpu
from voices import load_custom_voices, custom_voices
from generation import setup_logging

logger = setup_logging()
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_custom_voices()
    logger.info(f"VoxQwen v{API_VERSION} | {DEVICE} | custom={len(custom_voices)}")
    yield
    await _graceful_shutdown()

app = FastAPI(title="TTS-Alex", version=API_VERSION, lifespan=lifespan)
app.state.limiter = limiter

# Exception handler rate limit
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={...})

# Enregistrer les routeurs
from routers import register_all
register_all(app)

# Static files + templates
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)))
templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None

# MCP — APRES register_all (doit voir toutes les routes)
mcp_server = FastApiMCP(app, name="VoxQwen", include_tags=["MCP Tools"])
mcp_server.mount()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8060)
```

---

## Compatibilite tests

Les tests PRD-005 utilisent `from main import app`. Apres refactoring, ce chemin **reste valide** car `main.py` contient toujours `app = FastAPI(...)`. L'import declenche :
1. Import de `config.py` (detection device, creation dossiers)
2. Import de `routers/` (enregistrement des routes)
3. Creation de `app` avec lifespan

C'est exactement ce que les tests attendent. **Aucune modification des tests necessaire.**

Si a l'avenir `main.py` est renomme en `server.py`, mettre a jour `conftest.py` : `from server import app`.

---

## Regles de migration

1. **Zero changement d'API** : memes routes, memes parametres, memes reponses
2. **Zero changement de comportement** : tests existants passent sans modification
3. **Un commit par module extrait** : revert granulaire possible
4. **Pas de logique dans main.py** : l'assembleur ne fait qu'assembler
5. **Imports explicites** : chaque routeur importe depuis config, models, voices, generation

---

## Ordre d'implementation

L'ordre suit les dependances (feuilles d'abord, assembleur en dernier) :

```
Etape 1 — Feuilles (zero dependance entre elles)
  1a. config.py (constants, device, mappings) ........... 30 min
  1b. schemas.py (Pydantic models) ...................... 30 min
  → Commit + verifier serveur demarre

Etape 2 — Services (dependent de config)
  2a. models.py (5 chargeurs + cleanup GPU) ............. 45 min
  2b. voices.py (custom, prompts, validation) ........... 45 min
  2c. generation.py (semaphore, lock, langue) ........... 30 min
  → Commit + verifier serveur demarre + GET /voices repond

Etape 3 — Routeurs (dependent des services)
  3a. routers/health.py (/, /health, /languages) ........ 15 min
  3b. routers/synthesis.py (/preset, /design) ........... 30 min
  3c. routers/clone.py (/clone, /clone/prompt) .......... 30 min
  3d. routers/voice_management.py (/voices) ............. 30 min
  3e. routers/batch.py (/batch/*) ....................... 30 min
  3f. routers/admin.py (/models/status, etc.) ........... 15 min
  3g. routers/tokenizer.py (/tokenizer/*) ............... 15 min
  3h. routers/mcp_routes.py (/mcp/*) .................... 45 min
  3i. routers/__init__.py (register_all) ................ 15 min
  → Commit apres chaque routeur + verifier avec Swagger /docs

Etape 4 — Assembleur final
  4a. main.py = lifespan + app + MCP + uvicorn .......... 30 min
  → Commit + tests complets + verification VoxStudio
```

**Effort total** : ~7h (2-3 sessions)

---

## Points d'attention par etape

### Etape 3h — MCP (le plus delicat)

Les routes MCP (lignes 2129-2810) ont des particularites :
- Elles referent `mcp_server` (variable globale, initialisee dans main.py)
- Les helpers `get_mcp_tools_from_server()` (ligne 2501) et `get_models_status_for_template()` (ligne 2771) accedent aux globales modeles
- Le template `/mcp/docs` (ligne 2783) utilise `templates` (Jinja2)

**Approche** : Passer `mcp_server` et `templates` en parametres via `app.state` :

```python
# main.py
app.state.mcp_server = mcp_server
app.state.templates = templates

# routers/mcp_routes.py
@router.get("/mcp/docs")
async def mcp_docs(request: Request):
    templates = request.app.state.templates
    mcp_server = request.app.state.mcp_server
    # ...
```

### Etape 2a — Models (globals mutables)

Les 5 variables globales modeles sont mutees par `load_*_model()` via `global`. En les deplacant dans `models.py`, les routeurs doivent importer depuis `models` au lieu de les avoir en local :

```python
# routers/synthesis.py
from models import load_voice_design_model, voice_design_model
# Ou mieux : acceder via fonction
model = load_voice_design_model()  # Retourne le modele (lazy load si needed)
```

---

## Criteres de validation par etape

### Apres etape 1
- [ ] `from config import DEVICE, PRESET_VOICES` fonctionne
- [ ] `from schemas import DesignRequest` fonctionne
- [ ] Serveur demarre et `GET /` repond

### Apres etape 2
- [ ] `from models import load_voice_design_model` fonctionne
- [ ] `from voices import load_custom_voices, custom_voices` fonctionne
- [ ] `from generation import with_generation_lock` fonctionne

### Apres etape 3
- [ ] `GET /docs` (Swagger) affiche les 31 routes avec les bons tags
- [ ] Tous les tests existants (MCP) passent
- [ ] Tous les tests PRD-005 (REST) passent

### Apres etape 4
- [ ] `main.py` < 100 lignes
- [ ] `wc -l` de chaque fichier < 500 lignes
- [ ] VoxStudio parcours complet fonctionne (6 etapes)
- [ ] `GET /health` retourne 200

---

## Ce que ce PRD ne fait PAS

- Pas de changement d'API (ni routes, ni parametres, ni reponses)
- Pas de nouvelle fonctionnalite
- Pas de Docker/containerisation
- Pas de changement de dependances
- Pas de renommage de routes

---

## Historique

| Version | Date | Modification |
|---------|------|-------------|
| v1.0 | 2026-03-20 | Creation |
| v2.0 | 2026-03-20 | Audit connus/inconnus : graphe dependances verifie (acyclique), couplage MCP identifie (must be after register_all), side effects import documentes, pattern app.state pour MCP/templates, detail par module avec lignes source |
| v2.1 | 2026-03-20 | Evaluation : placement limiter/setup_logging/langdetect dans config.py, compatibilite tests (from main import app stable), code complet config.py avec les 3 objets orphelins |
