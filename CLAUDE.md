# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Langue

Toujours répondre en français.

## Dépôt distant

- **GitHub** : `git@github.com:Alexmacapple/VoxQwen.git` (SSH)
- **URL publique** : `https://github.com/Alexmacapple/VoxQwen`

## API

- **URL** : `http://localhost:8060`
- **Swagger UI** : `http://localhost:8060/docs`
- **ReDoc** : `http://localhost:8060/redoc`
- **MCP** : `http://localhost:8060/mcp/docs`

## Aperçu du Projet

TTS-Alex est une API locale de synthèse vocale utilisant les modèles Qwen3-TTS, optimisée pour Mac Studio (Apple Silicon/MPS). Deux fonctionnalités principales :
- **Voice Design** : Générer une voix à partir d'une description textuelle
- **Voice Clone** : Cloner une voix à partir d'un échantillon audio de référence

## Commandes

```bash
# Activer l'environnement
source venv/bin/activate

# Lancer le serveur API
python main.py
# API sur http://localhost:8060, docs sur http://localhost:8060/docs

# Redémarrer le serveur (si modifications dans main.py)
# 1. Trouver le processus
lsof -i :8060
# 2. Tuer le processus (remplacer PID par le numéro affiché)
kill <PID>
# 3. Relancer
python main.py

# Ou en une commande (force kill + relance)
kill $(lsof -t -i :8060) 2>/dev/null; python main.py

# Télécharger les modèles (~18 Go au total)
python models/download_models.py              # Tous les modèles
python models/download_models.py --list       # Lister les disponibles
python models/download_models.py --model 1.7B-VoiceDesign  # Modèle spécifique

```

## Architecture

### Structure du code

```
VoxQwen/
├── main.py              # Assembleur (~162 lignes) : lifespan, app, MCP, uvicorn
├── config.py            # Configuration, constants, device, mappings, logging, rate limiting
├── schemas.py           # 15 classes Pydantic (zero dependance)
├── models.py            # 5 chargeurs de modeles lazy, cleanup GPU
├── voices.py            # Voix natives + custom + prompts volatils, persistence
├── generation.py        # Semaphore GPU, with_generation_lock, stats
├── routers/
│   ├── __init__.py      # register_all(app)
│   ├── health.py        # GET /, /health, /languages
│   ├── synthesis.py     # POST /preset, /preset/instruct, /design
│   ├── clone.py         # POST /clone, /clone/prompt, GET/DELETE prompts
│   ├── voice_management.py  # GET/POST/DELETE /voices, /voices/custom
│   ├── batch.py         # POST /batch/preset, /batch/design, /batch/clone
│   ├── admin.py         # GET /models/status, /generation/status, POST /models/preload
│   ├── tokenizer.py     # POST /tokenizer/encode, /tokenizer/decode
│   └── mcp_routes.py    # 9 routes /mcp/* + helpers documentation
├── Documentation/       # 5 guides techniques
├── PRD/                 # 6 PRD (voix persistantes, MCP, clone, safety, observabilite, refactoring)
├── Test/                # 25 tests REST (pytest) + 11 tests MCP (urllib)
├── models/              # Modeles Qwen3-TTS ~18 Go (gitignored)
├── voices/              # Voix custom (gitignored)
└── logs/                # Logs rotation JSON (gitignored)
```

### Routes API
| Route | Méthode | Description | Modèle |
|-------|---------|-------------|--------|
| `/` | GET | État du serveur | - |
| `/languages` | GET | Liste des 10 langues supportées | - |
| `/voices` | GET | Liste des voix (natives + personnalisées) | - |
| `/voices/custom` | POST | Créer une voix personnalisée persistante | 1.7B-Base / 0.6B-Base |
| `/voices/custom/{name}` | GET | Détails d'une voix personnalisée | - |
| `/voices/custom/{name}` | DELETE | Supprimer une voix personnalisée | - |
| `/preset` | POST | Synthèse avec voix (native ou custom) | Variable |
| `/preset/instruct` | POST | Voix natives + contrôle émotions/styles | 1.7B-CustomVoice |
| `/design` | POST | Voice Design (créer voix par description) | 1.7B-VoiceDesign |
| `/clone` | POST | Voice Clone (cloner depuis audio ou prompt) | 1.7B-Base / 0.6B-Base |
| `/clone/prompt` | POST | Créer un prompt réutilisable pour clonage | 1.7B-Base / 0.6B-Base |
| `/clone/prompts` | GET | Lister les prompts en cache | - |
| `/clone/prompts/{id}` | DELETE | Supprimer un prompt | - |
| `/models/status` | GET | Statut des modeles, GPU memory | - |
| `/models/preload` | POST | Pre-charger les modeles | - |
| `/generation/status` | GET | Generation active, stats, GPU memory | - |
| `/health` | GET | Probe de sante (200/503) | - |
| `/voices/reload` | POST | Recharger les voix custom depuis disque | - |
| `/batch/preset` | POST | Batch preset voice (retourne ZIP) | Variable |
| `/batch/design` | POST | Batch voice design (retourne ZIP) | 1.7B-VoiceDesign |
| `/batch/clone` | POST | Batch voice clone (retourne ZIP) | 1.7B-Base / 0.6B-Base |
| `/tokenizer/encode` | POST | Encoder texte en tokens | - |
| `/tokenizer/decode` | POST | Décoder tokens en texte | - |

### Voix Préréglées (routes `/preset` et `/preset/instruct`)
Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

**Différence entre les deux routes :**
- `/preset` : Rapide (0.6B), sans contrôle émotionnel
- `/preset/instruct` : Plus expressif (1.7B), avec paramètre `instruct` pour contrôler émotions/styles

### Stockage des Modèles
Tous les modèles stockés localement dans `models/` (pas de cache HuggingFace) :
- `0.6B-CustomVoice` - 9 voix préréglées (rapide)
- `0.6B-Base` - Clonage vocal (rapide)
- `1.7B-VoiceDesign` - Conception de voix (génération par description)
- `1.7B-CustomVoice` - Voix préréglées avec contrôle émotionnel
- `1.7B-Base` - Clonage vocal (haute qualité)
- `Tokenizer` - Tokenizer vocal (requis par tous les modèles)

**Note importante** : Les modèles Base supportent `create_voice_clone_prompt()` pour créer des prompts réutilisables, contrairement aux modèles CustomVoice.

### Voix Personnalisées Persistantes

Les voix personnalisées permettent de sauvegarder des voix créées via Voice Clone ou Voice Design pour les réutiliser après redémarrage du serveur.

**Stockage sur disque** : `voices/custom/{name}/`

```
voices/custom/narrateur-dynamique/
├── meta.json    # Métadonnées (nom, description, date, modèle, source)
└── prompt.pt    # Embedding vocal PyTorch (~1.4 Ko = l'"ADN" de la voix)
```

**Fonctionnement interne** :

1. `POST /voices/custom` envoie une description textuelle (source=design) ou un audio (source=clone)
2. Le modèle 1.7B génère un **embedding vocal** (vecteur mathématique représentant la voix)
3. L'embedding est sauvegardé dans `prompt.pt`, les métadonnées dans `meta.json`
4. Au démarrage du serveur, toutes les voix dans `voices/custom/` sont rechargées automatiquement
5. `POST /preset` avec `voice={name}` charge l'embedding et l'utilise pour la synthèse

**Non-déterminisme de Voice Design** : l'embedding sauvegardé est stable, mais le décodeur audio introduit des variations à chaque génération. Le timbre, la hauteur et le genre perçu peuvent varier d'un appel à l'autre avec le même embedding. Pour une cohérence maximale, préférer **Voice Clone** (`/clone`) avec un échantillon audio humain.

Workflow recommandé :
1. `POST /voices/custom` - Créer une voix persistante (clone ou design)
2. `POST /preset` - Utiliser la voix par son nom
3. La voix persiste après redémarrage

Paramètres de `/voices/custom` (source=clone) :
- `name` : Nom unique (3-50 chars, alphanum + tirets) - **REQUIS**
- `source` : "clone" - **REQUIS**
- `reference_audio` : Fichier audio (1-30 sec) - **REQUIS**
- `reference_text` : Transcription exacte de l'audio - **REQUIS**
- `model` : "1.7B" (qualité) ou "0.6B" (rapide) - défaut: 1.7B
- `description` : Description optionnelle (max 200 chars)

Paramètres de `/voices/custom` (source=design) :
- `name` : Nom unique (3-50 chars, alphanum + tirets) - **REQUIS**
- `source` : "design" - **REQUIS**
- `voice_description` : Description textuelle de la voix - **REQUIS**
- `language` : Langue (fr, en, etc.) - défaut: fr
- `description` : Description optionnelle (max 200 chars)

### Prompts de Clonage Vocal (Volatils)

Les prompts permettent de réutiliser une voix clonée pour générer plusieurs phrases sans retraiter l'audio de référence à chaque fois.

**⚠️ IMPORTANT : Les prompts sont stockés en MÉMOIRE uniquement et sont perdus au redémarrage du serveur.**
**Pour une persistance, utilisez plutôt `/voices/custom`.**

Workflow recommandé :
1. `POST /clone/prompt` - Créer un prompt avec `name` optionnel (ex: "voix_yves")
2. `POST /clone` - Générer plusieurs phrases avec `prompt_id`
3. Conserver le fichier audio source pour recréer le prompt si nécessaire

Paramètres de `/clone/prompt` :
- `reference_audio` : Fichier audio (1-30 sec) - **REQUIS**
- `reference_text` : Transcription exacte de l'audio - **REQUIS**
- `model` : "1.7B" (qualité) ou "0.6B" (rapide) - défaut: 1.7B
- `name` : Nom pour identifier le prompt - **OPTIONNEL**
- `x_vector_only` : Si True, retourne uniquement l'embedding sans stocker - défaut: False

### Batch Processing (v1.2)

Permet de générer plusieurs audios en une seule requête. Retourne un fichier ZIP contenant les WAV numérotés (001.wav, 002.wav, etc.).

**Routes disponibles :**
- `POST /batch/preset` - Batch avec voix préréglée ou personnalisée
- `POST /batch/design` - Batch avec Voice Design
- `POST /batch/clone` - Batch avec voix clonée (nécessite un prompt_id)

**Limites :** Maximum 100 textes par requête.

**Exemple avec curl :**
```bash
curl -X POST http://localhost:8060/batch/preset \
  -H "Content-Type: application/json" \
  -d '{"texts": ["Bonjour", "Au revoir"], "voice": "Serena"}' \
  -o batch_output.zip
```

### Détection automatique de langue (v1.2)

Toutes les routes acceptent `language: "auto"` pour détecter automatiquement la langue du texte.

**Dépendance optionnelle :** `pip install langdetect`
- Si `langdetect` n'est pas installé, le fallback est le français.

### API Tokenizer (v1.2)

Permet d'encoder/décoder du texte en tokens via le tokenizer de Qwen3-TTS.

- `POST /tokenizer/encode` : `{"text": "Bonjour"}` → `{"tokens": [...], "count": N}`
- `POST /tokenizer/decode` : `{"tokens": [...]}` → `{"text": "...", "count": N}`

### Patterns cles

**Architecture modulaire** : Le code est decoupe en modules (`config.py`, `models.py`, `voices.py`, `generation.py`) + 8 routeurs. `main.py` est un assembleur de ~162 lignes. Les routeurs importent depuis les modules, pas d'imports circulaires.

**Concurrence GPU** : Un seul appel TTS a la fois via `asyncio.Semaphore(1)` dans `generation.py`. Timeout queue 5s (503), timeout generation 120s (504). Cleanup GPU differe 30s apres timeout.

**Rate limiting** : `@limiter.limit()` sur toutes les routes TTS (10/min preset/design, 5/min clone, 2/min batch). Configurable via env vars `VOXQWEN_TTS_RATE_LIMIT`, `VOXQWEN_BATCH_RATE_LIMIT`, `VOXQWEN_CLONE_RATE_LIMIT`.

**Chargement lazy** : Les modeles sont charges au premier appel (dans `models.py`). `torch.float16` pour les modeles 1.7B, `torch.float32` pour les 0.6B (MPS).

**Lifespan** : Startup = chargement voix custom. Shutdown = attente generation en cours (max 30s) + decharge modeles + `empty_cache()` + `gc.collect()`.

**Logging** : `RotatingFileHandler` JSON dans `logs/voxqwen.log` (10 Mo x 5). Console en format lisible. Logger = `logging.getLogger("voxqwen")`.

**Cache prompts** : TTL 24h, limite 100 prompts max. Eviction automatique dans `store_prompt()`.

**MCP** : `FastApiMCP(app)` cree dans `main.py` APRES `register_all(app)`. Routes MCP accedent a `mcp_server` et `templates` via `app.state`.

**Traitement Audio** : L'audio de reference doit faire 1-30 secondes. Toujours nettoyer les fichiers temporaires avec `os.unlink()` dans les blocs finally. Sortie en WAV via StreamingResponse.

## Langues Supportées

Français, Anglais, Chinois, Japonais, Coréen, Allemand, Russe, Portugais, Espagnol, Italien

**+ Détection automatique** : Utilisez `language: "auto"` (nécessite `pip install langdetect`)

## Documentation API (Swagger/OpenAPI)

L'API génère automatiquement une documentation interactive conforme OpenAPI 3.1 :

| URL | Description |
|-----|-------------|
| `http://localhost:8060/docs` | Swagger UI - Interface interactive pour tester les routes |
| `http://localhost:8060/redoc` | ReDoc - Documentation alternative plus lisible |
| `http://localhost:8060/openapi.json` | Schéma OpenAPI 3.1 (JSON brut) |

## Stack Technique

- Python 3.12
- FastAPI + Uvicorn (port 8060), 8 routeurs, 39 routes
- fastapi-mcp (integration MCP pour Claude Code)
- slowapi (rate limiting sur toutes routes TTS)
- PyTorch avec acceleration MPS (Apple Silicon)
- qwen-tts (depuis GitHub)
- soundfile, librosa, torchaudio pour le traitement audio
- torchcodec (requis pour les routes /clone et /clone/prompt)
- langdetect (optionnel, pour la detection automatique de langue)

## Tests

- **Tests REST** : `python -m pytest Test/test_rest_endpoints.py -v` (25 tests, sans GPU)
- **Tests MCP** : `python Test/test_mcp_integration.py` (serveur live requis, 11 tests)
- **Lock file** : `requirements-lock.txt` (versions exactes pour deploiement)
