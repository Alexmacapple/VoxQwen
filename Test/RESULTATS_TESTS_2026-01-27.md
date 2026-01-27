# Résultats des Tests - 2026-01-27

## Informations d'exécution

| Paramètre | Valeur |
|-----------|--------|
| Date | 2026-01-27 |
| Heure | 16:39 - 16:52 |
| Environnement | Mac Studio (Apple Silicon) |
| Device | MPS |
| URL | http://localhost:8060 |

---

## Résumé

| Statut | Nombre |
|--------|--------|
| ✅ Réussi | 12 |
| ❌ Échoué | 0 |
| ⚠️ Corrigé | 2 |

**Taux de réussite : 100%** (après corrections)

---

## Corrections effectuées pendant les tests

### 1. Dépendance manquante : torchcodec

**Problème** : Les routes `/clone` et `/clone/prompt` échouaient avec l'erreur :
```
{"detail":"TorchCodec is required for load_with_torchcodec. Please install torchcodec to use this function."}
```

**Solution** :
```bash
pip install torchcodec
```

**Fichiers mis à jour** :
- `requirements.txt` : ajout de `torchcodec>=0.10.0`
- `setup.sh` : ajout de `torchcodec` dans l'installation PyTorch

---

### 2. Bug dans main.py:466

**Problème** : La route `/clone` avec `prompt_id` échouait avec l'erreur :
```
{"detail":"Either `voice_clone_prompt` or `ref_audio` must be provided."}
```

**Cause** : Paramètre incorrect dans l'appel à `generate_voice_clone()`

**Correction** :
```python
# Avant (ligne 466)
prompt_items=prompt_data["prompt_items"]

# Après
voice_clone_prompt=prompt_data["prompt_items"]
```

---

## Détail des Tests

### Test 1 : GET /
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| status = "ok" | ✅ OK |
| device = "mps" | ✅ OK |

**Réponse** :
```json
{
    "status": "ok",
    "service": "TTS-Alex",
    "device": "mps",
    "models": {
        "voice_design": "1.7B-VoiceDesign",
        "voice_clone": "1.7B-Base (qualite) / 0.6B-Base (rapide)",
        "preset_voice": "0.6B-CustomVoice",
        "preset_instruct": "1.7B-CustomVoice"
    }
}
```

---

### Test 2 : GET /languages
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| count = 10 | ✅ OK |
| Toutes langues présentes | ✅ OK |

**Langues** : fr, en, zh, ja, ko, de, ru, pt, es, it

---

### Test 3 : GET /voices
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| count = 9 | ✅ OK |
| Toutes voix présentes | ✅ OK |

**Voix** : Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

---

### Test 4 : GET /models/status
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| mps_available = true | ✅ OK |
| Tous champs présents | ✅ OK |

**Réponse** :
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

---

### Test 5 : POST /models/preload
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| status = "success" | ✅ OK |
| Modèle chargé | ✅ OK |

**Réponse** :
```json
{
    "status": "success",
    "loaded": ["preset_voice (0.6B-CustomVoice)"],
    "device": "mps"
}
```

---

### Test 6 : GET /clone/prompts
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| count = 0 | ✅ OK |

**Réponse** :
```json
{
    "prompts": [],
    "count": 0
}
```

---

### Test 7 : POST /preset
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| Fichier créé | ✅ OK |
| Taille | 214K |
| Format WAV | ✅ OK |

**Commande** :
```bash
curl -s -X POST http://localhost:8060/preset \
  -F "text=Bonjour, ceci est un test de synthèse vocale." \
  -F "voice=Serena" \
  -F "language=fr" \
  --output outputs/test_preset.wav
```

**Fichier généré** :
```
-rw-r--r--  1 alex  staff  214K  outputs/test_preset.wav
RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 24000 Hz
```

---

### Test 8 : POST /preset/instruct
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| Fichier créé | ✅ OK |
| Taille | 100K |

**Commande** :
```bash
curl -s -X POST http://localhost:8060/preset/instruct \
  -F "text=Je suis tellement content de vous voir!" \
  -F "voice=Serena" \
  -F "instruct=Ton joyeux et enthousiaste" \
  -F "language=fr" \
  --output outputs/test_preset_instruct.wav
```

**Fichier généré** :
```
-rw-r--r--  1 alex  staff  100K  outputs/test_preset_instruct.wav
```

---

### Test 9 : POST /design
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| Fichier créé | ✅ OK |
| Taille | 156K |

**Commande** :
```bash
curl -s -X POST http://localhost:8060/design \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bienvenue dans notre application de synthèse vocale.",
    "voice_instruct": "Voix masculine grave et posée, style narrateur documentaire",
    "language": "fr"
  }' \
  --output outputs/test_design.wav
```

**Fichier généré** :
```
-rw-r--r--  1 alex  staff  156K  outputs/test_design.wav
```

---

### Test 10 : POST /clone
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 (après install torchcodec) |
| Fichier créé | ✅ OK |
| Taille | 123K |

**Commande** :
```bash
curl -s -X POST http://localhost:8060/clone \
  -F "text=Ceci est un test de clonage vocal." \
  -F reference_audio=@outputs/test_preset.wav \
  -F "reference_text=Bonjour ceci est un test de synthese vocale" \
  -F language=fr \
  -F model=1.7B \
  --output outputs/test_clone.wav
```

**Fichier généré** :
```
-rw-r--r--  1 alex  staff  123K  outputs/test_clone.wav
```

---

### Test 11 : POST /clone/prompt
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| prompt_id généré | ✅ OK |
| Format UUID | ✅ OK |

**Commande** :
```bash
curl -s -X POST http://localhost:8060/clone/prompt \
  -F reference_audio=@outputs/test_preset.wav \
  -F "reference_text=Bonjour ceci est un test" \
  -F model=1.7B
```

**Réponse** :
```json
{
    "prompt_id": "84dab8eb-d793-41e4-a6e0-95e8ec686c32",
    "model": "1.7B",
    "created_at": "2026-01-27T16:51:53.920257"
}
```

---

### Test 11b : POST /clone avec prompt_id
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 (après fix bug) |
| Fichier créé | ✅ OK |
| Taille | 90K |

**Commande** :
```bash
curl -s -X POST http://localhost:8060/clone \
  -F "text=Test avec le prompt reutilisable" \
  -F "prompt_id=84dab8eb-d793-41e4-a6e0-95e8ec686c32" \
  -F language=fr \
  --output outputs/test_clone_with_prompt.wav
```

**Fichier généré** :
```
-rw-r--r--  1 alex  staff  90K  outputs/test_clone_with_prompt.wav
```

---

### Test 12 : DELETE /clone/prompts/{id}
| Critère | Résultat |
|---------|----------|
| HTTP Status | ✅ 200 |
| status = "deleted" | ✅ OK |
| Prompt supprimé | ✅ OK |

**Avant suppression** :
```json
{"prompts":[{"prompt_id":"84dab8eb-d793-41e4-a6e0-95e8ec686c32","model":"1.7B","created_at":"2026-01-27T16:51:53.920257"}],"count":1}
```

**Commande** :
```bash
curl -s -X DELETE http://localhost:8060/clone/prompts/84dab8eb-d793-41e4-a6e0-95e8ec686c32
```

**Réponse** :
```json
{"status":"deleted","prompt_id":"84dab8eb-d793-41e4-a6e0-95e8ec686c32"}
```

**Après suppression** :
```json
{"prompts":[],"count":0}
```

---

## Fichiers Audio Générés

| Fichier | Taille | Route | Statut |
|---------|--------|-------|--------|
| `test_preset.wav` | 214K | POST /preset | ✅ |
| `test_preset_instruct.wav` | 100K | POST /preset/instruct | ✅ |
| `test_design.wav` | 156K | POST /design | ✅ |
| `test_clone.wav` | 123K | POST /clone | ✅ |
| `test_clone_with_prompt.wav` | 90K | POST /clone + prompt_id | ✅ |

---

## Conclusion

**Tous les tests sont passés avec succès** après les deux corrections :
1. Installation de `torchcodec`
2. Correction du bug `prompt_items` → `voice_clone_prompt`

L'API Qwen3-TTS est pleinement fonctionnelle.
