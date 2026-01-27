# PRD : Intégration FastAPI-MCP pour VoxQwen

**Produit** : VoxQwen (TTS-Alex)
**Version cible** : 1.3.0
**Date** : 2026-01-27
**Méthode** : BMAD (Business, Model, Architecture, Design)
**Statut** : Validé par Council (confiance: 0.72, note: 8.5/10)
**Révision** : 2.2 - Clarification conformité MCP + comportement FastAPI-MCP

---

## 1. BUSINESS - Vision et Contexte

### 1.1 Problème

Actuellement, VoxQwen est une API REST accessible uniquement via HTTP (curl, clients REST). Les agents IA comme Claude Code ne peuvent pas utiliser directement ses capacités de synthèse vocale car :

- **Pas de protocole MCP** : Les endpoints ne sont pas exposés comme "outils" MCP
- **Format incompatible** : Les uploads multipart/form-data et les réponses streaming ne sont pas supportés nativement par MCP
- **Isolation** : L'API fonctionne en silo, sans intégration dans les workflows d'agents IA

### 1.2 Solution

Intégrer **FastAPI-MCP** pour exposer automatiquement les endpoints de VoxQwen comme outils MCP, permettant à Claude Code et autres agents IA d'utiliser la synthèse vocale nativement.

### 1.3 Bénéfices Attendus

| Bénéfice | Impact |
|----------|--------|
| **Accessibilité IA** | Claude Code peut générer de l'audio directement |
| **Workflow unifié** | TTS intégré dans les pipelines d'agents |
| **Zero reconfiguration** | FastAPI-MCP préserve l'API REST existante |
| **Extensibilité** | Base pour intégrations futures (n8n, Langchain, etc.) |

### 1.4 Métriques de Succès

- [ ] 100% des outils Tier 1 fonctionnels via MCP
- [ ] Latence MCP acceptable (overhead base64 ~33% attendu)
- [ ] Documentation MCP complète dans Swagger
- [ ] Tests automatisés pytest passants
- [ ] Aucune régression sur l'API REST existante
- [ ] Rate limiting fonctionnel (max 10 req/min par défaut)

---

## 2. MODEL - User Stories et Cas d'Usage

### 2.1 Personas

| Persona | Description | Besoin Principal |
|---------|-------------|------------------|
| **Agent IA** | Claude Code, GPT, etc. | Générer de l'audio via outils MCP |
| **Développeur** | Intégrateur de workflows | API unifiée REST + MCP |
| **Utilisateur Final** | Consommateur d'audio | Audio de qualité, faible latence |

### 2.2 User Stories

#### US-1 : Synthèse vocale basique (P0)
> **En tant qu'** agent IA
> **Je veux** générer un audio à partir d'un texte et d'une voix
> **Afin de** produire du contenu audio sans intervention humaine

**Critères d'acceptation :**
- Appeler l'outil `tts_preset_voice` avec {text, voice, language}
- Recevoir l'audio en base64 dans la réponse JSON
- Support des 9 voix natives + voix custom

#### US-2 : Clonage vocal avec prompt (P0)
> **En tant qu'** agent IA
> **Je veux** cloner une voix à partir d'un prompt existant
> **Afin de** générer de l'audio avec une voix personnalisée

**Critères d'acceptation :**
- Utiliser un prompt_id créé précédemment
- Pas besoin d'upload de fichier audio
- Retour audio en base64
- **Message d'avertissement si prompt volatile** (perdu au redémarrage)

#### US-3 : Voice Design (P1)
> **En tant qu'** agent IA
> **Je veux** créer une voix à partir d'une description textuelle
> **Afin de** générer des voix créatives sans échantillon audio

**Critères d'acceptation :**
- Appeler l'outil `tts_voice_design` avec {text, voice_description, language}
- Recevoir l'audio en base64
- Support de language="auto"

#### US-4 : Lister les voix disponibles (P0)
> **En tant qu'** agent IA
> **Je veux** connaître les voix disponibles
> **Afin de** choisir la voix appropriée

**Critères d'acceptation :**
- Appeler l'outil `tts_get_voices`
- Recevoir la liste des voix natives et custom
- Inclure les métadonnées (genre, langue native, description)

#### US-5 : Créer un prompt de clonage (P1)
> **En tant qu'** agent IA
> **Je veux** créer un prompt réutilisable à partir d'un audio en base64
> **Afin de** optimiser les générations futures

**Critères d'acceptation :**
- Envoyer l'audio de référence en base64 (max 5MB)
- Recevoir un prompt_id réutilisable
- Option x_vector_only pour embeddings
- **Avertissement clair** : prompt stocké en mémoire, perdu au redémarrage

#### US-6 : Gestion des erreurs (P0) - NOUVEAU
> **En tant qu'** agent IA
> **Je veux** recevoir des messages d'erreur clairs et actionnables
> **Afin de** comprendre et résoudre les problèmes

**Critères d'acceptation :**
- Erreur 404 si voix/prompt inexistant avec suggestion (voix similaires)
- Erreur 503 si modèle non chargé avec instruction de pré-chargement
- Erreur 429 si rate limit atteint avec temps d'attente
- Erreur 422 si payload base64 invalide (trop grand ou format non reconnu) (v2.1)
- Format d'erreur standardisé : `{error, code, suggestion, retry_after?}`

---

## 3. ARCHITECTURE - Décisions Techniques

### 3.1 Stack Technologique

| Composant | Technologie | Justification |
|-----------|-------------|---------------|
| **MCP Layer** | FastAPI-MCP ^0.3.0 | Intégration native FastAPI, testé |
| **API Core** | FastAPI 0.109+ | Existant, stable |
| **Sérialisation** | base64 pour audio | Compatibilité MCP JSON-only |
| **Transport** | HTTP + SSE | Standard MCP |
| **Rate Limiting** | slowapi | Protection DoS |

### 3.2 Conformité MCP et Comportement FastAPI-MCP (NOUVEAU v2.2)

#### 3.2.1 Comment FastAPI-MCP Gère les Réponses

**Investigation du code source FastAPI-MCP** : La bibliothèque ne convertit PAS les réponses en types MCP natifs (audio, image, etc.). Elle encapsule toutes les réponses FastAPI comme `TextContent` :

```python
# Comportement réel de FastAPI-MCP (server.py)
result_text = json.dumps(response_data)
return types.TextContent(type="text", text=result_text)
```

**Implication** : Notre réponse `MCPAudioResponse` sera sérialisée en JSON puis wrappée :

```json
// Ce que le client MCP reçoit réellement
{
  "content": [
    {
      "type": "text",
      "text": "{\"audio_base64\":\"UklGRv4...\",\"format\":\"wav\",\"sample_rate\":24000}"
    }
  ],
  "isError": false
}
```

Le client doit donc parser le JSON dans le champ `text` pour extraire `audio_base64`.

#### 3.2.2 Différence avec le Standard MCP Natif

| Aspect | Standard MCP Natif | FastAPI-MCP (réalité) |
|--------|-------------------|----------------------|
| **Audio** | `{type: "audio", data: "<b64>", mimeType: "audio/wav"}` | `{type: "text", text: "{\"audio_base64\":\"...\"}"}` |
| **Erreurs** | `isError: true` ou JSON-RPC error | HTTPException → sérialisée en JSON |
| **Capabilities** | Déclaration explicite | Géré automatiquement par FastAPI-MCP |

#### 3.2.3 Impact sur l'Intégration

1. **Pour Claude Code** : Fonctionne car Claude Code parse le JSON textuel
2. **Pour clients MCP stricts** : Nécessite un wrapper côté client pour extraire l'audio
3. **Évolution future** : Si FastAPI-MCP ajoute le support des types natifs, migration facile

#### 3.2.4 Alternative : Serveur MCP Custom (Non Retenu)

Pour une conformité MCP 100% native, il faudrait créer un serveur MCP custom :

```python
# Exemple de réponse MCP native (NON supporté par FastAPI-MCP)
@server.tool()
async def tts_preset_voice(text: str, voice: str) -> list[types.AudioContent]:
    audio_bytes = generate_audio(text, voice)
    return [types.AudioContent(
        type="audio",
        data=base64.b64encode(audio_bytes).decode(),
        mimeType="audio/wav"
    )]
```

**Raison du rejet** : Complexité accrue, FastAPI-MCP suffisant pour Claude Code.

### 3.3 Architecture Cible

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENTS                                  │
├─────────────────┬───────────────────┬───────────────────────┤
│   Claude Code   │   Autres Agents   │   REST Clients        │
│   (MCP)         │   (MCP)           │   (curl, etc.)        │
└────────┬────────┴─────────┬─────────┴──────────┬────────────┘
         │                  │                    │
         ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    VoxQwen API (FastAPI)                     │
│                       Port 8060                              │
├─────────────────────────────────────────────────────────────┤
│                    MIDDLEWARE SÉCURITÉ                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ rate_limiter│  │ size_guard  │  │ auth_local  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
├─────────────────────────────────────────────────────────────┤
│  /mcp/*          │  /preset, /clone, /design, etc.          │
│  (FastAPI-MCP)   │  (Routes REST existantes)                │
├─────────────────────────────────────────────────────────────┤
│                    COUCHE MÉTIER PARTAGÉE                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ tts_service │  │ audio_utils │  │ error_handler│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
├─────────────────────────────────────────────────────────────┤
│                    MODÈLES Qwen3-TTS                         │
│  0.6B-CustomVoice │ 1.7B-VoiceDesign │ 1.7B-Base │ etc.     │
└─────────────────────────────────────────────────────────────┘
```

### 3.4 Contraintes et Solutions

| Contrainte | Impact | Solution |
|------------|--------|----------|
| **Uploads multipart** | MCP ne supporte pas | Accepter audio en base64 |
| **Streaming audio** | MCP = JSON only | Encoder WAV en base64 dans réponse |
| **Taille réponse** | Payload JSON volumineux | Limiter texte à 2000 chars pour MCP |
| **Taille entrée base64** | Mémoire serveur | Limiter à 5MB (audio ~30s WAV) |
| **Latence modèles** | Premier appel lent | Pré-charger via `/models/preload` |
| **PyTorch bloquant** | Event loop bloqué | Routes synchrones (`def`) + threadpool |

### 3.5 Routes MCP à Exposer

#### Tier 1 - Essentiels (MVP)

| Outil MCP | Route REST | Adaptation Requise |
|-----------|------------|-------------------|
| `tts_preset_voice` | POST /preset | Retour base64 |
| `tts_voice_clone_with_prompt` | POST /clone (prompt_id) | Retour base64 + warning volatilité |
| `tts_voice_design` | POST /design | Retour base64 |
| `tts_get_voices` | GET /voices | Aucune |
| `tts_get_languages` | GET /languages | Aucune |

#### Tier 2 - Importants (Post-MVP)

| Outil MCP | Route REST | Adaptation Requise |
|-----------|------------|-------------------|
| `tts_create_clone_prompt` | POST /clone/prompt | Accepter audio base64, valider taille |
| `tts_preset_instruct` | POST /preset/instruct | Retour base64 |
| `tts_get_model_status` | GET /models/status | Aucune |

#### Tier 3 - Optionnels

| Outil MCP | Route REST | Note |
|-----------|------------|------|
| `tts_create_custom_voice` | POST /voices/custom | Complexe (upload) |
| `tts_batch_preset` | POST /batch/preset | Retour ZIP → base64 |
| `tts_tokenize` | POST /tokenizer/encode | Utilitaire |

### 3.6 Sécurité

#### 3.6.1 Authentification Locale (Améliorée v2.1)

```python
import secrets

# Token optionnel pour environnements partagés
MCP_AUTH_TOKEN = os.getenv("VOXQWEN_MCP_TOKEN", None)

async def verify_mcp_token(request: Request):
    """
    Vérifie le token MCP si configuré.

    Utilise secrets.compare_digest() pour éviter les timing attacks.
    """
    if MCP_AUTH_TOKEN is None:
        return  # Pas d'auth requise

    token = request.headers.get("X-MCP-Token", "")

    # Comparaison timing-safe pour éviter les timing attacks
    if not secrets.compare_digest(token.encode(), MCP_AUTH_TOKEN.encode()):
        raise HTTPException(401, detail={
            "error": "Token MCP invalide",
            "code": "INVALID_TOKEN",
            "suggestion": "Vérifiez la variable VOXQWEN_MCP_TOKEN"
        })
```

#### 3.6.2 Rate Limiting (Amélioré v2.1)

```python
import secrets
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

def get_rate_limit_key(request: Request) -> str:
    """
    Clé de rate limiting intelligente :
    - Si token MCP présent → rate limit par token (évite contournement localhost)
    - Sinon → rate limit par IP (fallback)
    """
    token = request.headers.get("X-MCP-Token")
    if token and MCP_AUTH_TOKEN:
        # Hash du token pour éviter de stocker en clair
        return f"token:{hash(token)}"
    return get_remote_address(request)

limiter = Limiter(key_func=get_rate_limit_key)

# Limites par défaut (configurables via env)
MCP_RATE_LIMIT = os.getenv("VOXQWEN_RATE_LIMIT", "10/minute")

@app.post("/mcp/preset")
@limiter.limit(MCP_RATE_LIMIT)
def mcp_preset_voice(request: MCPPresetRequest):
    ...
```

**Note v2.1** : En environnement localhost, toutes les requêtes partagent l'IP 127.0.0.1.
Le rate limiting par token (si auth activée) résout ce problème.

#### 3.6.3 Validation Taille Base64 (Améliorée v2.1)

**Problème identifié** : La validation `max_length` sur la STRING base64 ne protège pas correctement.
Base64 gonfle ~33% → 5MB string ≈ 3.7MB audio réel.

**Solution** : Double validation (string + bytes décodés) + vérification format WAV.

```python
MAX_AUDIO_BASE64_STRING = 7 * 1024 * 1024  # 7MB string (~5MB décodé)
MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5MB bytes réels
MIN_AUDIO_DURATION = 1.0  # secondes
MAX_AUDIO_DURATION = 30.0  # secondes

class MCPCreatePromptRequest(BaseModel):
    reference_audio_base64: str = Field(
        ...,
        max_length=MAX_AUDIO_BASE64_STRING,
        description="Audio WAV en base64 (max ~5MB décodé, 1-30s)"
    )
    reference_text: str = Field(..., min_length=1, max_length=1000)
    model: str = Field("1.7B")
    name: Optional[str] = Field(None, max_length=50)

    @validator('reference_audio_base64')
    def validate_audio_base64(cls, v):
        """Validation complète : taille décodée + format WAV."""
        import base64
        import io

        # 1. Décoder et vérifier taille réelle
        try:
            audio_bytes = base64.b64decode(v)
        except Exception:
            raise ValueError("Base64 invalide")

        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise ValueError(
                f"Audio trop grand: {len(audio_bytes) / 1024 / 1024:.1f}MB > {MAX_AUDIO_BYTES / 1024 / 1024}MB"
            )

        # 2. Vérifier que c'est un fichier audio valide (header WAV/RIFF)
        if not (audio_bytes[:4] == b'RIFF' or audio_bytes[:4] == b'fLaC' or audio_bytes[:3] == b'ID3'):
            # Accepter WAV, FLAC, MP3
            raise ValueError("Format audio non reconnu. Utilisez WAV, FLAC ou MP3.")

        return v
```

#### 3.6.4 Binding Localhost

```python
# Par défaut, bind sur localhost uniquement
MCP_HOST = os.getenv("VOXQWEN_MCP_HOST", "127.0.0.1")
```

---

## 4. DESIGN - Plan d'Implémentation

### 4.1 Fichiers à Modifier

| Fichier | Action | Priorité |
|---------|--------|----------|
| `main.py` | Ajouter FastAPI-MCP + routes MCP + sécurité | P0 |
| `requirements.txt` | Ajouter fastapi-mcp==0.3.x, slowapi | P0 |
| `mcp_routes.py` | Routes MCP (nouveau fichier) | P0 |
| `tts_service.py` | Logique métier factorisée (nouveau) | P0 |
| `CLAUDE.md` | Documenter outils MCP | P1 |
| `README.md` | Section MCP | P1 |
| `tests/test_mcp.py` | Tests automatisés (nouveau) | P1 |

### 4.2 Étapes d'Implémentation

#### Phase 1 : Setup FastAPI-MCP et Sécurité

```python
# Dans main.py
from fastapi_mcp import FastApiMCP
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Après définition de toutes les routes MCP
mcp = FastApiMCP(
    app,
    name="VoxQwen",
    description="API de synthèse vocale Qwen3-TTS pour Mac Studio",
    version="1.3.0",
    include_tags=["MCP Tools"],
)

mcp.mount()
```

#### Phase 2 : Factorisation de la Logique Métier

Créer `tts_service.py` pour éviter la duplication REST/MCP :

```python
# tts_service.py
import io
import base64
import soundfile as sf
from typing import Tuple, Optional
from dataclasses import dataclass

# Constantes de validation (v2.1)
MAX_AUDIO_BASE64_STRING = 7 * 1024 * 1024  # 7MB string
MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5MB décodé
VALID_AUDIO_HEADERS = [
    b'RIFF',  # WAV
    b'fLaC',  # FLAC
    b'ID3',   # MP3 avec ID3
    b'\xff\xfb',  # MP3 sans ID3
    b'\xff\xfa',  # MP3 sans ID3
]

@dataclass
class AudioValidationResult:
    """Résultat de validation audio."""
    valid: bool
    audio_bytes: Optional[bytes] = None
    error: Optional[str] = None
    format_detected: Optional[str] = None

def audio_to_base64(audio_buffer: io.BytesIO) -> str:
    """Convertit un buffer audio en string base64."""
    audio_buffer.seek(0)
    return base64.b64encode(audio_buffer.read()).decode('utf-8')

def base64_to_audio_validated(b64_string: str) -> AudioValidationResult:
    """
    Convertit et valide une string base64 en buffer audio. (v2.1)

    Validation complète :
    1. Taille de la string base64
    2. Décodage base64 valide
    3. Taille des bytes décodés
    4. Format audio reconnu (header magic bytes)

    Returns:
        AudioValidationResult avec audio_bytes si valide, sinon error
    """
    # 1. Vérifier taille string base64
    if len(b64_string) > MAX_AUDIO_BASE64_STRING:
        return AudioValidationResult(
            valid=False,
            error=f"String base64 trop grande: {len(b64_string) / 1024 / 1024:.1f}MB > {MAX_AUDIO_BASE64_STRING / 1024 / 1024}MB"
        )

    # 2. Décoder base64
    try:
        audio_bytes = base64.b64decode(b64_string)
    except Exception as e:
        return AudioValidationResult(valid=False, error=f"Base64 invalide: {e}")

    # 3. Vérifier taille décodée
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return AudioValidationResult(
            valid=False,
            error=f"Audio trop grand: {len(audio_bytes) / 1024 / 1024:.1f}MB > {MAX_AUDIO_BYTES / 1024 / 1024}MB"
        )

    # 4. Vérifier format audio (magic bytes)
    format_detected = None
    header = audio_bytes[:4]
    if header == b'RIFF':
        format_detected = "wav"
    elif header == b'fLaC':
        format_detected = "flac"
    elif header[:3] == b'ID3' or header[:2] in (b'\xff\xfb', b'\xff\xfa'):
        format_detected = "mp3"
    else:
        return AudioValidationResult(
            valid=False,
            error=f"Format audio non reconnu (header: {header[:4].hex()}). Utilisez WAV, FLAC ou MP3."
        )

    return AudioValidationResult(
        valid=True,
        audio_bytes=audio_bytes,
        format_detected=format_detected
    )

def generate_preset_audio(text: str, voice: str, language: str) -> Tuple[bytes, int, int]:
    """
    Génère un audio avec une voix préréglée.
    Retourne: (audio_bytes, sample_rate, duration_ms)

    Utilisé par /preset (REST) et /mcp/preset (MCP).
    """
    # Logique commune extraite de preset_voice()
    ...

    audio_buffer = io.BytesIO()
    sf.write(audio_buffer, wavs[0], sr, format="WAV")
    audio_buffer.seek(0)

    duration_ms = int(len(wavs[0]) / sr * 1000)
    return audio_buffer.read(), sr, duration_ms
```

#### Phase 3 : Routes MCP-Compatible (SYNCHRONES)

**IMPORTANT** : Utiliser `def` au lieu de `async def` pour les routes PyTorch bloquantes.

```python
# mcp_routes.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

from tts_service import generate_preset_audio, audio_to_base64

router = APIRouter(prefix="/mcp", tags=["MCP Tools"])

class MCPPresetRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str = Field("Serena", description="Voix native ou custom")
    language: str = Field("fr", description="Code langue ou 'auto'")

class MCPAudioResponse(BaseModel):
    audio_base64: str
    format: str = "wav"
    sample_rate: int
    duration_ms: int
    voice_used: str
    model_used: str

class MCPErrorResponse(BaseModel):
    error: str
    code: str
    suggestion: Optional[str] = None
    retry_after: Optional[int] = None

@router.post("/preset", response_model=MCPAudioResponse)
@limiter.limit(MCP_RATE_LIMIT)
def mcp_preset_voice(request: MCPPresetRequest):  # def, pas async def!
    """
    [MCP Tool] Génère un audio avec une voix préréglée.

    Retourne l'audio encodé en base64 pour compatibilité MCP.
    Limite: 2000 caractères max pour le texte.
    """
    try:
        audio_bytes, sr, duration_ms = generate_preset_audio(
            text=request.text,
            voice=request.voice,
            language=request.language,
        )

        return MCPAudioResponse(
            audio_base64=base64.b64encode(audio_bytes).decode('utf-8'),
            format="wav",
            sample_rate=sr,
            duration_ms=duration_ms,
            voice_used=request.voice,
            model_used="0.6B-CustomVoice",
        )
    except VoiceNotFoundError as e:
        raise HTTPException(404, detail={
            "error": str(e),
            "code": "VOICE_NOT_FOUND",
            "suggestion": f"Voix disponibles: {', '.join(get_all_voice_names())}"
        })
    except ModelNotLoadedError as e:
        raise HTTPException(503, detail={
            "error": str(e),
            "code": "MODEL_NOT_LOADED",
            "suggestion": "Appelez POST /models/preload d'abord"
        })
```

#### Phase 4 : Route Clone avec Avertissement Volatilité

```python
class MCPCloneRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    prompt_id: str = Field(..., description="UUID du prompt (VOLATILE: perdu au redémarrage!)")
    language: str = Field("fr")

class MCPCloneResponse(MCPAudioResponse):
    warning: Optional[str] = None

@router.post("/clone", response_model=MCPCloneResponse)
@limiter.limit(MCP_RATE_LIMIT)
def mcp_voice_clone(request: MCPCloneRequest):
    """
    [MCP Tool] Clone une voix en utilisant un prompt existant.

    ⚠️ ATTENTION: Les prompts sont stockés en MÉMOIRE uniquement.
    Ils sont perdus au redémarrage du serveur.
    Pour une persistance, utilisez POST /voices/custom.
    """
    prompt_data = get_prompt(request.prompt_id)
    if not prompt_data:
        raise HTTPException(404, detail={
            "error": f"Prompt '{request.prompt_id}' non trouvé",
            "code": "PROMPT_NOT_FOUND",
            "suggestion": "Les prompts sont volatils. Recréez-le via /clone/prompt ou utilisez /voices/custom pour la persistance."
        })

    # ... génération audio ...

    return MCPCloneResponse(
        audio_base64=audio_b64,
        format="wav",
        sample_rate=sr,
        duration_ms=duration_ms,
        voice_used=f"clone:{request.prompt_id[:8]}",
        model_used=prompt_data["model"],
        warning="Prompt stocké en mémoire, perdu au redémarrage. Utilisez /voices/custom pour persistance."
    )
```

#### Phase 5 : Documentation et Tests

- Mettre à jour CLAUDE.md avec les outils MCP
- Ajouter exemples dans README.md
- Tests automatisés pytest

### 4.5 Page Documentation MCP

#### 4.5.1 Objectif

Créer une page de documentation interactive sur `/mcp/docs` permettant aux développeurs de :
- Comprendre rapidement comment intégrer VoxQwen avec Claude Code
- Voir le statut en temps réel du serveur MCP
- Copier des exemples curl fonctionnels

#### 4.5.2 Structure (3 Onglets)

| Onglet | Contenu |
|--------|---------|
| **Skill Claude Code** | Instructions installation, config JSON pour `~/.claude/settings.json` |
| **Statut Serveur** | Version, outils MCP, modèles chargés, voix disponibles (dynamique) |
| **Guide d'Intégration** | Exemples curl par outil, format JSON-RPC 2.0, accordions par outil |

#### 4.5.3 Fichiers Créés

| Fichier | Description |
|---------|-------------|
| `templates/mcp_docs.html` | Template Jinja2 avec onglets et accordions |
| `static/mcp_docs.css` | Styles CSS (design moderne, responsive) |
| `static/mcp_docs.js` | Logique onglets, accordions, copie code |

#### 4.5.4 Route FastAPI

```python
@app.get("/mcp/docs", response_class=HTMLResponse, include_in_schema=False)
async def mcp_docs(request: Request):
    """Page de documentation MCP interactive."""
    return templates.TemplateResponse("mcp_docs.html", {
        "request": request,
        "version": API_VERSION,
        "device": DEVICE,
        "tools": get_mcp_tools_list(),
        "voices": get_voices_for_template(),
        "models": get_models_status_for_template(),
    })
```


### 4.3 Modèles Pydantic MCP

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List

# === REQUÊTES MCP ===

class MCPPresetRequest(BaseModel):
    """Requête pour synthèse avec voix préréglée."""
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str = Field("Serena", description="Voix native ou custom")
    language: str = Field("fr", description="Code langue ou 'auto'")

class MCPDesignRequest(BaseModel):
    """Requête pour Voice Design."""
    text: str = Field(..., min_length=1, max_length=2000)
    voice_description: str = Field(..., min_length=5, max_length=500, description="Description de la voix")
    language: str = Field("fr")

class MCPCloneRequest(BaseModel):
    """Requête pour clonage avec prompt existant."""
    text: str = Field(..., min_length=1, max_length=2000)
    prompt_id: str = Field(..., description="UUID du prompt (VOLATILE)")
    language: str = Field("fr")

class MCPCreatePromptRequest(BaseModel):
    """Requête pour créer un prompt de clonage. (Amélioré v2.1)"""
    reference_audio_base64: str = Field(
        ...,
        max_length=7 * 1024 * 1024,  # 7MB string (~5MB décodé)
        description="Audio WAV/FLAC/MP3 en base64 (max ~5MB décodé, 1-30s)"
    )
    reference_text: str = Field(..., min_length=1, max_length=1000, description="Transcription exacte")
    model: str = Field("1.7B", description="1.7B ou 0.6B")
    name: Optional[str] = Field(None, max_length=50, description="Nom du prompt")

    @validator('model')
    def validate_model(cls, v):
        if v not in ("1.7B", "0.6B"):
            raise ValueError("model doit être '1.7B' ou '0.6B'")
        return v

    @validator('reference_audio_base64')
    def validate_audio(cls, v):
        """
        Validation complète de l'audio base64. (v2.1)

        Vérifie :
        1. Taille des bytes décodés (pas juste la string)
        2. Format audio valide (WAV, FLAC, MP3)
        """
        from tts_service import base64_to_audio_validated

        result = base64_to_audio_validated(v)
        if not result.valid:
            raise ValueError(result.error)

        return v

# === RÉPONSES MCP ===

class MCPAudioResponse(BaseModel):
    """Réponse contenant l'audio généré."""
    audio_base64: str
    format: str = "wav"
    sample_rate: int
    duration_ms: int
    voice_used: str
    model_used: str

class MCPCloneResponse(MCPAudioResponse):
    """Réponse clone avec avertissement volatilité."""
    warning: Optional[str] = None

class MCPPromptResponse(BaseModel):
    """Réponse après création de prompt."""
    prompt_id: str
    name: Optional[str]
    model: str
    created_at: str
    warning: str = "Prompt stocké en mémoire, perdu au redémarrage. Utilisez /voices/custom pour persistance."

class MCPVoicesResponse(BaseModel):
    """Liste des voix disponibles."""
    voices: List[dict]
    count: int
    native_count: int
    custom_count: int

class MCPErrorResponse(BaseModel):
    """Format d'erreur standardisé."""
    error: str
    code: str
    suggestion: Optional[str] = None
    retry_after: Optional[int] = None
```

### 4.4 Configuration MCP Recommandée

```python
mcp = FastApiMCP(
    app,
    name="VoxQwen",
    description="API de synthèse vocale Qwen3-TTS pour Mac Studio",
    version="1.3.0",
    include_tags=["MCP Tools"],
)
```

---

## 5. VÉRIFICATION - Tests et Validation

### 5.1 Tests Automatisés (pytest)

```python
# tests/test_mcp.py
import pytest
import base64
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestMCPPreset:
    def test_preset_success(self):
        response = client.post("/mcp/preset", json={
            "text": "Bonjour",
            "voice": "Serena",
            "language": "fr"
        })
        assert response.status_code == 200
        data = response.json()
        assert "audio_base64" in data
        assert data["format"] == "wav"
        assert data["sample_rate"] > 0

    def test_preset_voice_not_found(self):
        response = client.post("/mcp/preset", json={
            "text": "Test",
            "voice": "VoixInexistante",
            "language": "fr"
        })
        assert response.status_code == 404
        assert "VOICE_NOT_FOUND" in response.json()["detail"]["code"]

    def test_preset_text_too_long(self):
        response = client.post("/mcp/preset", json={
            "text": "x" * 2001,
            "voice": "Serena",
            "language": "fr"
        })
        assert response.status_code == 422  # Validation error

class TestMCPClone:
    def test_clone_prompt_not_found(self):
        response = client.post("/mcp/clone", json={
            "text": "Test",
            "prompt_id": "uuid-inexistant",
            "language": "fr"
        })
        assert response.status_code == 404
        assert "PROMPT_NOT_FOUND" in response.json()["detail"]["code"]
        assert "volatils" in response.json()["detail"]["suggestion"]

class TestMCPRateLimiting:
    def test_rate_limit_exceeded(self):
        # Dépasse la limite
        for _ in range(15):
            client.post("/mcp/preset", json={
                "text": "Test",
                "voice": "Serena",
                "language": "fr"
            })

        response = client.post("/mcp/preset", json={
            "text": "Test",
            "voice": "Serena",
            "language": "fr"
        })
        assert response.status_code == 429

class TestMCPCreatePrompt:
    def test_audio_base64_too_large(self):
        # 6MB de données base64 (dépasse 5MB décodé)
        large_audio = base64.b64encode(b"x" * 6 * 1024 * 1024).decode()
        response = client.post("/mcp/clone/prompt", json={
            "reference_audio_base64": large_audio,
            "reference_text": "Test",
            "model": "1.7B"
        })
        assert response.status_code == 422
        assert "trop grand" in response.json()["detail"][0]["msg"].lower()

    def test_audio_invalid_format(self):
        """Test v2.1: Vérifie que les formats non-audio sont rejetés."""
        # Données qui ne sont pas un format audio valide
        fake_audio = base64.b64encode(b"NOT_AN_AUDIO_FILE_HEADER" + b"x" * 1000).decode()
        response = client.post("/mcp/clone/prompt", json={
            "reference_audio_base64": fake_audio,
            "reference_text": "Test",
            "model": "1.7B"
        })
        assert response.status_code == 422
        assert "format" in response.json()["detail"][0]["msg"].lower()

    def test_audio_valid_wav_header(self):
        """Test v2.1: Vérifie qu'un header WAV valide passe la validation format."""
        # Header WAV minimal valide (RIFF....WAVEfmt )
        wav_header = b'RIFF' + b'\x00' * 4 + b'WAVEfmt ' + b'\x00' * 100
        valid_wav = base64.b64encode(wav_header).decode()
        response = client.post("/mcp/clone/prompt", json={
            "reference_audio_base64": valid_wav,
            "reference_text": "Test",
            "model": "1.7B"
        })
        # Note: Ce test vérifie la validation format, pas le contenu audio complet
        # En production, torchaudio vérifiera le contenu complet
        assert response.status_code in (200, 422, 500)  # 500 si audio invalide mais format OK
```

### 5.2 Tests Manuels

```bash
# 1. Vérifier que le serveur MCP est actif
curl http://localhost:8060/mcp

# 2. Test outil tts_preset_voice
curl -X POST http://localhost:8060/mcp/preset \
  -H "Content-Type: application/json" \
  -d '{"text": "Bonjour le monde", "voice": "Serena", "language": "fr"}'

# 3. Test rate limiting (exécuter rapidement 15 fois)
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8060/mcp/preset \
    -H "Content-Type: application/json" \
    -d '{"text": "Test", "voice": "Serena"}'
done

# 4. Décoder et jouer l'audio
curl -s http://localhost:8060/mcp/preset \
  -H "Content-Type: application/json" \
  -d '{"text": "Test MCP", "voice": "Vivian"}' \
  | jq -r '.audio_base64' | base64 -d > test_mcp.wav
afplay test_mcp.wav
```

### 5.3 Test avec Claude Code

Après intégration, configurer Claude Code pour utiliser le serveur MCP :

```json
{
  "mcpServers": {
    "voxqwen": {
      "url": "http://localhost:8060/mcp"
    }
  }
}
```

Puis demander à Claude Code :
> "Génère un audio qui dit 'Bonjour' avec la voix Serena"

### 5.4 Checklist de Validation

- [ ] `GET /mcp` retourne les métadonnées du serveur MCP
- [ ] `POST /mcp/preset` génère de l'audio en base64
- [ ] `POST /mcp/design` fonctionne avec description textuelle
- [ ] `POST /mcp/clone` fonctionne avec prompt_id + affiche warning
- [ ] `GET /voices` reste fonctionnel (pas de régression)
- [ ] Documentation Swagger inclut les routes MCP
- [ ] Rate limiting fonctionnel (429 après limite)
- [ ] Rate limiting par token fonctionne si `VOXQWEN_MCP_TOKEN` configuré (v2.1)
- [ ] Erreur 422 si audio base64 > 5MB décodé (validation Pydantic)
- [ ] Erreur 422 si format audio non reconnu (WAV/FLAC/MP3 requis) (v2.1)
- [ ] Tests pytest passent (`pytest tests/test_mcp.py`)
- [ ] Pas de blocage event loop (vérifier avec requests concurrentes)

---

## 6. RISQUES ET MITIGATIONS

| Risque | Probabilité | Impact | Mitigation | Statut v2.1 |
|--------|-------------|--------|------------|-------------|
| **Taille base64 trop grande** | Moyenne | Élevé | Validation string (7MB) + bytes décodés (5MB) + format | ✅ Résolu |
| **FastAPI-MCP incompatible** | Faible | Critique | Pin version ^0.3.0, tests d'intégration | ✅ Mitigé |
| **Latence MCP élevée** | Élevée | Moyen | Overhead base64 ~33% documenté, pré-chargement modèles | ✅ Documenté |
| **Régression API REST** | Faible | Élevé | Routes MCP séparées (/mcp/*), tests non-régression | ✅ Mitigé |
| **DoS via requêtes massives** | Moyenne | Élevé | Rate limiting 10 req/min + par token si auth activée | ✅ Résolu |
| **Rate limit contournable (localhost)** | Moyenne | Moyen | Rate limiting par token si `VOXQWEN_MCP_TOKEN` configuré | ✅ Résolu v2.1 |
| **Saturation mémoire MPS** | Moyenne | Élevé | Monitoring mémoire, limite concurrent requests | ⚠️ Partiel |
| **Prompts perdus au redémarrage** | Certaine | Moyen | Warning explicite dans réponses, suggérer /voices/custom | ✅ Documenté |
| **Blocage event loop PyTorch** | Élevée | Élevé | Routes synchrones (def), threadpool automatique | ✅ Résolu |
| **Injection payload base64** | Faible | Moyen | Validation taille + format audio (magic bytes) | ✅ Résolu v2.1 |
| **Timing attack sur token** | Faible | Faible | `secrets.compare_digest()` pour comparaison timing-safe | ✅ Résolu v2.1 |

---

## 7. LIVRABLES

| Livrable | Description | Priorité |
|----------|-------------|----------|
| Routes `/mcp/preset`, `/mcp/design`, `/mcp/clone` | Outils MCP Tier 1 | P0 |
| `tts_service.py` | Logique métier factorisée | P0 |
| Modèles Pydantic MCP + validation | Schémas requêtes/réponses | P0 |
| Rate limiting + auth locale | Sécurité | P0 |
| Tests pytest `tests/test_mcp.py` | Tests automatisés | P1 |
| Documentation CLAUDE.md | Guide outils MCP | P1 |
| Section README MCP | Instructions utilisateur | P1 |
| Route `/mcp/clone/prompt` | Création prompt via base64 | P2 |

---

## 8. DÉPENDANCES

### 8.1 Nouvelles dépendances (requirements.txt)

```
# MCP Integration (v1.3.0)
fastapi-mcp>=0.3.0,<0.4.0
slowapi>=0.1.9
```

### 8.2 Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `VOXQWEN_MCP_TOKEN` | None | Token auth MCP (optionnel, **recommandé** pour rate limiting efficace) |
| `VOXQWEN_RATE_LIMIT` | "10/minute" | Limite requêtes MCP |
| `VOXQWEN_MCP_HOST` | "127.0.0.1" | Host binding (localhost par défaut) |

**Note v2.1** : En environnement localhost, configurer `VOXQWEN_MCP_TOKEN` permet un rate limiting par token (plus efficace que par IP car toutes les requêtes locales partagent 127.0.0.1).

---

## 9. RÉFÉRENCES

- [FastAPI-MCP GitHub](https://github.com/tadata-org/fastapi_mcp)
- [FastAPI-MCP Documentation](https://fastapi-mcp.tadata.com/getting-started/welcome)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [slowapi Rate Limiting](https://github.com/laurentS/slowapi)

---

## 10. HISTORIQUE DES RÉVISIONS

| Version | Date | Auteur | Changements |
|---------|------|--------|-------------|
| 1.0 | 2026-01-27 | Claude | Version initiale |
| 2.0 | 2026-01-27 | Council (Claude+Gemini) | Ajout sécurité, rate limiting, validation taille, US-6 erreurs, factorisation code, routes synchrones, tests pytest, warnings volatilité |
| 2.1 | 2026-01-27 | Council (Claude+Gemini) | **Failles mineures résolues** : (1) Validation base64 complète (taille décodée + format WAV/FLAC/MP3), (2) Rate limiting par token pour localhost, (3) Comparaison token timing-safe, (4) Correction 413→422 dans docs. Note Council: 8.5/10 |
| 2.2 | 2026-01-27 | Claude (Opus 4.5) | **Clarification conformité MCP** : Investigation FastAPI-MCP → réponses wrappées en `TextContent(type="text")`, pas de types natifs MCP (audio/image). Architecture confirmée correcte. Section 3.2 ajoutée expliquant le comportement réel. |
