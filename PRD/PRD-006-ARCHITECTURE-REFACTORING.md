# PRD-006 — Refactoring architectural

**Version** : v1.0
**Date** : 2026-03-20
**Statut** : A faire
**Priorite** : Moyenne (post-production)
**Effort estime** : 2-3 jours
**Dependance** : PRD-004 et PRD-005 termines

---

## Contexte

`main.py` fait 2876 lignes et contient tout : 31 endpoints, 5 chargeurs de modeles, validation, gestion des voix, cache prompts, batch processing, MCP, monitoring. C'est un monolithe qui fonctionne mais qui devient difficile a maintenir :

- Trouver un bug = chercher dans 2876 lignes
- Modifier une route batch risque de casser une route MCP
- Impossible de tester un module independamment
- Les variables globales (5 modeles, 2 caches, 1 semaphore, 4 stats) sont eparpillees

### Comparaison VoxStudio

VoxStudio a fait ce refactoring (PRD-010) : server.py est passe de ~800 lignes a ~56 lignes d'assemblage + 10 routeurs autonomes. Le meme pattern s'applique a VoxQwen.

### Principe

Ce n'est PAS un rewrite. C'est un **deplacement** de code existant dans des fichiers separes, sans changer le comportement. Chaque route garde exactement la meme signature, les memes validations, les memes reponses. Si un test passait avant, il passe apres.

---

## Architecture cible

```
VoxQwen/
├── main.py                     # Assembleur (~80 lignes) : lifespan, middlewares, mount
├── config.py                   # Configuration (constants, env vars, device detection)
├── models.py                   # Chargement lazy des 5 modeles, GPU cleanup
├── voices.py                   # Voix natives, custom, validation, persistence
├── generation.py               # Semaphore GPU, with_generation_lock, stats
├── routers/
│   ├── __init__.py             # register_all(app)
│   ├── health.py               # GET /, /health, /languages
│   ├── synthesis.py            # POST /preset, /preset/instruct, /design
│   ├── clone.py                # POST /clone, /clone/prompt, GET/DELETE prompts
│   ├── voice_management.py     # GET/POST/DELETE /voices, /voices/custom
│   ├── batch.py                # POST /batch/preset, /batch/design, /batch/clone
│   ├── admin.py                # GET /models/status, /generation/status, POST /models/preload
│   ├── tokenizer.py            # POST /tokenizer/encode, /tokenizer/decode
│   └── mcp_routes.py           # Toutes les routes /mcp/*
├── Documentation/              # (inchange)
├── PRD/                        # (inchange)
├── Test/                       # (inchange, nouveaux tests PRD-005)
├── models/                     # Modeles Qwen3-TTS (gitignored)
├── voices/                     # Voix custom (gitignored)
└── logs/                       # Logs (gitignored, PRD-005)
```

### Repartition du code

| Fichier cible | Lignes actuelles (approx) | Contenu |
|---------------|--------------------------|---------|
| `config.py` | 50-100, 174-210 | Constants, env vars, DEVICE, PRESET_VOICES, LANGUAGE_MAP |
| `models.py` | 78-86, 430-580 | Globals modeles, load_voice_design_model, load_voice_clone_model, etc. |
| `voices.py` | 87-93, 610-800 | custom_voices, voice_clone_prompts, validate_voice_name, load_custom_voices, get_custom_voice_prompt, save_custom_voice, list_available_voices |
| `generation.py` | 95-171 | Semaphore, _generation_lock, with_generation_lock, stats, _deferred_gpu_cleanup (PRD-004) |
| `routers/health.py` | 831-865 | GET /, /health, /languages |
| `routers/synthesis.py` | 866-909, 1516-1670 | /design, /preset, /preset/instruct |
| `routers/clone.py` | 910-1237 | /clone, /clone/prompt, GET/DELETE prompts |
| `routers/voice_management.py` | 1238-1515 | /voices, /voices/custom CRUD, /voices/reload |
| `routers/batch.py` | 1765-2037 | /batch/preset, /batch/design, /batch/clone |
| `routers/admin.py` | 1674-1764 | /models/status, /generation/status, /models/preload |
| `routers/tokenizer.py` | 2038-2126 | /tokenizer/encode, /tokenizer/decode |
| `routers/mcp_routes.py` | 2127-2782 | Toutes les routes /mcp/* |
| `main.py` (nouveau) | ~80 lignes | Lifespan, app creation, register_all, static mount |

---

## Regles de migration

1. **Zero changement d'API** : les routes gardent les memes paths, parametres, reponses
2. **Zero changement de comportement** : si un test passait avant, il passe apres
3. **Imports explicites** : chaque routeur importe ce dont il a besoin depuis config, models, voices, generation
4. **Pas de logique dans main.py** : l'assembleur ne fait qu'assembler
5. **Un commit par fichier extrait** : si ca casse, on sait exactement quoi revert

### Pattern d'import

```python
# routers/synthesis.py
from fastapi import APIRouter, HTTPException, Request, Form
from config import LANGUAGE_MAP, resolve_language, TTS_RATE_LIMIT
from models import load_voice_design_model, load_preset_model
from voices import get_custom_voice_prompt, list_available_voices
from generation import with_generation_lock, limiter

router = APIRouter(tags=["Synthese vocale"])

@router.post("/design")
@limiter.limit(TTS_RATE_LIMIT)
async def voice_design(request: Request, data: DesignRequest):
    # ... code existant inchange
```

```python
# main.py (assembleur)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import API_VERSION, DEVICE
from models import _cleanup_gpu
from voices import load_custom_voices
from routers import register_all

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_custom_voices()
    logger.info(f"VoxQwen v{API_VERSION} demarre sur {DEVICE}")
    yield
    _cleanup_gpu()

app = FastAPI(title="TTS-Alex", version=API_VERSION, lifespan=lifespan)
register_all(app)
```

---

## Schemas Pydantic

Les 15+ classes Pydantic (DesignRequest, CloneRequest, BatchPresetRequest, etc.) sont actuellement dans main.py. Les deplacer dans un fichier `schemas.py` :

```python
# schemas.py
from pydantic import BaseModel, Field, field_validator

class DesignRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    voice_instruct: str = Field(..., min_length=1, max_length=2000)
    language: str = "fr"

class CloneRequest(BaseModel):
    # ...

class BatchPresetRequest(BaseModel):
    # ...

# etc.
```

---

## Ordre d'implementation

L'ordre est dicte par les dependances entre fichiers :

```
Etape 1 : Extraire les feuilles (pas de dependances)
  1a. config.py (constants, env vars, device) ............ 30 min
  1b. schemas.py (Pydantic models) ....................... 30 min
  → Commit + tests

Etape 2 : Extraire les services (dependent de config)
  2a. models.py (chargement modeles) ..................... 45 min
  2b. voices.py (voix custom, prompts, validation) ....... 45 min
  2c. generation.py (semaphore, lock, stats) ............. 30 min
  → Commit + tests

Etape 3 : Extraire les routeurs (dependent des services)
  3a. routers/health.py ................................. 15 min
  3b. routers/synthesis.py .............................. 30 min
  3c. routers/clone.py .................................. 30 min
  3d. routers/voice_management.py ....................... 30 min
  3e. routers/batch.py .................................. 30 min
  3f. routers/admin.py .................................. 15 min
  3g. routers/tokenizer.py .............................. 15 min
  3h. routers/mcp_routes.py ............................. 45 min
  3i. routers/__init__.py (register_all) ................ 15 min
  → Commit + tests apres chaque routeur

Etape 4 : Reduire main.py a l'assembleur
  4a. main.py = lifespan + app + register_all + mount .... 30 min
  → Commit + tests complets
```

**Effort total** : ~7h (2-3 sessions)

---

## Criteres de validation par etape

### Apres etape 1

- [ ] `config.py` importe sans erreur
- [ ] `schemas.py` importe sans erreur
- [ ] `main.py` importe depuis config et schemas
- [ ] Serveur demarre et `GET /` repond

### Apres etape 2

- [ ] `models.py`, `voices.py`, `generation.py` importent sans erreur
- [ ] `POST /preset` fonctionne (charge le modele, genere un WAV)
- [ ] `GET /voices` retourne les voix natives + custom

### Apres etape 3

- [ ] Chaque routeur a au moins 1 test qui passe
- [ ] `GET /docs` (Swagger) affiche toutes les 31 routes
- [ ] Les tags OpenAPI sont corrects (Synthese vocale, Batch, MCP, etc.)

### Apres etape 4

- [ ] `main.py` fait < 100 lignes
- [ ] Tous les tests (MCP + REST) passent
- [ ] VoxStudio fonctionne normalement (parcours complet 6 etapes)
- [ ] `GET /health` retourne 200

---

## Criteres de succes global

- [ ] Zero regression fonctionnelle (memes routes, memes reponses)
- [ ] `main.py` < 100 lignes
- [ ] Chaque fichier < 500 lignes
- [ ] Tous les tests passent
- [ ] Swagger UI affiche les 31 routes avec les bons tags
- [ ] VoxStudio n'a aucune modification a faire (API identique)

---

## Ce que ce PRD ne fait PAS

- Pas de changement d'API (ni routes, ni parametres, ni reponses)
- Pas de nouvelle fonctionnalite
- Pas de migration de base de donnees
- Pas de changement de dependances
- Pas de Docker/containerisation

---

## Historique

| Version | Date | Modification |
|---------|------|-------------|
| v1.0 | 2026-03-20 | Creation (audit production du 2026-03-20) |
