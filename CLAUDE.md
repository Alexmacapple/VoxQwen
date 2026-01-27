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
| `/` | GET | Health check | - |
| `/languages` | GET | Liste des 10 langues supportées | - |
| `/voices` | GET | Liste des 9 voix préréglées | - |
| `/preset` | POST | Voix préréglées (rapide, léger) | 0.6B-CustomVoice |
| `/preset/instruct` | POST | Voix préréglées + contrôle émotions/styles | 1.7B-CustomVoice |
| `/design` | POST | Voice Design (créer voix par description) | 1.7B-VoiceDesign |
| `/clone` | POST | Voice Clone (cloner depuis audio ou prompt) | 1.7B-Base / 0.6B-Base |
| `/clone/prompt` | POST | Créer un prompt réutilisable pour clonage | 1.7B-Base / 0.6B-Base |
| `/clone/prompts` | GET | Lister les prompts en cache | - |
| `/clone/prompts/{id}` | DELETE | Supprimer un prompt | - |
| `/models/status` | GET | Statut des modèles chargés | - |
| `/models/preload` | POST | Pré-charger les modèles | - |

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
