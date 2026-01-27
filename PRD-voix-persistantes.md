# PRD : Voix Personnalisées Persistantes

**Produit** : TTS-Alex
**Version** : 1.1.0
**Date** : 2026-01-27
**Auteur** : Council (Claude + Gemini) + Synthèse
**Statut** : En attente de validation

---

## 1. Résumé Exécutif

### Problème
Actuellement, les voix créées via Voice Design ou Voice Clone sont stockées en mémoire et **perdues au redémarrage du serveur**. L'utilisateur doit recréer ses voix à chaque session, perdant son investissement en temps et en ajustements.

### Solution
Permettre de sauvegarder les voix créées comme "presets maison" persistants sur disque, qui seront rechargés automatiquement au démarrage et apparaîtront aux côtés des 9 voix natives.

### Contexte
- **Produit** : API locale de synthèse vocale pour Mac Studio
- **Usage** : Personnel/Studio (single-tenant)
- **Stack** : FastAPI + Qwen3-TTS + PyTorch/MPS

---

## 2. Objectifs et Valeur Utilisateur

### 2.1 Objectifs

| Objectif | Métrique de succès |
|----------|-------------------|
| Préserver l'investissement utilisateur | 0 perte de voix après redémarrage |
| Simplifier le workflow | Réutilisation en 1 clic (juste le nom) |
| Enrichir la bibliothèque de voix | > 9 voix disponibles |

### 2.2 Valeur Utilisateur

- **Productivité** : Plus besoin de recréer les voix clonées/designées
- **Cohérence** : Même voix garantie pour un projet long (podcast, audiobook)
- **Professionnalisation** : Constitution d'une bibliothèque de voix métier
- **Expérience** : Workflow fluide, pas de friction

### 2.3 Persona Cible

> **Alex, créateur de contenu audio**
> Utilise TTS-Alex pour générer des voix off pour ses vidéos. Il a passé du temps à cloner la voix d'un narrateur qu'il aime. Il veut retrouver cette voix demain sans refaire le processus.

---

## 3. Spécifications Fonctionnelles

### 3.1 Nouvelles Routes API

#### POST /voices/custom
Sauvegarde une voix personnalisée de façon persistante.

```
POST /voices/custom
Content-Type: multipart/form-data

Paramètres :
- name (str, requis) : Nom unique de la voix (3-50 chars, slug-friendly)
- source (str, requis) : "design" ou "clone"
- description (str, optionnel) : Description de la voix (max 200 chars)

Si source = "design" :
- voice_description (str, requis) : Description textuelle de la voix
- language (str, défaut "fr") : Langue pour la génération

Si source = "clone" :
- reference_audio (file, requis) : Fichier audio de référence
- reference_text (str, requis) : Transcription de l'audio
- model (str, défaut "1.7B") : Modèle à utiliser

Réponse 201 :
{
  "status": "created",
  "voice": {
    "name": "narrateur-grave",
    "type": "custom",
    "source": "clone",
    "description": "Voix masculine grave pour documentaires",
    "created_at": "2026-01-27T19:30:00Z"
  }
}

Erreurs :
- 400 : Nom invalide ou déjà utilisé
- 400 : Paramètres manquants
- 500 : Erreur de génération
```

#### GET /voices (modifié)
Retourne les voix natives ET les voix custom.

```
GET /voices

Réponse 200 :
{
  "voices": [
    {
      "name": "Vivian",
      "type": "native",
      "gender": "Femme",
      "native_lang": "Chinois",
      "description": "Voix feminine jeune, vive et legerement incisive"
    },
    {
      "name": "narrateur-grave",
      "type": "custom",
      "source": "clone",
      "description": "Voix masculine grave pour documentaires",
      "created_at": "2026-01-27T19:30:00Z"
    }
  ],
  "count": 10,
  "native_count": 9,
  "custom_count": 1
}
```

#### DELETE /voices/custom/{name}
Supprime une voix personnalisée.

```
DELETE /voices/custom/narrateur-grave

Réponse 200 :
{
  "status": "deleted",
  "name": "narrateur-grave"
}

Erreurs :
- 404 : Voix non trouvée
- 403 : Impossible de supprimer une voix native
```

#### GET /voices/custom/{name}
Détails d'une voix personnalisée.

```
GET /voices/custom/narrateur-grave

Réponse 200 :
{
  "name": "narrateur-grave",
  "type": "custom",
  "source": "clone",
  "description": "Voix masculine grave pour documentaires",
  "model": "1.7B",
  "created_at": "2026-01-27T19:30:00Z",
  "file_size_bytes": 1548276
}
```

### 3.2 Modifications des Routes Existantes

#### POST /preset et POST /preset/instruct
Le paramètre `voice` accepte maintenant les voix custom en plus des natives.

```
POST /preset
- voice: "narrateur-grave"  # Voix custom acceptée

Erreur 404 si la voix n'existe pas (ni native, ni custom)
```

### 3.3 Règles de Validation

| Règle | Valeur |
|-------|--------|
| Longueur nom | 3-50 caractères |
| Format nom | Alphanumérique + tirets, pas d'espaces |
| Noms réservés | Les 9 noms natifs (Vivian, Serena, etc.) |
| Unicité | Nom unique parmi les voix custom |
| Description max | 200 caractères |

### 3.4 Comportement au Démarrage

1. Le serveur charge `voices/custom/index.json`
2. Les métadonnées sont mises en mémoire
3. Les embeddings sont chargés en **lazy loading** (à la première utilisation)
4. Message dans le banner : "X voix personnalisées chargées"

---

## 4. Architecture Technique

### 4.1 Structure de Stockage

```
tts-alex/
├── voices/
│   └── custom/
│       ├── index.json              # Index des voix custom
│       ├── narrateur-grave/
│       │   ├── meta.json           # Métadonnées
│       │   └── prompt.pt           # Embeddings PyTorch
│       └── voix-corporate/
│           ├── meta.json
│           └── prompt.pt
```

### 4.2 Format des Fichiers

**index.json** (léger, chargé au boot)
```json
{
  "version": "1.0",
  "voices": ["narrateur-grave", "voix-corporate"],
  "updated_at": "2026-01-27T19:30:00Z"
}
```

**meta.json** (par voix)
```json
{
  "name": "narrateur-grave",
  "source": "clone",
  "description": "Voix masculine grave pour documentaires",
  "model": "1.7B",
  "language": "fr",
  "created_at": "2026-01-27T19:30:00Z",
  "prompt_file": "prompt.pt"
}
```

**prompt.pt** (embeddings PyTorch)
- Sauvegardé via `torch.save()`
- Contient les `prompt_items` du clonage ou les embeddings du design
- Taille estimée : 1-3 MB par voix

### 4.3 Cycle de Vie

```
┌─────────────────────────────────────────────────────────────┐
│                     DÉMARRAGE SERVEUR                       │
├─────────────────────────────────────────────────────────────┤
│  1. Charger index.json                                      │
│  2. Pour chaque voix : charger meta.json en mémoire         │
│  3. prompt.pt NON chargé (lazy loading)                     │
│  4. Afficher "X voix personnalisées disponibles"            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CRÉATION VOIX                            │
├─────────────────────────────────────────────────────────────┤
│  1. Valider le nom (unique, format correct)                 │
│  2. Générer les embeddings (Voice Design ou Clone)          │
│  3. Créer le dossier voices/custom/{name}/                  │
│  4. Sauvegarder meta.json                                   │
│  5. Sauvegarder prompt.pt (atomic write via .tmp)           │
│  6. Mettre à jour index.json                                │
│  7. Ajouter en mémoire                                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   UTILISATION VOIX                          │
├─────────────────────────────────────────────────────────────┤
│  1. Requête avec voice="narrateur-grave"                    │
│  2. Si embeddings pas en mémoire : charger prompt.pt        │
│  3. Générer l'audio avec les embeddings                     │
│  4. Retourner le fichier WAV                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   SUPPRESSION VOIX                          │
├─────────────────────────────────────────────────────────────┤
│  1. Vérifier que c'est une voix custom (pas native)         │
│  2. Supprimer le dossier voices/custom/{name}/              │
│  3. Mettre à jour index.json                                │
│  4. Retirer de la mémoire                                   │
└─────────────────────────────────────────────────────────────┘
```

### 4.4 Gestion Mémoire

| Stratégie | Implémentation |
|-----------|----------------|
| Lazy loading | Embeddings chargés à la première utilisation |
| Cache LRU | Optionnel V2 : limiter à N voix en mémoire |
| Métadonnées légères | Toujours en mémoire (~1 KB par voix) |

### 4.5 Sécurité

| Risque | Mitigation |
|--------|------------|
| Path traversal | Validation stricte du nom (regex alphanum + tirets) |
| Noms malicieux | Refuser `.`, `..`, `/`, `\`, caractères spéciaux |
| Saturation disque | Pas de limite V1 (usage local), monitoring V2 |
| Corruption fichiers | Atomic writes (écrire .tmp puis rename) |
| Concurrence | Lock fichier pendant l'écriture |

---

## 5. Implémentation

### 5.1 Fichiers à Modifier

| Fichier | Modifications |
|---------|---------------|
| `main.py` | Nouvelles routes, modification /voices et /preset |
| `main.py` | Fonctions de gestion du stockage |
| `main.py` | Chargement au démarrage |

### 5.2 Nouvelles Dépendances

Aucune nouvelle dépendance requise. Utilisation de :
- `pathlib` (stdlib) pour les chemins
- `json` (stdlib) pour les métadonnées
- `torch.save/load` (déjà présent) pour les embeddings
- `shutil` (stdlib) pour les suppressions

### 5.3 Plan d'Implémentation

#### Phase 1 : MVP (Effort S)
- [ ] Créer la structure `voices/custom/`
- [ ] Implémenter `POST /voices/custom` (clone uniquement)
- [ ] Implémenter le chargement au démarrage
- [ ] Modifier `GET /voices` pour inclure les custom
- [ ] Modifier `/preset` pour accepter les voix custom
- [ ] Tests manuels

#### Phase 2 : Complet (Effort S)
- [ ] Ajouter `DELETE /voices/custom/{name}`
- [ ] Ajouter `GET /voices/custom/{name}`
- [ ] Supporter source="design"
- [ ] Mettre à jour le banner de démarrage
- [ ] Documentation API (docstrings)

#### Phase 3 : Robustesse (Effort XS, optionnel)
- [ ] Atomic writes
- [ ] Validation renforcée
- [ ] Backup index.json.bak

---

## 6. Risques et Mitigations

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Embeddings non sérialisables | Faible | Bloquant | Test préalable avec torch.save/load |
| Incompatibilité après update modèle | Moyen | Moyen | Versionner les prompts, permettre régénération |
| Corruption index.json | Faible | Élevé | Backup automatique avant modification |
| Confusion native/custom | Faible | Faible | Champ "type" explicite dans la réponse |

---

## 7. Hors Scope (V1)

Les éléments suivants sont explicitement exclus de cette version :

- **Tags/Catégories** : Pas de système de tags pour organiser les voix
- **Multi-utilisateur** : Une seule bibliothèque partagée
- **Import/Export** : Pas d'export ZIP ou partage
- **Quotas** : Pas de limite de nombre de voix
- **Cache LRU** : Toutes les voix utilisées restent en mémoire
- **API de mise à jour** : Pas de PUT pour modifier une voix existante
- **Duplication** : Pas de copie d'une voix existante

---

## 8. Effort Estimé

| Phase | Effort | Temps estimé |
|-------|--------|--------------|
| Phase 1 (MVP) | S | 2-3h |
| Phase 2 (Complet) | S | 1-2h |
| Phase 3 (Robustesse) | XS | 30min |
| **Total** | **M** | **4-6h** |

---

## 9. Critères d'Acceptation

### Fonctionnels
- [ ] Je peux créer une voix custom via POST /voices/custom
- [ ] La voix apparaît dans GET /voices avec type="custom"
- [ ] Je peux utiliser la voix dans POST /preset
- [ ] Après redémarrage du serveur, la voix est toujours disponible
- [ ] Je peux supprimer une voix custom
- [ ] Je ne peux pas supprimer une voix native
- [ ] Les noms de voix sont validés (pas de caractères spéciaux)

### Techniques
- [ ] Les embeddings sont sauvegardés en format PyTorch (.pt)
- [ ] L'index.json est mis à jour atomiquement
- [ ] Le lazy loading fonctionne (voix non utilisée = pas en RAM)

---

## 10. Recommandation

### Verdict : **GO**

| Critère | Évaluation |
|---------|------------|
| Valeur utilisateur | **Élevée** - Résout une frustration réelle |
| Effort | **Modéré** - 4-6h de développement |
| Risque technique | **Faible** - Technologies maîtrisées |
| Cohérence produit | **Excellente** - Complète Voice Design/Clone |
| Maintenabilité | **Bonne** - Architecture simple, fichiers JSON |

### Justification

1. **Le problème est réel** : Les prompts en mémoire sont perdus au redémarrage
2. **La solution est simple** : Fichiers JSON + torch.save, pas de BDD
3. **L'usage est local** : Pas de problème de scaling ou multi-tenant
4. **ROI immédiat** : Chaque voix sauvegardée = temps économisé

### Prochaines Étapes

1. Valider le PRD
2. Implémenter Phase 1 (MVP)
3. Tester manuellement
4. Implémenter Phase 2 si satisfait
5. Mettre à jour CLAUDE.md avec les nouvelles routes

---

## 11. Plan de Tests

### Tests de Validation (Manuels)

```bash
# Prérequis : Serveur démarré
kill $(lsof -t -i :8060) 2>/dev/null; python main.py &
sleep 5

# ============================================================
# TEST 1 : Validation des noms
# ============================================================

# 1.1 Nom trop court (doit échouer)
curl -s -X POST http://localhost:8060/voices/custom \
  -F "name=ab" -F "source=clone" | python3 -m json.tool
# Attendu : {"detail": "Nom invalide..."}

# 1.2 Nom réservé (doit échouer)
curl -s -X POST http://localhost:8060/voices/custom \
  -F "name=Vivian" -F "source=clone" | python3 -m json.tool
# Attendu : {"detail": "Nom invalide..."}

# 1.3 Caractères invalides (doit échouer)
curl -s -X POST http://localhost:8060/voices/custom \
  -F "name=voix/test" -F "source=clone" | python3 -m json.tool
# Attendu : {"detail": "Nom invalide..."}

# ============================================================
# TEST 2 : Création de voix (clone)
# ============================================================

# 2.1 Créer une voix clonée
curl -s -X POST http://localhost:8060/voices/custom \
  -F "name=voix-test" \
  -F "source=clone" \
  -F "description=Voix de test" \
  -F "reference_audio=@outputs/test_clone.wav" \
  -F "reference_text=Ceci est un test." \
  -F "model=1.7B" | python3 -m json.tool
# Attendu : {"status": "created", "voice": {...}}

# 2.2 Vérifier les fichiers créés
ls -la voices/custom/voix-test/
# Attendu : meta.json et prompt.pt

# 2.3 Vérifier dans /voices
curl -s http://localhost:8060/voices | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Total: {d[\"count\"]}, Custom: {d[\"custom_count\"]}')"
# Attendu : Total: 10, Custom: 1

# ============================================================
# TEST 3 : Utilisation de la voix custom
# ============================================================

# 3.1 Générer avec /preset
curl -s -X POST http://localhost:8060/preset \
  -F "text=Bonjour avec ma voix personnalisée." \
  -F "voice=voix-test" \
  --output /tmp/test_custom.wav && echo "OK: Audio généré"
# Attendu : OK: Audio généré

# ============================================================
# TEST 4 : Persistance après redémarrage
# ============================================================

# 4.1 Redémarrer le serveur
kill $(lsof -t -i :8060) && sleep 2 && python main.py &
sleep 5

# 4.2 Vérifier que la voix est toujours là
curl -s http://localhost:8060/voices | python3 -c "import sys,json; d=json.load(sys.stdin); custom=[v for v in d['voices'] if v['type']=='custom']; print('Custom:', [v['name'] for v in custom])"
# Attendu : Custom: ['voix-test']

# ============================================================
# TEST 5 : Détails et suppression
# ============================================================

# 5.1 Obtenir les détails
curl -s http://localhost:8060/voices/custom/voix-test | python3 -m json.tool
# Attendu : Métadonnées complètes avec file_size_bytes

# 5.2 Supprimer la voix
curl -s -X DELETE http://localhost:8060/voices/custom/voix-test | python3 -m json.tool
# Attendu : {"status": "deleted", "name": "voix-test"}

# 5.3 Vérifier la suppression
ls -la voices/custom/
# Attendu : Répertoire vide (sauf . et ..)

curl -s http://localhost:8060/voices | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Custom: {d[\"custom_count\"]}')"
# Attendu : Custom: 0

# ============================================================
# TEST 6 : Protection des voix natives
# ============================================================

# 6.1 Tenter de supprimer une voix native
curl -s -X DELETE http://localhost:8060/voices/custom/Serena | python3 -m json.tool
# Attendu : {"detail": "Impossible de supprimer la voix native 'Serena'"}
```

### Tests Automatisés (À implémenter)

```python
# tests/test_custom_voices.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_create_custom_voice_invalid_name():
    response = client.post("/voices/custom", data={"name": "ab", "source": "clone"})
    assert response.status_code == 400
    assert "Nom invalide" in response.json()["detail"]

def test_create_custom_voice_reserved_name():
    response = client.post("/voices/custom", data={"name": "Vivian", "source": "clone"})
    assert response.status_code == 400

def test_delete_native_voice_forbidden():
    response = client.delete("/voices/custom/Serena")
    assert response.status_code == 403

def test_delete_nonexistent_voice():
    response = client.delete("/voices/custom/inexistante")
    assert response.status_code == 404
```

---

## Annexe : Exemples d'Utilisation

### Créer une voix clonée persistante

```bash
# 1. Créer la voix
curl -X POST http://localhost:8060/voices/custom \
  -F "name=narrateur-yves" \
  -F "source=clone" \
  -F "description=Voix d'Yves pour les podcasts" \
  -F "reference_audio=@/path/to/yves.wav" \
  -F "reference_text=Bonjour, je suis Yves et voici mon podcast." \
  -F "model=1.7B"

# Réponse
{
  "status": "created",
  "voice": {
    "name": "narrateur-yves",
    "type": "custom",
    "source": "clone",
    "description": "Voix d'Yves pour les podcasts",
    "created_at": "2026-01-27T20:00:00Z"
  }
}

# 2. Utiliser la voix (maintenant et après redémarrage)
curl -X POST http://localhost:8060/preset \
  -F "text=Bienvenue dans ce nouvel épisode." \
  -F "voice=narrateur-yves" \
  -F "language=fr" \
  --output episode.wav

# 3. Lister les voix
curl http://localhost:8060/voices
# Affiche les 9 natives + narrateur-yves

# 4. Supprimer si besoin
curl -X DELETE http://localhost:8060/voices/custom/narrateur-yves
```

### Créer une voix designée persistante

```bash
curl -X POST http://localhost:8060/voices/custom \
  -F "name=voix-robot" \
  -F "source=design" \
  -F "description=Voix robotique pour les annonces système" \
  -F "voice_description=A robotic, monotone voice with mechanical undertones" \
  -F "language=fr"
```
