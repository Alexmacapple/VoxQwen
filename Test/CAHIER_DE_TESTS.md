# Cahier de Tests - Qwen3-TTS API

## Informations

- **Date** : 2026-01-27
- **Version API** : 1.0.0
- **Environnement** : Mac Studio (Apple Silicon / MPS)
- **URL de base** : http://localhost:8060

---

## Plan de Tests

### Routes à tester (12 routes)

| # | Route | Méthode | Catégorie | Priorité |
|---|-------|---------|-----------|----------|
| 1 | `/` | GET | Health | Haute |
| 2 | `/languages` | GET | Info | Haute |
| 3 | `/voices` | GET | Info | Haute |
| 4 | `/models/status` | GET | Info | Haute |
| 5 | `/models/preload` | POST | Info | Moyenne |
| 6 | `/clone/prompts` | GET | TTS | Moyenne |
| 7 | `/preset` | POST | TTS | Haute |
| 8 | `/preset/instruct` | POST | TTS | Haute |
| 9 | `/design` | POST | TTS | Haute |
| 10 | `/clone` | POST | TTS | Haute |
| 11 | `/clone/prompt` | POST | TTS | Haute |
| 12 | `/clone/prompts/{id}` | DELETE | TTS | Moyenne |

---

## Prérequis

### Dépendances requises
```bash
pip install torchcodec  # Requis pour /clone et /clone/prompt
```

### Démarrage du serveur
```bash
source venv/bin/activate
python main.py
```

### Fichiers de test
- Audio de référence : `outputs/test_preset.wav` (généré par test #7)

---

## Tests Détaillés

### Test 1 : GET /

**Objectif** : Vérifier que l'API répond (health check)

**Commande** :
```bash
curl -s http://localhost:8060/
```

**Réponse attendue** :
```json
{
    "status": "ok",
    "service": "TTS-Alex",
    "device": "mps",
    "models": {...}
}
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] `status` = "ok"
- [ ] `device` = "mps" (sur Mac)

---

### Test 2 : GET /languages

**Objectif** : Lister les 10 langues supportées

**Commande** :
```bash
curl -s http://localhost:8060/languages
```

**Réponse attendue** :
```json
{
    "languages": [
        {"code": "fr", "name": "French"},
        {"code": "en", "name": "English"},
        ...
    ],
    "count": 10,
    "models": {...},
    "device": "mps"
}
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] `count` = 10
- [ ] Langues : fr, en, zh, ja, ko, de, ru, pt, es, it

---

### Test 3 : GET /voices

**Objectif** : Lister les 9 voix préréglées

**Commande** :
```bash
curl -s http://localhost:8060/voices
```

**Réponse attendue** :
```json
{
    "voices": [
        {"name": "Vivian", "gender": "Femme", ...},
        {"name": "Serena", "gender": "Femme", ...},
        ...
    ],
    "count": 9,
    "model": "0.6B-CustomVoice"
}
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] `count` = 9
- [ ] Voix : Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

---

### Test 4 : GET /models/status

**Objectif** : Vérifier le statut des modèles chargés

**Commande** :
```bash
curl -s http://localhost:8060/models/status
```

**Réponse attendue** :
```json
{
    "voice_design_loaded": false,
    "voice_clone_loaded": false,
    "preset_voice_loaded": false,
    "clone_1_7b_loaded": false,
    "clone_0_6b_loaded": false,
    "prompts_cached": 0,
    "device": "mps",
    "mps_available": true,
    "cuda_available": false,
    "models_dir": "/Users/alex/LOIC/tts-alex/models"
}
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] `mps_available` = true (sur Mac)
- [ ] Tous les champs présents

---

### Test 5 : POST /models/preload

**Objectif** : Précharger le modèle 0.6B-CustomVoice

**Commande** :
```bash
curl -s -X POST "http://localhost:8060/models/preload?preset=true"
```

**Réponse attendue** :
```json
{
    "status": "success",
    "loaded": ["preset_voice (0.6B-CustomVoice)"],
    "device": "mps"
}
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] `status` = "success"
- [ ] Modèle apparaît dans la liste `loaded`

---

### Test 6 : GET /clone/prompts

**Objectif** : Lister les prompts en cache (vide au départ)

**Commande** :
```bash
curl -s http://localhost:8060/clone/prompts
```

**Réponse attendue** :
```json
{
    "prompts": [],
    "count": 0
}
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] `count` = 0 (au départ)

---

### Test 7 : POST /preset

**Objectif** : Générer un audio avec une voix préréglée

**Commande** :
```bash
curl -s -X POST http://localhost:8060/preset \
  -F "text=Bonjour, ceci est un test de synthèse vocale." \
  -F "voice=Serena" \
  -F "language=fr" \
  --output outputs/test_preset.wav
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] Fichier WAV créé
- [ ] Taille > 50KB
- [ ] Format : RIFF WAVE, 24000 Hz, mono

**Vérification** :
```bash
file outputs/test_preset.wav
# Attendu: RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 24000 Hz
```

---

### Test 8 : POST /preset/instruct

**Objectif** : Générer un audio avec contrôle émotionnel

**Commande** :
```bash
curl -s -X POST http://localhost:8060/preset/instruct \
  -F "text=Je suis tellement content de vous voir!" \
  -F "voice=Serena" \
  -F "instruct=Ton joyeux et enthousiaste" \
  -F "language=fr" \
  --output outputs/test_preset_instruct.wav
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] Fichier WAV créé
- [ ] Taille > 50KB

---

### Test 9 : POST /design

**Objectif** : Créer une voix à partir d'une description textuelle

**Commande** :
```bash
curl -s -X POST http://localhost:8060/design \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bienvenue dans notre application.",
    "voice_instruct": "Voix masculine grave, style narrateur",
    "language": "fr"
  }' \
  --output outputs/test_design.wav
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] Fichier WAV créé
- [ ] Taille > 50KB

---

### Test 10 : POST /clone

**Objectif** : Cloner une voix depuis un audio de référence

**Prérequis** : Fichier `outputs/test_preset.wav` existant

**Commande** :
```bash
curl -s -X POST http://localhost:8060/clone \
  -F "text=Ceci est un test de clonage vocal." \
  -F reference_audio=@outputs/test_preset.wav \
  -F "reference_text=Bonjour ceci est un test" \
  -F language=fr \
  -F model=1.7B \
  --output outputs/test_clone.wav
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] Fichier WAV créé
- [ ] Taille > 50KB

---

### Test 11 : POST /clone/prompt

**Objectif** : Créer un prompt réutilisable pour le clonage

**Commande** :
```bash
curl -s -X POST http://localhost:8060/clone/prompt \
  -F reference_audio=@outputs/test_preset.wav \
  -F "reference_text=Bonjour ceci est un test" \
  -F model=1.7B
```

**Réponse attendue** :
```json
{
    "prompt_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "model": "1.7B",
    "created_at": "2026-01-27T..."
}
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] `prompt_id` est un UUID valide
- [ ] `model` = "1.7B"

---

### Test 11b : POST /clone avec prompt_id

**Objectif** : Utiliser un prompt existant pour générer un audio

**Commande** :
```bash
curl -s -X POST http://localhost:8060/clone \
  -F "text=Test avec le prompt réutilisable" \
  -F "prompt_id=<PROMPT_ID>" \
  -F language=fr \
  --output outputs/test_clone_with_prompt.wav
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] Fichier WAV créé
- [ ] Génération plus rapide qu'avec reference_audio

---

### Test 12 : DELETE /clone/prompts/{id}

**Objectif** : Supprimer un prompt du cache

**Commande** :
```bash
curl -s -X DELETE http://localhost:8060/clone/prompts/<PROMPT_ID>
```

**Réponse attendue** :
```json
{
    "status": "deleted",
    "prompt_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

**Critères de succès** :
- [ ] HTTP 200
- [ ] `status` = "deleted"
- [ ] Le prompt n'apparaît plus dans GET /clone/prompts

---

## Exécution des Tests

### Script de test complet

```bash
# Voir Test/run_tests.sh
./Test/run_tests.sh
```

### Tests manuels

```bash
# 1. Démarrer le serveur
source venv/bin/activate
python main.py

# 2. Dans un autre terminal, exécuter les tests
./Test/run_tests.sh
```
