# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Langue

Toujours répondre en français.

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

# Lancer les démos
python demo_basique_voix_prereglees.py        # Voix préréglées basiques
python demo_avancee_conception_clonage.py     # Conception/clonage avancé
```

## Architecture

### Routes API (main.py)
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
| `/models/status` | GET | Statut des modèles et voix | - |
| `/models/preload` | POST | Pré-charger les modèles | - |
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

**Stockage** : `voices/custom/{name}/` avec `meta.json` + `prompt.pt`

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

### Patterns Clés

**Détection du Device** (à préserver) :
```python
if torch.backends.mps.is_available():
    DEVICE = "mps"
elif torch.cuda.is_available():
    DEVICE = "cuda:0"
else:
    DEVICE = "cpu"
```

**Chargement des Modèles** : Chargement paresseux - les modèles sont chargés au premier appel de route, stockés comme globales au niveau du module. Utilise `torch.float16` (bfloat16 non supporté sur MPS).

**Mapping des Langues** : Utiliser le dict `LANGUAGE_MAP` pour convertir les codes (fr, en, zh, etc.) en noms complets (French, English, Chinese) comme requis par Qwen3-TTS.

**Traitement Audio** : L'audio de référence doit faire 1-30 secondes. Toujours nettoyer les fichiers temporaires avec `os.unlink()` dans les blocs finally. Sortie en WAV via StreamingResponse.

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
- FastAPI + Uvicorn (port 8060)
- PyTorch avec accélération MPS
- qwen-tts (depuis GitHub)
- soundfile, librosa, torchaudio pour le traitement audio
- torchcodec (requis pour les routes /clone et /clone/prompt)
- langdetect (optionnel, pour la détection automatique de langue)
