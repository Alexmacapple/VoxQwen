# VoxQwen - Qwen3-TTS Local API

API locale de synthèse vocale basée sur Qwen3-TTS (Alibaba), optimisée pour Mac Studio / Apple Silicon. Voice Design, Voice Clone, 9 voix préréglées, batch processing, détection auto de langue. FastAPI + PyTorch MPS. Génération audio haute qualité 100% local, sans cloud.

## Fonctionnalités

| Route | Fonction | Modèle |
|-------|----------|--------|
| `GET /` | Health check | - |
| `GET /languages` | Liste des 10 langues supportées | - |
| `GET /voices` | Liste des voix (natives + personnalisées) | - |
| `POST /voices/custom` | Créer une voix personnalisée persistante | 1.7B-Base / 0.6B-Base |
| `GET /voices/custom/{name}` | Détails d'une voix personnalisée | - |
| `DELETE /voices/custom/{name}` | Supprimer une voix personnalisée | - |
| `POST /preset` | Voix préréglées (rapide) | 0.6B-CustomVoice |
| `POST /preset/instruct` | Voix préréglées + contrôle émotions/styles | 1.7B-CustomVoice |
| `POST /design` | Voice Design (création de voix par description) | 1.7B-VoiceDesign |
| `POST /clone` | Voice Clone (clonage depuis audio ou prompt) | 1.7B-Base / 0.6B-Base |
| `POST /clone/prompt` | Créer un prompt réutilisable pour clonage | 1.7B-Base / 0.6B-Base |
| `GET /clone/prompts` | Lister les prompts en cache | - |
| `DELETE /clone/prompts/{id}` | Supprimer un prompt | - |
| `POST /batch/preset` | Batch preset voice (retourne ZIP) | Variable |
| `POST /batch/design` | Batch voice design (retourne ZIP) | 1.7B-VoiceDesign |
| `POST /batch/clone` | Batch voice clone (retourne ZIP) | 1.7B-Base / 0.6B-Base |
| `POST /tokenizer/encode` | Encoder texte en tokens | - |
| `POST /tokenizer/decode` | Décoder tokens en texte | - |
| `GET /models/status` | Statut des modèles chargés | - |
| `POST /models/preload` | Pré-charger les modèles | - |

## Installation Rapide

```bash
git clone https://github.com/Alexmacapple/VoxQwen.git
cd VoxQwen
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install langdetect  # Optionnel: détection auto de langue
```

## Téléchargement des Modèles

```bash
source venv/bin/activate
python models/download_models.py              # Tous les modèles (~18GB)
python models/download_models.py --list       # Voir les modèles disponibles
python models/download_models.py --model 1.7B-VoiceDesign  # Un modèle spécifique
```

## Démarrage

```bash
source venv/bin/activate
python main.py
# API disponible sur http://localhost:8060
# Documentation Swagger: http://localhost:8060/docs
```

## Exemples d'utilisation

### Preset Voice (voix préréglées)

```bash
curl -X POST http://localhost:8060/preset \
  -F "text=Bonjour, je suis Serena!" \
  -F "voice=Serena" \
  -F "language=fr" \
  --output preset.wav
```

Voix disponibles: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

### Preset Voice avec contrôle émotionnel

```bash
curl -X POST http://localhost:8060/preset/instruct \
  -F "text=Je viens d'apprendre la nouvelle!" \
  -F "voice=Serena" \
  -F "instruct=Ton très joyeux et excité" \
  -F "language=fr" \
  --output preset_joyeux.wav
```

### Voice Design (création de voix par description)

```bash
curl -X POST http://localhost:8060/design \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bonjour, je suis une voix générée par IA.",
    "voice_instruct": "Voix masculine grave, style narrateur documentaire",
    "language": "fr"
  }' \
  --output speech.wav
```

### Voice Clone (clonage de voix)

```bash
# Clonage direct
curl -X POST http://localhost:8060/clone \
  -F "text=Bonjour, je suis un clone de votre voix." \
  -F "reference_audio=@ma_voix.wav" \
  -F "reference_text=Transcription exacte de l'audio" \
  -F "language=fr" \
  -F "model=1.7B" \
  --output clone.wav
```

### Voix personnalisées persistantes

```bash
# 1. Créer une voix personnalisée (persiste après redémarrage)
curl -X POST http://localhost:8060/voices/custom \
  -F "name=ma-voix" \
  -F "source=clone" \
  -F "reference_audio=@ma_voix.wav" \
  -F "reference_text=Transcription exacte"

# 2. Utiliser la voix par son nom
curl -X POST http://localhost:8060/preset \
  -F "text=Bonjour avec ma voix personnalisée" \
  -F "voice=ma-voix" \
  -F "language=fr" \
  --output custom.wav
```

### Batch Processing (génération multiple)

```bash
# Générer plusieurs audios en une requête (retourne ZIP)
curl -X POST http://localhost:8060/batch/preset \
  -H "Content-Type: application/json" \
  -d '{"texts": ["Phrase 1", "Phrase 2", "Phrase 3"], "voice": "Serena"}' \
  -o batch.zip
```

### Détection automatique de langue

```bash
# language=auto détecte automatiquement la langue
curl -X POST http://localhost:8060/preset \
  -F "text=Hello, how are you today?" \
  -F "voice=Serena" \
  -F "language=auto" \
  --output auto_detect.wav
```

### Tokenizer API

```bash
# Encoder du texte en tokens
curl -X POST http://localhost:8060/tokenizer/encode \
  -H "Content-Type: application/json" \
  -d '{"text": "Bonjour"}'

# Décoder des tokens en texte
curl -X POST http://localhost:8060/tokenizer/decode \
  -H "Content-Type: application/json" \
  -d '{"tokens": [81581]}'
```

## Modèles Disponibles

| Modèle | Taille | Utilisation |
|--------|--------|-------------|
| `0.6B-CustomVoice` | 2.3 GB | Voix préréglées rapides |
| `0.6B-Base` | 2.3 GB | Clonage vocal rapide |
| `1.7B-VoiceDesign` | 4.2 GB | Création de voix par description |
| `1.7B-CustomVoice` | 4.2 GB | Voix préréglées + émotions |
| `1.7B-Base` | 4.2 GB | Clonage vocal haute qualité |
| `Tokenizer` | 651 MB | Speech tokenizer (requis) |

**Total : ~18 GB**

## Langues Supportées

Français, Anglais, Chinois, Japonais, Coréen, Allemand, Russe, Portugais, Espagnol, Italien

**+ Détection automatique** : `language=auto` (nécessite `pip install langdetect`)

## Documentation API

| URL | Description |
|-----|-------------|
| http://localhost:8060/docs | Swagger UI - Interface interactive |
| http://localhost:8060/redoc | ReDoc - Documentation lisible |
| http://localhost:8060/openapi.json | Schéma OpenAPI 3.1 |

## Configuration Technique

- **Python** : 3.12
- **Device** : MPS (Apple Silicon) / CUDA / CPU
- **PyTorch** : 2.1+
- **Port API** : 8060

## Ressources

- [Collection HuggingFace Qwen3-TTS](https://huggingface.co/collections/Qwen/qwen3-tts)
- [GitHub Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)

## Licence

MIT
