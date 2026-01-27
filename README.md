# TTS-Alex - Qwen3-TTS Local API

API locale pour Qwen3-TTS sur Mac Studio (Apple Silicon / MPS).

## Fonctionnalites

| Route | Fonction | Modele |
|-------|----------|--------|
| `GET /` | Health check | - |
| `GET /languages` | Liste des 10 langues supportees | - |
| `GET /voices` | Liste des 9 voix prereglees | - |
| `POST /preset` | Voix prereglees (rapide) | 0.6B-CustomVoice |
| `POST /preset/instruct` | Voix prereglees + controle emotions/styles | 1.7B-CustomVoice |
| `POST /design` | Voice Design (creation de voix par description) | 1.7B-VoiceDesign |
| `POST /clone` | Voice Clone (clonage depuis audio ou prompt) | 1.7B-Base / 0.6B-Base |
| `POST /clone/prompt` | Creer un prompt reutilisable pour clonage | 1.7B-Base / 0.6B-Base |
| `GET /clone/prompts` | Lister les prompts en cache | - |
| `DELETE /clone/prompts/{id}` | Supprimer un prompt | - |
| `GET /models/status` | Statut des modeles charges | - |
| `POST /models/preload` | Pre-charger les modeles | - |

## Installation Rapide

```bash
cd /Users/alex/LOIC/tts-alex
./setup.sh
```

Ou manuellement :

```bash
cd /Users/alex/LOIC/tts-alex
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Telechargement des Modeles

```bash
source venv/bin/activate
python download_models.py              # Tous les modeles (~18GB)
python download_models.py --list       # Voir les modeles disponibles
python download_models.py --model 1.7B-VoiceDesign  # Un modele specifique
```

## Demarrage

```bash
source venv/bin/activate
python main.py
# API disponible sur http://localhost:8060
```

### Redemarrer le serveur

Apres modification de `main.py`, il faut redemarrer le serveur :

```bash
# Methode 1 : Manuelle
lsof -i :8060                    # Trouver le PID
kill <PID>                       # Arreter le serveur
python main.py                   # Relancer

# Methode 2 : Une seule commande
kill $(lsof -t -i :8060) 2>/dev/null; python main.py
```

## Documentation API (Swagger/OpenAPI)

L'API genere automatiquement une documentation interactive conforme OpenAPI 3.1 :

| URL | Description |
|-----|-------------|
| http://localhost:8060/docs | **Swagger UI** - Interface interactive pour tester les routes |
| http://localhost:8060/redoc | **ReDoc** - Documentation alternative plus lisible |
| http://localhost:8060/openapi.json | **Schema OpenAPI 3.1** - JSON brut pour integration |

```bash
# Ouvrir la documentation Swagger dans le navigateur
open http://localhost:8060/docs

# Telecharger le schema OpenAPI
curl http://localhost:8060/openapi.json -o openapi.json
```

## Utilisation

### Preset Voice (voix prereglees - rapide)

```bash
curl -X POST http://localhost:8060/preset \
  -F "text=Bonjour, je suis Serena!" \
  -F "voice=Serena" \
  -F "language=fr" \
  --output preset.wav
```

Voix disponibles: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

### Preset Voice avec controle emotionnel (1.7B)

```bash
curl -X POST http://localhost:8060/preset/instruct \
  -F "text=Je viens d'apprendre la nouvelle!" \
  -F "voice=Serena" \
  -F "instruct=Ton tres joyeux et excite" \
  -F "language=fr" \
  --output preset_joyeux.wav
```

Exemples d'instructions:
- Emotions: "Triste et melancolique", "En colere et frustree", "Effrayee et anxieuse"
- Styles: "Chuchotant doucement", "Parlant tres vite", "Tres dramatique et theatral"
- Scenarios: "Commentateur sportif energique", "Presentation professionnelle"

### Voice Design (creation de voix par description)

```bash
curl -X POST http://localhost:8060/design \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bonjour, je suis une voix generee par IA.",
    "voice_instruct": "Voix masculine grave, style narrateur documentaire",
    "language": "fr"
  }' \
  --output speech.wav
```

### Voice Clone (clonage de voix)

```bash
# Mode simple : clonage direct (retraite l'audio a chaque requete)
curl -X POST http://localhost:8060/clone \
  -F "text=Bonjour, je suis un clone de votre voix." \
  -F "reference_audio=@ma_voix.wav" \
  -F "reference_text=Transcription de l'audio de reference" \
  -F "language=fr" \
  -F "model=1.7B" \
  --output clone.wav

# Avec le modele 0.6B (plus rapide, qualite legerement inferieure)
curl -X POST http://localhost:8060/clone \
  -F "text=Generation rapide." \
  -F "reference_audio=@ma_voix.wav" \
  -F "model=0.6B" \
  -F "language=fr" \
  --output clone_rapide.wav
```

### Voice Clone avec prompts reutilisables (recommande pour plusieurs phrases)

```bash
# 1. Creer un prompt reutilisable (traite l'audio une seule fois)
curl -X POST http://localhost:8060/clone/prompt \
  -F "reference_audio=@ma_voix.wav" \
  -F "reference_text=Bonjour, ceci est ma voix de reference." \
  -F "model=1.7B"

# Reponse: {"prompt_id": "abc123-...", "model": "1.7B", "created_at": "..."}

# 2. Utiliser le prompt pour generer plusieurs audios (beaucoup plus rapide!)
curl -X POST http://localhost:8060/clone \
  -F "text=Premiere phrase avec ma voix clonee." \
  -F "prompt_id=abc123-..." \
  -F "language=fr" \
  --output phrase1.wav

curl -X POST http://localhost:8060/clone \
  -F "text=Deuxieme phrase, meme voix, sans retraiter l'audio!" \
  -F "prompt_id=abc123-..." \
  -F "language=fr" \
  --output phrase2.wav

# 3. Lister les prompts en cache
curl http://localhost:8060/clone/prompts

# 4. Supprimer un prompt
curl -X DELETE http://localhost:8060/clone/prompts/abc123-...
```

## Modeles Disponibles

Tous les modeles sont stockes localement dans `models/` (pas de cache HuggingFace).

| Modele | Taille | Utilisation |
|--------|--------|-------------|
| `0.6B-CustomVoice` | 2.3 GB | 9 voix prereglees, 10 langues (`/preset`) |
| `0.6B-Base` | 2.3 GB | Clonage vocal rapide (`/clone` avec model=0.6B) |
| `1.7B-VoiceDesign` | 4.2 GB | Creation de voix par description (`/design`) |
| `1.7B-CustomVoice` | 4.2 GB | Voix prereglees + emotions (`/preset/instruct`) |
| `1.7B-Base` | 4.2 GB | Clonage vocal haute qualite (`/clone` avec model=1.7B) |
| `Tokenizer` | 651 MB | Speech tokenizer (requis par tous les modeles) |

**Total : ~18 GB**

## Langues Supportees

Francais, Anglais, Chinois, Japonais, Coreen, Allemand, Russe, Portugais, Espagnol, Italien

## Structure du Projet

```
tts-alex/
├── main.py              # API FastAPI
├── download_models.py   # Script de telechargement des modeles
├── setup.sh             # Script d'installation
├── requirements.txt     # Dependances Python
├── models/              # Modeles Qwen3-TTS (locaux)
│   ├── 0.6B-CustomVoice/
│   ├── 0.6B-Base/
│   ├── 1.7B-VoiceDesign/
│   ├── 1.7B-CustomVoice/
│   ├── 1.7B-Base/
│   └── Tokenizer/
├── outputs/             # Fichiers audio generes
├── venv/                # Environnement virtuel Python
└── Documentation/       # Guides et documentation
```

## Configuration Technique

- **Python** : 3.12
- **Device** : MPS (Apple Silicon)
- **PyTorch** : 2.1+
- **TorchCodec** : 0.10+ (requis pour le clonage vocal)
- **Port API** : 8060

## Ressources

- [Collection HuggingFace Qwen3-TTS](https://huggingface.co/collections/Qwen/qwen3-tts)
- [GitHub Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- [Demo HuggingFace](https://huggingface.co/spaces/Qwen/Qwen3-TTS)
