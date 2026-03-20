# PRD-004 — Production Safety

**Version** : v1.0
**Date** : 2026-03-20
**Statut** : A faire
**Priorite** : Critique
**Effort estime** : 1 jour

---

## Contexte

VoxQwen est fonctionnellement complet (31 endpoints, voix persistantes, batch, MCP). La securite des inputs est correcte (validation noms, taille fichiers, path traversal). Mais trois risques critiques empechent un deploiement en production :

1. Le GPU peut fuir en memoire apres un timeout TTS (thread orphelin)
2. Un kill du serveur pendant une generation laisse le GPU dans un etat incertain
3. Les routes TTS couteuses (GPU) n'ont aucun rate limiting

### Perimetre

Ce PRD couvre exclusivement la **surete d'execution** : proteger le GPU, le processus et l'acces aux ressources. Il ne couvre pas le refactoring architectural (PRD-006) ni l'observabilite (PRD-005).

---

## Phase 1 — GPU lifecycle (bloquant)

### 1.1 Cleanup GPU apres timeout

**Probleme** : `with_generation_lock()` (main.py:115-171) ne fait pas `empty_cache()` apres un timeout (ligne 160, commentaire explicite). Le thread orphelin qui executait `model.generate()` continue de consommer la VRAM. Apres N timeouts, la VRAM se remplit progressivement et le Mac Studio ralentit ou freeze.

**Analyse** : Le commentaire "PAS de empty_cache() ici : le thread orphelin utilise encore MPS" est correct — appeler `empty_cache()` pendant que le thread tourne peut causer un segfault. Le vrai probleme est que le thread orphelin n'est jamais annule.

**Solution** : Ajouter un mecanisme de recuperation GPU apres timeout.

```python
# main.py — with_generation_lock(), bloc except asyncio.TimeoutError

except asyncio.TimeoutError:
    _generation_stats["timeouts"] += 1
    logger.error(f"TTS generation TIMEOUT: endpoint={endpoint}, timeout={t}s")

    # Tenter un nettoyage GPU differe (laisser le thread orphelin finir)
    asyncio.get_event_loop().call_later(
        30.0,  # 30s apres le timeout, le thread devrait etre mort
        _deferred_gpu_cleanup,
        endpoint
    )

    raise HTTPException(
        status_code=504,
        detail=f"Generation interrompue (timeout {t}s)."
    )
```

```python
def _deferred_gpu_cleanup(endpoint: str):
    """Nettoie la VRAM GPU 30s apres un timeout (thread orphelin probablement termine)."""
    try:
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
            logger.info(f"GPU cleanup differe OK (post-timeout {endpoint})")
    except Exception as e:
        logger.warning(f"GPU cleanup differe echoue : {e}")
```

**Alternative** : Si le modele Qwen3-TTS supporte l'interruption, utiliser `torch.cuda.synchronize()` / `torch.mps.synchronize()` pour forcer la fin du calcul GPU avant le nettoyage. A tester.

**Fichier** : `main.py` lignes 115-171

**Criteres de validation** :
- [ ] Apres un timeout TTS, `empty_cache()` est appele 30s plus tard
- [ ] Log "GPU cleanup differe OK" visible
- [ ] Un deuxieme appel TTS apres timeout fonctionne normalement
- [ ] Pas de segfault ni de freeze MPS
- [ ] Le stats counter `timeouts` est incremente

---

### 1.2 Monitoring VRAM

**Probleme** : Aucune visibilite sur la consommation VRAM. Si le GPU fuit, on ne le sait qu'au freeze.

**Solution** : Ajouter l'info VRAM dans `GET /generation/status` et `GET /models/status`.

```python
def _get_gpu_memory_info() -> dict:
    """Retourne les infos memoire GPU si disponibles."""
    info = {"device": DEVICE, "available": False}
    try:
        if DEVICE == "mps" and hasattr(torch.mps, "current_allocated_memory"):
            info["allocated_bytes"] = torch.mps.current_allocated_memory()
            info["allocated_mb"] = round(info["allocated_bytes"] / 1024 / 1024, 1)
            info["available"] = True
        elif DEVICE.startswith("cuda"):
            info["allocated_mb"] = round(torch.cuda.memory_allocated() / 1024 / 1024, 1)
            info["total_mb"] = round(torch.cuda.get_device_properties(0).total_mem / 1024 / 1024, 1)
            info["available"] = True
    except Exception:
        pass
    return info
```

Ajouter `"gpu_memory": _get_gpu_memory_info()` dans les reponses de `/generation/status` et `/models/status`.

**Criteres de validation** :
- [ ] `GET /generation/status` retourne `gpu_memory.allocated_mb`
- [ ] La valeur augmente pendant une generation et redescend apres
- [ ] Apres un timeout + cleanup differe, la valeur redescend

---

## Phase 2 — Graceful shutdown (bloquant)

### 2.1 Lifespan FastAPI

**Probleme** : Pas de lifespan context manager. `load_custom_voices()` est appele dans le bloc `__main__` (ligne 2837), pas dans la lifespan FastAPI. Consequence : si l'app est importee (ex: par un test), les voix ne sont pas chargees. Et surtout : aucun cleanup au shutdown.

**Solution** :

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup et shutdown de l'application."""
    # Startup
    load_custom_voices()
    custom_count = len(custom_voices)
    logger.info(f"VoxQwen v{API_VERSION} demarre sur {DEVICE}")
    logger.info(f"Voix natives: 9, voix custom: {custom_count}")
    yield
    # Shutdown
    logger.info("Arret en cours...")
    _cleanup_gpu()
    logger.info("VoxQwen arrete proprement.")

def _cleanup_gpu():
    """Libere les ressources GPU au shutdown."""
    global voice_design_model, voice_clone_model, preset_voice_model
    global clone_model_1_7b, clone_model_0_6b

    # Decharger les modeles
    for name, ref in [
        ("voice_design", voice_design_model),
        ("voice_clone", voice_clone_model),
        ("preset_voice", preset_voice_model),
        ("clone_1_7b", clone_model_1_7b),
        ("clone_0_6b", clone_model_0_6b),
    ]:
        if ref is not None:
            del ref
            logger.info(f"Modele {name} decharge")

    voice_design_model = None
    voice_clone_model = None
    preset_voice_model = None
    clone_model_1_7b = None
    clone_model_0_6b = None

    # Vider le cache GPU
    try:
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        elif torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    import gc
    gc.collect()
    logger.info("GPU cleanup termine")

# Modifier la creation de l'app
app = FastAPI(
    title="TTS-Alex",
    description=f"API Qwen3-TTS v{API_VERSION}",
    version=API_VERSION,
    lifespan=lifespan,
)
```

**Supprimer** le `load_custom_voices()` du bloc `__main__` (ligne 2837) — c'est desormais dans la lifespan.

**Fichier** : `main.py` — creation de l'app + bloc `__main__`

**Criteres de validation** :
- [ ] `Ctrl+C` sur le serveur affiche "Arret en cours..." + "GPU cleanup termine"
- [ ] `kill <pid>` (SIGTERM) declenche le meme cleanup
- [ ] Les modeles sont decharges (verifiable via `GET /models/status` juste avant arret)
- [ ] Apres restart, les voix custom sont toujours chargees (lifespan startup)
- [ ] Les tests existants fonctionnent (voix chargees via lifespan, pas via __main__)

---

### 2.2 Protection generation en cours au shutdown

**Probleme** : Si un shutdown arrive pendant une generation batch (10+ minutes), le processus est tue brutalement. Le fichier WAV en cours d'ecriture peut etre corrompu.

**Solution** : Attendre la fin de la generation en cours (avec timeout) dans la lifespan shutdown.

```python
# Dans lifespan, avant _cleanup_gpu()
if _generation_active:
    logger.warning("Generation en cours, attente max 30s avant arret...")
    for _ in range(30):
        await asyncio.sleep(1)
        if not _generation_active:
            logger.info("Generation terminee, arret propre")
            break
    else:
        logger.warning("Timeout attente generation, arret force")
```

**Criteres de validation** :
- [ ] `kill` pendant une generation courte (< 30s) attend la fin
- [ ] `kill` pendant une generation longue (> 30s) arrete apres 30s
- [ ] Log "Generation terminee, arret propre" ou "arret force" visible

---

## Phase 3 — Rate limiting (bloquant)

### 3.1 Rate limiting sur les routes TTS

**Probleme** : Le rate limiter n'est applique que sur les routes MCP (5 routes, ligne 2130+). Les routes REST principales (`/design`, `/clone`, `/preset`, `/batch/*`) n'ont aucune protection. Un client peut spammer `/batch/design` avec 100 textes en boucle et saturer le GPU indefiniment.

**Etat actuel** :

| Route | Rate limit | GPU |
|-------|-----------|-----|
| `/preset` | Aucun | Oui |
| `/preset/instruct` | Aucun | Oui |
| `/design` | Aucun | Oui |
| `/clone` | Aucun | Oui |
| `/clone/prompt` | Aucun | Oui |
| `/batch/preset` | Aucun | Oui (x N) |
| `/batch/design` | Aucun | Oui (x N) |
| `/batch/clone` | Aucun | Oui (x N) |
| `/voices/custom` | Aucun | Oui |
| `/mcp/preset` | 10/min | Oui |
| `/mcp/design` | 10/min | Oui |
| `/mcp/clone` | 10/min | Oui |

**Solution** : Ajouter `@limiter.limit()` sur toutes les routes GPU.

```python
TTS_RATE_LIMIT = os.getenv("VOXQWEN_TTS_RATE_LIMIT", "10/minute")
BATCH_RATE_LIMIT = os.getenv("VOXQWEN_BATCH_RATE_LIMIT", "2/minute")
CLONE_RATE_LIMIT = os.getenv("VOXQWEN_CLONE_RATE_LIMIT", "5/minute")

@app.post("/preset", tags=["Synthese vocale"])
@limiter.limit(TTS_RATE_LIMIT)
async def preset_voice(request: Request, ...):

@app.post("/preset/instruct", tags=["Synthese vocale"])
@limiter.limit(TTS_RATE_LIMIT)
async def preset_voice_instruct(request: Request, ...):

@app.post("/design", tags=["Synthese vocale"])
@limiter.limit(TTS_RATE_LIMIT)
async def voice_design(request: Request, ...):

@app.post("/clone", tags=["Synthese vocale"])
@limiter.limit(CLONE_RATE_LIMIT)
async def voice_clone(request: Request, ...):

@app.post("/clone/prompt", tags=["Synthese vocale"])
@limiter.limit(CLONE_RATE_LIMIT)
async def create_clone_prompt(request: Request, ...):

@app.post("/batch/preset", tags=["Batch Processing"])
@limiter.limit(BATCH_RATE_LIMIT)
async def batch_generate_preset(request: Request, ...):

@app.post("/batch/design", tags=["Batch Processing"])
@limiter.limit(BATCH_RATE_LIMIT)
async def batch_generate_design(request: Request, ...):

@app.post("/batch/clone", tags=["Batch Processing"])
@limiter.limit(BATCH_RATE_LIMIT)
async def batch_generate_clone(request: Request, ...):

@app.post("/voices/custom", tags=["Synthese vocale"])
@limiter.limit(CLONE_RATE_LIMIT)
async def create_custom_voice(request: Request, ...):
```

**Note** : Les routes existantes qui n'ont pas `request: Request` en parametre devront l'ajouter (slowapi en a besoin pour identifier le client).

**Fichier** : `main.py` — 9 routes a modifier

**Criteres de validation** :
- [ ] `POST /preset` retourne 429 apres 10 appels en 1 minute
- [ ] `POST /batch/design` retourne 429 apres 2 appels en 1 minute
- [ ] Les limites sont configurables via variables d'environnement
- [ ] Les routes MCP gardent leur rate limit existant
- [ ] Le message 429 est clair ("Trop de requetes, reessayez dans X secondes")

---

## Phase 4 — Cache prompts (important)

### 4.1 Limite et TTL sur voice_clone_prompts

**Probleme** : `voice_clone_prompts` (main.py:89) est un dict en memoire qui croit indefiniment. Chaque `POST /clone/prompt` ajoute une entree (~1-5 Mo d'embeddings PyTorch). 1000 prompts = 1-5 Go de RAM consommes.

**Solution** : Limite de taille + TTL.

```python
MAX_CLONE_PROMPTS = int(os.getenv("VOXQWEN_MAX_PROMPTS", "100"))
PROMPT_TTL_HOURS = int(os.getenv("VOXQWEN_PROMPT_TTL_HOURS", "24"))

def _cleanup_expired_prompts():
    """Supprime les prompts expires (> TTL)."""
    now = datetime.now()
    expired = [
        pid for pid, data in voice_clone_prompts.items()
        if (now - data["created_at"]).total_seconds() > PROMPT_TTL_HOURS * 3600
    ]
    for pid in expired:
        del voice_clone_prompts[pid]
    if expired:
        logger.info(f"Prompts expires supprimes: {len(expired)}")

def _enforce_prompt_limit():
    """Supprime les prompts les plus anciens si la limite est depassee."""
    while len(voice_clone_prompts) > MAX_CLONE_PROMPTS:
        oldest = min(voice_clone_prompts, key=lambda k: voice_clone_prompts[k]["created_at"])
        del voice_clone_prompts[oldest]
        logger.info(f"Prompt {oldest} evince (limite {MAX_CLONE_PROMPTS})")
```

Appeler `_cleanup_expired_prompts()` + `_enforce_prompt_limit()` dans `POST /clone/prompt` apres creation du nouveau prompt.

**Criteres de validation** :
- [ ] Un prompt cree il y a > 24h est supprime au prochain appel
- [ ] Au-dela de 100 prompts, le plus ancien est evince
- [ ] Limites configurables via env vars
- [ ] Les prompts non expires restent fonctionnels

---

## Nettoyage complementaire

### 5.1 print() → logger

**Probleme** : 20+ appels `print()` (lignes 447-541, 703, 728, 2842-2874) au lieu du logger. En production, ces messages se melangent au stdout sans timestamp, sans niveau, sans formatage.

**Solution** : Remplacer tous les `print()` par `logger.info()` ou `logger.warning()`.

| Lignes | Contexte | Remplacement |
|--------|----------|-------------|
| 447-463 | Chargement modele Voice Design | `logger.info()` |
| 471-486 | Chargement modele Voice Clone | `logger.info()` |
| 494-508 | Chargement modele Preset Voice | `logger.info()` |
| 528-541 | Chargement modele 1.7B-Base | `logger.info()` |
| 703 | Erreur chargement voix custom | `logger.error()` |
| 728 | Erreur chargement embeddings | `logger.error()` |
| 2842-2874 | Banner demarrage | `logger.info()` |

### 5.2 Exception silencieuse MCP

**Probleme** : Ligne 2516, `except Exception: pass` avale les erreurs d'introspection MCP sans aucun log.

**Solution** : Ajouter un log warning.

```python
except Exception as e:
    logger.warning(f"Erreur introspection MCP tools: {e}")
```

---

## Fichiers modifies

| Fichier | Phase | Modification |
|---------|-------|-------------|
| `main.py` | 1.1 | `_deferred_gpu_cleanup()`, modification `with_generation_lock()` |
| `main.py` | 1.2 | `_get_gpu_memory_info()`, ajout dans 2 endpoints status |
| `main.py` | 2.1 | `lifespan()`, `_cleanup_gpu()`, modification creation app |
| `main.py` | 2.2 | Attente generation en cours dans lifespan shutdown |
| `main.py` | 3.1 | `@limiter.limit()` sur 9 routes TTS, 3 constantes rate limit |
| `main.py` | 4.1 | `_cleanup_expired_prompts()`, `_enforce_prompt_limit()` |
| `main.py` | 5.1 | 20+ print → logger |
| `main.py` | 5.2 | 1 except pass → logger.warning |

---

## Ordre d'implementation

```
Phase 1 — GPU lifecycle (~2h)
  1.1 Cleanup GPU differe apres timeout ........... 1h
  1.2 Monitoring VRAM dans /status ................ 30 min
  5.1 print → logger (prerequis pour le reste) .... 30 min

Phase 2 — Graceful shutdown (~1h)
  2.1 Lifespan FastAPI ............................ 45 min
  2.2 Attente generation au shutdown .............. 15 min

Phase 3 — Rate limiting (~1h)
  3.1 Limiter sur 9 routes TTS .................... 1h

Phase 4 — Cache prompts (~30 min)
  4.1 TTL + limite prompts ....................... 30 min

Nettoyage (~15 min)
  5.2 Exception silencieuse MCP .................. 15 min
```

**Effort total** : ~5h

---

## Criteres de succes global

- [ ] Generation TTS fonctionne apres un timeout (GPU pas fuite)
- [ ] `GET /generation/status` retourne `gpu_memory.allocated_mb`
- [ ] `Ctrl+C` ou `kill` → shutdown propre avec decharge modeles
- [ ] Toutes les routes GPU ont un rate limit
- [ ] Cache prompts limite a 100 max, TTL 24h
- [ ] Zero `print()` dans le code, tout passe par le logger
- [ ] VoxStudio peut toujours appeler toutes les routes normalement

---

## Risques

| Risque | Probabilite | Impact | Mitigation |
|--------|------------|--------|------------|
| `empty_cache()` differe cause segfault MPS | Moyenne | Mac Studio freeze | Tester avec un timeout force, fallback = ne pas appeler si MPS actif |
| Rate limit trop strict bloque VoxStudio | Basse | Generation batch echoue | Limites configurables, VoxStudio = seul client sur localhost |
| Decharge modeles au shutdown cause erreur | Basse | Log d'erreur au shutdown | Try/except autour de chaque del |

---

## Historique

| Version | Date | Modification |
|---------|------|-------------|
| v1.0 | 2026-03-20 | Creation (audit production du 2026-03-20) |
