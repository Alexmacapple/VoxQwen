# PRD-004 — Production Safety

**Version** : v2.0
**Date** : 2026-03-20
**Statut** : A faire
**Priorite** : Critique
**Effort estime** : 5-6 heures

---

## Contexte

VoxQwen est fonctionnellement complet (31 endpoints, voix persistantes, batch, MCP). La securite des inputs est correcte (validation noms, taille fichiers). Mais trois risques critiques empechent un deploiement en production :

1. Le GPU peut fuir en memoire apres un timeout TTS (thread orphelin)
2. Un kill du serveur pendant une generation laisse le GPU dans un etat incertain
3. Les routes TTS couteuses (GPU) n'ont aucun rate limiting

### Perimetre

Ce PRD couvre exclusivement la **surete d'execution** : proteger le GPU, le processus et l'acces aux ressources. Il ne couvre pas le refactoring architectural (PRD-006) ni l'observabilite (PRD-005).

---

## Phase 1 — GPU lifecycle (bloquant, ~2h30)

### 1.1 Remplacement print() par logger (prerequis)

**Probleme** : 20+ appels `print()` (lignes 447-541, 703, 728, 2842-2874) au lieu du logger. En production, ces messages se melangent au stdout sans timestamp, sans niveau, sans formatage. Ce nettoyage est prerequis pour que les logs des phases suivantes soient coherents.

**Solution** : Remplacer tous les `print()` par `logger.info()` ou `logger.error()`.

| Lignes | Contexte | Remplacement |
|--------|----------|-------------|
| 447-450 | "Chargement du modele Voice Design..." | `logger.info("Chargement Voice Design...")` |
| 463 | "Modele Voice Design charge sur {DEVICE}" | `logger.info(f"Voice Design charge ({DEVICE})")` |
| 471-474 | "Chargement du modele Voice Clone..." | `logger.info("Chargement Voice Clone...")` |
| 486 | "Modele Voice Clone charge sur {DEVICE}" | `logger.info(f"Voice Clone charge ({DEVICE})")` |
| 494-497 | "Chargement du modele Preset Voice..." | `logger.info("Chargement Preset Voice...")` |
| 508 | "Modele Preset Voice charge sur {DEVICE}" | `logger.info(f"Preset Voice charge ({DEVICE})")` |
| 528-531 | "Chargement du modele 1.7B-Base..." | `logger.info("Chargement 1.7B-Base...")` |
| 541 | "Modele 1.7B-Base charge sur {DEVICE}" | `logger.info(f"1.7B-Base charge ({DEVICE})")` |
| 547-549, 558 | idem pour 0.6B-Base | idem |
| 703 | "Erreur chargement voix {name}" | `logger.error(f"Erreur chargement voix {name}: {e}")` |
| 728 | "Erreur chargement embeddings {name}" | `logger.error(f"Erreur chargement embeddings {name}: {e}")` |
| 2842-2874 | Banner demarrage | `logger.info(f"VoxQwen v{API_VERSION} sur {DEVICE}")` |

Supprimer les bannieres decoratives (`═══`, `║`). Un simple `logger.info()` avec les infos essentielles suffit.

**Aussi** : ligne 2516, `except Exception: pass` (introspection MCP tools) → ajouter `logger.warning(f"Erreur introspection MCP: {e}")`.

**Criteres de validation** :
- [ ] Zero `print()` dans main.py (grep confirme)
- [ ] Chaque chargement de modele genere un log INFO avec duree
- [ ] Les erreurs de chargement sont loggees en ERROR

---

### 1.2 Cleanup GPU differe apres timeout

**Probleme** : `with_generation_lock()` (main.py:115-171) ne fait pas `empty_cache()` apres un timeout (ligne 160, commentaire explicite). Le thread orphelin qui executait `model.generate()` dans `asyncio.to_thread()` continue de consommer la VRAM. Apres N timeouts, la VRAM se remplit progressivement.

**Analyse du risque** :
- Apres `asyncio.wait_for()` timeout, la coroutine est annulee mais le thread sous-jacent (`to_thread`) **continue jusqu'a completion** — c'est une limitation connue de Python asyncio
- Le thread finira par se terminer (model.generate retourne tot ou tard), mais en attendant il tient la VRAM
- Appeler `empty_cache()` pendant que le thread tourne peut causer un segfault MPS
- Le cleanup differe (attendre que le thread ait probablement fini) est la meilleure approche

**Solution** :

```python
# Nouvelle fonction
def _deferred_gpu_cleanup(endpoint: str):
    """Nettoie la VRAM GPU apres un timeout (thread orphelin probablement termine)."""
    try:
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        elif torch.cuda.is_available():
            torch.cuda.empty_cache()
        import gc
        gc.collect()
        logger.info(f"GPU cleanup differe OK (post-timeout {endpoint})")
    except Exception as e:
        logger.warning(f"GPU cleanup differe echoue: {e}")
```

```python
# Dans with_generation_lock(), bloc except asyncio.TimeoutError (ligne 159)
except asyncio.TimeoutError:
    _generation_stats["timeouts"] += 1
    logger.error(f"TTS generation TIMEOUT: endpoint={endpoint}, timeout={t}s")

    # Cleanup differe : 30s apres le timeout, le thread devrait etre termine
    loop = asyncio.get_running_loop()
    loop.call_later(30.0, _deferred_gpu_cleanup, endpoint)

    raise HTTPException(
        status_code=504,
        detail=f"Generation interrompue (timeout {t}s)."
    )
```

**Note technique** : `loop.call_later()` avec une fonction synchrone fonctionne car la fonction s'execute dans le thread de l'event loop (pas dans un thread separe). `torch.mps.empty_cache()` est une operation rapide qui ne bloque pas significativement.

**Risque residuel** : Si le thread orphelin n'a pas termine apres 30s (generation tres longue sur un gros texte), le `empty_cache()` pourrait confliter. Mitigation : le try/except autour de `empty_cache()` protege contre le crash. Au pire, le cache n'est pas vide — il le sera au prochain appel reussi (ligne 152).

**Criteres de validation** :
- [ ] Apres un timeout TTS force (texte de 10000 mots, timeout 5s), le log "GPU cleanup differe OK" apparait ~30s plus tard
- [ ] Un deuxieme appel TTS apres timeout fonctionne normalement
- [ ] Pas de segfault ni de freeze MPS
- [ ] Le compteur `_generation_stats["timeouts"]` est incremente

---

### 1.3 Cleanup GPU a la suppression de prompts et voix

**Probleme decouvert lors de l'audit** : `delete_prompt()` (ligne 618) et `delete_custom_voice()` (ligne 784) font `del` sur les references Python mais ne liberent pas la memoire GPU. Les tensors PyTorch restes en VRAM.

```python
# Actuel (ligne 618-621)
def delete_prompt(prompt_id: str) -> bool:
    if prompt_id in voice_clone_prompts:
        del voice_clone_prompts[prompt_id]  # Libere la ref Python, PAS la VRAM
        return True
    return False
```

**Solution** : Ajouter `gc.collect()` + `empty_cache()` apres suppression.

```python
import gc

def delete_prompt(prompt_id: str) -> bool:
    if prompt_id in voice_clone_prompts:
        del voice_clone_prompts[prompt_id]
        gc.collect()
        _try_empty_gpu_cache()
        return True
    return False

def delete_custom_voice(name: str) -> bool:
    # ... code existant de suppression fichiers ...
    if name in custom_voices:
        del custom_voices[name]
        gc.collect()
        _try_empty_gpu_cache()
        return True
    return False

def _try_empty_gpu_cache():
    """Tente de vider le cache GPU (safe, ignore les erreurs)."""
    try:
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        elif torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
```

**Criteres de validation** :
- [ ] Creer un prompt, le supprimer, verifier que la VRAM redescend (via /generation/status)
- [ ] Creer une voix custom, la supprimer, verifier que la VRAM redescend
- [ ] Pas d'erreur ni de crash lors de la suppression

---

### 1.4 Monitoring VRAM dans les endpoints status

**Probleme** : Aucune visibilite sur la consommation VRAM. Si le GPU fuit, on ne le sait qu'au freeze.

**Solution** : Ajouter les infos GPU dans `GET /generation/status` et `GET /models/status`.

**Attention API PyTorch MPS** : `torch.mps.current_allocated_memory()` existe depuis PyTorch 2.1 mais peut ne pas etre disponible sur toutes les versions. Il faut aussi `torch.mps.driver_allocated_memory()` pour la memoire totale allouee par le driver. Verifier la disponibilite avec `hasattr()`.

```python
def _get_gpu_memory_info() -> dict:
    """Retourne les infos memoire GPU si disponibles."""
    info = {"device": DEVICE, "available": False}
    try:
        if DEVICE == "mps":
            if hasattr(torch.mps, "current_allocated_memory"):
                info["allocated_mb"] = round(
                    torch.mps.current_allocated_memory() / 1024 / 1024, 1
                )
                info["available"] = True
            if hasattr(torch.mps, "driver_allocated_memory"):
                info["driver_allocated_mb"] = round(
                    torch.mps.driver_allocated_memory() / 1024 / 1024, 1
                )
        elif DEVICE.startswith("cuda"):
            info["allocated_mb"] = round(
                torch.cuda.memory_allocated() / 1024 / 1024, 1
            )
            info["reserved_mb"] = round(
                torch.cuda.memory_reserved() / 1024 / 1024, 1
            )
            info["available"] = True
    except Exception:
        pass
    return info
```

Ajouter `"gpu_memory": _get_gpu_memory_info()` dans les reponses de `/generation/status` (ligne 1694) et `/models/status` (ligne 1674).

**Criteres de validation** :
- [ ] `GET /generation/status` retourne `gpu_memory.allocated_mb` (si API dispo)
- [ ] La valeur augmente pendant une generation et redescend apres
- [ ] Si l'API MPS n'est pas disponible, `gpu_memory.available` = false (pas de crash)

---

## Phase 2 — Graceful shutdown (bloquant, ~1h)

### 2.1 Lifespan FastAPI

**Probleme** : Pas de lifespan context manager. `load_custom_voices()` est appele dans le bloc `__main__` (ligne 2837), pas dans la lifespan FastAPI. Aucun cleanup au shutdown.

**Etat actuel de la creation de l'app** (ligne 187-227) :
```python
app = FastAPI(
    title="Qwen3-TTS API",
    description="...",
    version=API_VERSION,
)
```
Pas de parametre `lifespan=`.

**Side effects au niveau module** (executes a l'import) :
- `OUTPUTS_DIR.mkdir(exist_ok=True)` (ligne 52)
- `CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)` (ligne 68)
- `app = FastAPI(...)` (ligne 187)
- `app.state.limiter = limiter` (ligne 230)
- Mount static files si le dossier existe (ligne 246)
- Templates Jinja2 si le dossier existe (ligne 250)
- Exception handler rate limit (ligne 232)

Ces side effects sont **acceptables** et n'empechent pas l'ajout d'une lifespan.

**Solution** :

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup et shutdown de l'application."""
    # Startup
    load_custom_voices()
    logger.info(
        f"VoxQwen v{API_VERSION} demarre | device={DEVICE} | "
        f"voix_natives=9 | voix_custom={len(custom_voices)}"
    )
    yield
    # Shutdown
    logger.info("Arret en cours...")
    await _graceful_shutdown()
    logger.info("VoxQwen arrete proprement.")


async def _graceful_shutdown():
    """Attend la generation en cours puis libere les ressources GPU."""
    # 1. Attendre la generation en cours (max 30s)
    if _generation_active:
        logger.warning("Generation en cours, attente max 30s...")
        for _ in range(30):
            await asyncio.sleep(1)
            if not _generation_active:
                logger.info("Generation terminee, arret propre")
                break
        else:
            logger.warning("Timeout attente generation, arret force")

    # 2. Decharger les modeles
    global voice_design_model, voice_clone_model, preset_voice_model
    global clone_model_1_7b, clone_model_0_6b

    for name, model_ref in [
        ("voice_design", voice_design_model),
        ("voice_clone", voice_clone_model),
        ("preset_voice", preset_voice_model),
        ("clone_1_7b", clone_model_1_7b),
        ("clone_0_6b", clone_model_0_6b),
    ]:
        if model_ref is not None:
            logger.info(f"Decharge modele {name}")

    voice_design_model = None
    voice_clone_model = None
    preset_voice_model = None
    clone_model_1_7b = None
    clone_model_0_6b = None

    # 3. Vider le cache GPU
    _try_empty_gpu_cache()
    import gc
    gc.collect()
    logger.info("GPU cleanup termine")
```

**Modifier la creation de l'app** (ligne 187) :

```python
app = FastAPI(
    title="Qwen3-TTS API",
    description="...",
    version=API_VERSION,
    lifespan=lifespan,
)
```

**Supprimer** `load_custom_voices()` du bloc `__main__` (ligne 2837) — c'est desormais dans la lifespan.

**Note sur _generation_active** : L'audit a identifie une potentielle race condition sur ce booleen. En pratique, le risque est quasi nul car le semaphore `_generation_lock` serialise l'acces — une seule generation peut etre active a la fois. `_generation_active` est lu et ecrit exclusivement dans `with_generation_lock()`, qui est protege par le semaphore. Pas de correction necessaire.

**Criteres de validation** :
- [ ] `Ctrl+C` affiche "Arret en cours..." + "GPU cleanup termine"
- [ ] `kill <pid>` (SIGTERM) declenche le meme cleanup (uvicorn propage le signal)
- [ ] Apres restart, les voix custom sont chargees (lifespan startup)
- [ ] Le bloc `__main__` ne contient plus `load_custom_voices()`

---

## Phase 3 — Rate limiting (bloquant, ~1h30)

### 3.1 Rate limiting sur les routes TTS

**Probleme** : Le rate limiter n'est applique que sur les 5 routes MCP (lignes 2130, 2219, 2262, 2322, 2398). Les 9 routes REST GPU n'ont aucune protection.

**Etat actuel verifie** :

| Route | Ligne | Rate limit | `Request` param |
|-------|-------|-----------|-----------------|
| `POST /design` | 866 | Aucun | **Non** |
| `POST /clone` | 910 | Aucun | **Non** |
| `POST /clone/prompt` | 1052 | Aucun | **Non** |
| `POST /preset` | 1516 | Aucun | **Non** |
| `POST /preset/instruct` | 1604 | Aucun | **Non** |
| `POST /batch/preset` | 1765 | Aucun | **Non** |
| `POST /batch/design` | 1881 | Aucun | **Non** |
| `POST /batch/clone` | 1950 | Aucun | **Non** |
| `POST /voices/custom` | 1266 | Aucun | **Non** |

**Toutes ces routes** n'ont pas le parametre `Request` requis par slowapi. Il faut l'ajouter en premier parametre de chaque fonction.

**Solution** :

Nouvelles constantes (apres ligne 60) :

```python
TTS_RATE_LIMIT = os.getenv("VOXQWEN_TTS_RATE_LIMIT", "10/minute")
BATCH_RATE_LIMIT = os.getenv("VOXQWEN_BATCH_RATE_LIMIT", "2/minute")
CLONE_RATE_LIMIT = os.getenv("VOXQWEN_CLONE_RATE_LIMIT", "5/minute")
```

Pour chaque route, ajouter `request: Request` en premier parametre et `@limiter.limit()` :

```python
# Exemple pour /design (ligne 866)
@app.post("/design", tags=["Synthese vocale"])
@limiter.limit(TTS_RATE_LIMIT)
async def voice_design(request: Request, data: DesignRequest):
    # ... code inchange

# Exemple pour /preset (ligne 1516) — attention, cette route utilise Form()
@app.post("/preset", tags=["Synthese vocale"])
@limiter.limit(TTS_RATE_LIMIT)
async def preset_voice(
    request: Request,
    text: str = Form(...),
    voice: str = Form("Serena"),
    language: str = Form("fr"),
):
    # ... code inchange
```

**Note CORS** : VoxQwen n'a pas de `CORSMiddleware`. slowapi utilise `get_remote_address` qui lit l'IP client. En usage local (VoxStudio sur localhost), tous les appels viennent de `127.0.0.1` → le rate limit s'applique globalement, pas par utilisateur. C'est acceptable pour un usage solo/equipe restreinte. Si multi-utilisateurs derriere un proxy, il faudra ajouter un `key_func` custom qui lit `X-Forwarded-For`.

**Criteres de validation** :
- [ ] `POST /preset` retourne 429 apres 10 appels rapides
- [ ] `POST /batch/design` retourne 429 apres 2 appels rapides
- [ ] Le message 429 est du JSON : `{"error": "Rate limit exceeded", "code": "RATE_LIMIT_EXCEEDED", ...}`
- [ ] Les limites sont configurables via `VOXQWEN_TTS_RATE_LIMIT`, `VOXQWEN_BATCH_RATE_LIMIT`, `VOXQWEN_CLONE_RATE_LIMIT`
- [ ] VoxStudio peut toujours appeler les routes normalement (< 10/min en usage normal)

---

## Phase 4 — Cache prompts (important, ~30 min)

### 4.1 Limite et TTL sur voice_clone_prompts

**Probleme** : `voice_clone_prompts` (main.py:89) est un dict en memoire qui croit indefiniment. Chaque `POST /clone/prompt` ajoute une entree contenant des tensors PyTorch (embeddings vocaux, taille variable). Aucune limite, aucun TTL.

**Format actuel du created_at** (verifie) : `datetime.now()` (objet datetime Python, pas ISO string). Incoherent avec les voix custom qui utilisent `.isoformat()`. A harmoniser.

**Solution** :

```python
MAX_CLONE_PROMPTS = int(os.getenv("VOXQWEN_MAX_PROMPTS", "100"))
PROMPT_TTL_HOURS = int(os.getenv("VOXQWEN_PROMPT_TTL_HOURS", "24"))


def _cleanup_expired_prompts():
    """Supprime les prompts expires (> TTL)."""
    now = datetime.now()
    cutoff = PROMPT_TTL_HOURS * 3600
    expired = [
        pid for pid, data in voice_clone_prompts.items()
        if (now - data["created_at"]).total_seconds() > cutoff
    ]
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
        oldest = min(
            voice_clone_prompts,
            key=lambda k: voice_clone_prompts[k]["created_at"]
        )
        del voice_clone_prompts[oldest]
        removed += 1
    if removed:
        gc.collect()
        _try_empty_gpu_cache()
        logger.info(f"{removed} prompt(s) evince(s) (limite {MAX_CLONE_PROMPTS})")
```

Appeler `_cleanup_expired_prompts()` + `_enforce_prompt_limit()` dans la fonction `store_prompt()` (ligne 570) apres l'ajout du nouveau prompt.

**Criteres de validation** :
- [ ] Un prompt cree il y a > 24h est supprime au prochain `store_prompt()`
- [ ] Au-dela de 100 prompts, le plus ancien est evince
- [ ] `gc.collect()` + `empty_cache()` appeles apres eviction
- [ ] Limites configurables via env vars

---

## Fichiers modifies

Tous dans `main.py` :

| Phase | Lignes | Modification |
|-------|--------|-------------|
| 1.1 | 447-541, 703, 728, 2516, 2842-2874 | print → logger, except pass → logger.warning |
| 1.2 | 159-166 | Ajout `_deferred_gpu_cleanup()` + `loop.call_later(30.0)` |
| 1.3 | 618-621, 784-799 | Ajout `gc.collect()` + `_try_empty_gpu_cache()` apres suppression |
| 1.4 | 1674-1708 | Ajout `_get_gpu_memory_info()` dans 2 endpoints status |
| 2.1 | 187-227, 2833-2877 | Lifespan + `_graceful_shutdown()` + suppression `load_custom_voices()` de `__main__` |
| 3.1 | 60, 866-1951 | 3 constantes rate limit + `@limiter.limit()` + `request: Request` sur 9 routes |
| 4.1 | 570-592, 89 | `_cleanup_expired_prompts()` + `_enforce_prompt_limit()` + 2 constantes |

---

## Ordre d'implementation

```
Phase 1 — GPU lifecycle (~2h30)
  1.1 print → logger ........................... 30 min
  1.2 Cleanup GPU differe apres timeout ........ 45 min
  1.3 Cleanup GPU a la suppression ............. 30 min
  1.4 Monitoring VRAM dans /status ............. 30 min

Phase 2 — Graceful shutdown (~1h)
  2.1 Lifespan + graceful shutdown ............. 1h

Phase 3 — Rate limiting (~1h30)
  3.1 @limiter sur 9 routes + Request param .... 1h30

Phase 4 — Cache prompts (~30 min)
  4.1 TTL + limite + eviction .................. 30 min
```

**Effort total** : ~5h30

---

## Criteres de succes global

- [ ] Zero `print()` dans main.py
- [ ] Apres un timeout TTS, le GPU est nettoye (differe 30s)
- [ ] Suppression de prompt/voix libere la VRAM
- [ ] `GET /generation/status` retourne `gpu_memory.allocated_mb`
- [ ] `Ctrl+C` ou `kill` → shutdown propre avec decharge modeles
- [ ] Attente generation en cours (max 30s) avant arret
- [ ] Toutes les routes GPU ont un rate limit configurable
- [ ] Cache prompts limite a 100 max, TTL 24h
- [ ] VoxStudio peut toujours appeler toutes les routes normalement

---

## Risques et mitigations

| Risque | Probabilite | Impact | Mitigation |
|--------|------------|--------|------------|
| `empty_cache()` differe cause segfault MPS | Basse | Crash serveur | try/except protege, log warning, pas de crash |
| `torch.mps.current_allocated_memory()` absente | Moyenne | Monitoring inactif | `hasattr()` check, `gpu_memory.available=false` |
| Rate limit trop strict bloque VoxStudio | Basse | Generation echoue | Limites configurables via env, 10/min par defaut largement suffisant |
| Thread orphelin ne se termine jamais | Tres basse | VRAM bloquee | Le cleanup differe nettoie meme si c'est partiel |
| Race condition `_generation_active` | Quasi nulle | Faux statut | Serialise par semaphore, une seule generation possible |

---

## Historique

| Version | Date | Modification |
|---------|------|-------------|
| v1.0 | 2026-03-20 | Creation |
| v2.0 | 2026-03-20 | Audit connus/inconnus : ajout cleanup suppression voix/prompts (1.3), correction API MPS (`hasattr`), verification `Request` param manquant sur 9 routes, note CORS/rate limit, note race condition `_generation_active`, harmonisation created_at |
