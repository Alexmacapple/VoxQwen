# PRD - Complétion des Routes TTS-Alex

## Contexte

L'API TTS-Alex couvre ~80% des fonctionnalités Qwen3-TTS. Suite à l'audit du Council (Claude + Gemini), des lacunes critiques ont été identifiées.

### Problèmes identifiés

| Priorité | Problème | Impact |
|----------|----------|--------|
| **CRITIQUE** | `/clone` utilise 1.7B-CustomVoice au lieu de 1.7B-Base | Les modèles Base sont conçus pour le clonage |
| **CRITIQUE** | `create_voice_clone_prompt()` non exposé | Retraitement audio à chaque requête = lent |
| **IMPORTANT** | Pas de choix de modèle pour clonage | Impossible de choisir vitesse vs qualité |
| **MINEUR** | Tokenizer non exposé | Optionnel pour API haut niveau |

### Découverte technique importante

**`create_voice_clone_prompt()` n'est disponible QUE sur les modèles Base** (0.6B-Base et 1.7B-Base), pas sur CustomVoice. Cela signifie que :

1. Le `/clone` actuel utilise le mauvais modèle
2. Le `/clone/prompt` WIP ne peut pas fonctionner avec 1.7B-CustomVoice

---

## Spécifications Fonctionnelles

### 1. Nouveau modèle de chargement pour clonage

**Fichier**: `main.py`

Remplacer `load_voice_clone_model()` pour charger **1.7B-Base** au lieu de 1.7B-CustomVoice.

```python
# Avant
model_path = MODELS_DIR / "1.7B-CustomVoice"

# Après
model_path = MODELS_DIR / "1.7B-Base"
```

Ajouter une nouvelle fonction pour 0.6B-Base (clonage rapide).

### 2. Route `/clone` améliorée

**Modifications** :
- Utiliser 1.7B-Base par défaut
- Ajouter paramètre `model`: `"1.7B"` (qualité) ou `"0.6B"` (rapide)
- Ajouter paramètre optionnel `prompt_id` pour réutiliser un prompt

**Signature** :
```python
POST /clone
  - text: str (requis)
  - reference_audio: UploadFile (requis SI pas de prompt_id)
  - reference_text: str (optionnel mais recommandé)
  - language: str = "fr"
  - model: str = "1.7B"  # NOUVEAU: "1.7B" | "0.6B"
  - prompt_id: str = None  # NOUVEAU: réutilise un prompt existant
```

### 3. Route `/clone/prompt` complète

**Objectif** : Créer un prompt réutilisable pour éviter de retraiter l'audio.

**Fonctionnement** :
1. Upload audio de référence + transcription
2. Appel `model.create_voice_clone_prompt()`
3. Stockage en mémoire (dict global) avec UUID
4. Retourne `prompt_id`

**Signature** :
```python
POST /clone/prompt
  - reference_audio: UploadFile (requis)
  - reference_text: str (optionnel, recommandé pour qualité)
  - model: str = "1.7B"  # "1.7B" | "0.6B"

Retourne:
{
  "prompt_id": "uuid-xxx",
  "model": "1.7B",
  "created_at": "2026-01-27T16:00:00",
  "expires_in": 3600  # secondes (optionnel)
}
```

### 4. Route `/clone/prompts` (liste)

**Objectif** : Lister les prompts en cache.

```python
GET /clone/prompts

Retourne:
{
  "prompts": [
    {"prompt_id": "xxx", "model": "1.7B", "created_at": "..."},
    ...
  ],
  "count": 2
}
```

### 5. Route `/clone/prompts/{prompt_id}` (suppression)

```python
DELETE /clone/prompts/{prompt_id}

Retourne:
{"status": "deleted", "prompt_id": "xxx"}
```

---

## Architecture Technique

### Stockage des prompts (in-memory)

```python
# Nouveau dictionnaire global
voice_clone_prompts: Dict[str, Dict] = {}

# Structure d'un prompt stocké
{
    "prompt_id": "uuid",
    "prompt_items": [...],  # Résultat de create_voice_clone_prompt()
    "model": "1.7B",
    "created_at": datetime,
}
```

### Nouveaux loaders de modèles

```python
# Modèles Base pour clonage (NOUVEAUX)
clone_model_1_7b = None  # 1.7B-Base
clone_model_0_6b = None  # 0.6B-Base

def load_clone_model(model_size: str = "1.7B"):
    """Charge le modèle Base approprié pour le clonage."""
    ...
```

### Mapping des routes aux modèles

| Route | Modèle | Fonction Qwen3-TTS |
|-------|--------|-------------------|
| `/preset` | 0.6B-CustomVoice | `generate_custom_voice()` |
| `/preset/instruct` | 1.7B-CustomVoice | `generate_custom_voice(instruct=)` |
| `/design` | 1.7B-VoiceDesign | `generate_voice_design()` |
| `/clone` | **1.7B-Base** ou 0.6B-Base | `generate_voice_clone()` |
| `/clone/prompt` | **1.7B-Base** ou 0.6B-Base | `create_voice_clone_prompt()` |

---

## Fichiers à modifier

| Fichier | Modifications |
|---------|---------------|
| `main.py` | Toutes les modifications (routes, loaders, storage) |
| `CLAUDE.md` | Mise à jour documentation routes |
| `README.md` | Mise à jour documentation + exemples curl |

---

## Plan d'implémentation

### Étape 1 : Nouveaux loaders de modèles
- Renommer `load_voice_clone_model()` → garder pour CustomVoice
- Ajouter `load_clone_base_model(size="1.7B"|"0.6B")`
- Ajouter variables globales `clone_model_1_7b`, `clone_model_0_6b`

### Étape 2 : Storage des prompts
- Ajouter `voice_clone_prompts: Dict = {}`
- Ajouter fonction helper `store_prompt()`, `get_prompt()`, `delete_prompt()`

### Étape 3 : Implémenter `/clone/prompt`
- Compléter la route WIP existante
- Générer UUID, stocker prompt, retourner ID

### Étape 4 : Routes de gestion des prompts
- `GET /clone/prompts` - lister
- `DELETE /clone/prompts/{prompt_id}` - supprimer

### Étape 5 : Modifier `/clone`
- Ajouter paramètre `model`
- Ajouter paramètre `prompt_id`
- Si `prompt_id` fourni → utiliser prompt stocké
- Sinon → créer prompt à la volée

### Étape 6 : Mettre à jour `/models/status` et `/models/preload`
- Ajouter statut des modèles Base
- Permettre preload des modèles Base

### Étape 7 : Documentation
- Mettre à jour `CLAUDE.md`
- Mettre à jour `README.md` avec exemples

---

## Exemples d'utilisation (après implémentation)

### Workflow optimisé pour clonage répété

```bash
# 1. Créer un prompt réutilisable
curl -X POST http://localhost:8060/clone/prompt \
  -F "reference_audio=@ma_voix.wav" \
  -F "reference_text=Bonjour, ceci est ma voix de référence." \
  -F "model=1.7B"

# Réponse: {"prompt_id": "abc123", ...}

# 2. Utiliser le prompt pour générer plusieurs audios (rapide!)
curl -X POST http://localhost:8060/clone \
  -F "text=Première phrase avec ma voix clonée." \
  -F "prompt_id=abc123" \
  -F "language=fr" \
  --output phrase1.wav

curl -X POST http://localhost:8060/clone \
  -F "text=Deuxième phrase, même voix, sans retraiter l'audio!" \
  -F "prompt_id=abc123" \
  -F "language=fr" \
  --output phrase2.wav
```

### Clonage rapide avec 0.6B

```bash
curl -X POST http://localhost:8060/clone \
  -F "text=Génération rapide avec le petit modèle." \
  -F "reference_audio=@voix.wav" \
  -F "model=0.6B" \
  -F "language=fr" \
  --output rapide.wav
```

---

## Vérification

### Tests manuels

1. **Test `/clone/prompt`** : Créer un prompt, vérifier UUID retourné
2. **Test `/clone` avec prompt_id** : Utiliser le prompt, vérifier que c'est plus rapide
3. **Test `/clone` avec model=0.6B** : Vérifier que le petit modèle est utilisé
4. **Test `/clone/prompts`** : Lister les prompts créés
5. **Test DELETE** : Supprimer un prompt, vérifier qu'il n'est plus accessible

### Commandes de test

```bash
# Démarrer le serveur
source venv/bin/activate
python main.py

# Dans un autre terminal, exécuter les tests curl ci-dessus
```

---

## Notes importantes

1. **Modèles Base requis** : S'assurer que `models/1.7B-Base/` et `models/0.6B-Base/` existent
2. **Mémoire** : Les prompts sont stockés en RAM - prévoir nettoyage si trop nombreux
3. **dtype** : Utiliser `float32` pour 0.6B (comme preset) et `float16` pour 1.7B
4. **Rétrocompatibilité** : `/clone` fonctionne toujours sans `prompt_id` ni `model`

---

## Statut

**Implémenté le** : 2026-01-27

**Fichiers modifiés** :
- `main.py` - Toutes les routes et loaders
- `CLAUDE.md` - Documentation mise à jour
- `README.md` - Exemples d'utilisation ajoutés
