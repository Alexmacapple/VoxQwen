# PRD-005 — Observabilite et qualite

**Version** : v2.0
**Date** : 2026-03-20
**Statut** : A faire
**Priorite** : Haute
**Effort estime** : 6 heures

---

## Contexte

VoxQwen a un logger minimal (5 appels `logger.xxx()` dans 2876 lignes, tous dans `with_generation_lock()`), pas de persistance des logs, aucun test sur les routes REST (seulement 11 tests MCP sur serveur live), et des dependances non pinnees.

### Dependance

- PRD-004 phase 1.1 (print → logger) doit etre fait **avant** ce PRD
- Les phases de ce PRD sont independantes entre elles

### Etat actuel verifie

**Logging** : Logger `voxqwen` configure (ligne 111-112) mais sans handler — les logs vont sur stderr par defaut. Uvicorn logue les requetes HTTP sur stdout par defaut (access log).

**Tests existants** : 2 fichiers dans `Test/` :
- `test_mcp_integration.py` (7 tests) : connect a un serveur LIVE via `urllib` (port 8060)
- `test_mcp_audio.py` (4 tests) : idem, validation WAV structure (RIFF, WAVE, channels)
- **Aucun test REST** sur /preset, /design, /clone, /batch, /voices

**Import de main.py** : `from main import app` fonctionne SANS charger les modeles GPU. Tous les imports `qwen_tts` sont lazy (dans les fonctions `load_*_model()`). Side effects a l'import : creation dossiers, creation app FastAPI, mount static — tous acceptables pour les tests.

---

## Phase 1 — Logging production (~2h)

### 1.1 Setup logging structure

**Probleme** : Logger sans handler. Aucun fichier persiste. Apres restart, zero trace des erreurs precedentes.

**Solution** :

```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging():
    """Configure le logging pour la production."""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Format JSON pour les fichiers (parseable par outils monitoring)
    json_formatter = logging.Formatter(
        '{"ts":"%(asctime)s","level":"%(levelname)s",'
        '"logger":"%(name)s","msg":"%(message)s"}'
    )

    # Format lisible pour la console (dev)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s %(message)s"
    )

    # Fichier avec rotation (10 Mo, 5 backups = 50 Mo max)
    file_handler = RotatingFileHandler(
        log_dir / "voxqwen.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(logging.INFO)

    # Console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)

    # Logger voxqwen
    voxqwen_logger = logging.getLogger("voxqwen")
    voxqwen_logger.setLevel(logging.INFO)
    voxqwen_logger.addHandler(file_handler)
    voxqwen_logger.addHandler(console_handler)

    # Reduire le bruit des bibliotheques tierces
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return voxqwen_logger
```

Appeler `setup_logging()` au debut du module, en remplacement des lignes 111-112.

**Ajouter `logs/`** au `.gitignore`.

**Criteres de validation** :
- [ ] `logs/voxqwen.log` cree au demarrage
- [ ] Chaque ligne du fichier est du JSON valide
- [ ] Apres restart, les logs precedents sont dans le fichier
- [ ] Console garde le format lisible
- [ ] Les logs uvicorn access ne polluent pas le fichier

---

### 1.2 Couverture des logs aux points critiques

**Probleme** : 5 appels logger dans 2876 lignes (apres PRD-004 phase 1.1 qui convertit les print). Les routes principales ne sont pas loggees.

**Points a logger** (apres PRD-004 qui a deja converti les print des chargements modeles) :

| Point | Niveau | Contenu | Ou ajouter |
|-------|--------|---------|------------|
| Requete TTS recue | INFO | endpoint, voice/instruct, text_length | Debut de chaque route /preset, /design, /clone |
| Upload audio recu | INFO | filename, size_bytes | /clone, /clone/prompt, /voices/custom |
| Voix custom creee | INFO | name, source (design/clone) | /voices/custom POST |
| Voix custom supprimee | WARNING | name | DELETE /voices/custom |
| Prompt clone cree | INFO | prompt_id, model | /clone/prompt POST |
| Batch demarre | INFO | endpoint, nb_textes, timeout | /batch/* |
| Erreur generation | ERROR | endpoint, exception, traceback | catch dans chaque route |
| Rate limit atteint | WARNING | (automatique via slowapi handler) | — |

**Estimation** : ~15 lignes `logger.xxx()` a ajouter.

**Attention doublon access log** : Uvicorn logue deja chaque requete HTTP sur stdout (`INFO: 127.0.0.1 - "POST /preset HTTP/1.1" 200`). Les logs "requete TTS recue" ajoutes en 1.2 sont **complementaires** (ils contiennent voice, text_length, parametres metier que l'access log n'a pas). Pour eviter la confusion :
- Les logs metier utilisent le logger `voxqwen` (fichier `logs/voxqwen.log`)
- Les access logs uvicorn restent sur stdout (reduit a WARNING dans `setup_logging()`)
- Resultat : le fichier log contient uniquement les evenements metier, pas le bruit HTTP

**Criteres de validation** :
- [ ] Un `POST /preset` genere un log INFO au debut (voice, text_length) dans `voxqwen.log`
- [ ] with_generation_lock logue deja debut/fin (existant) → pas de doublon
- [ ] Les access logs uvicorn ne sont PAS dans `voxqwen.log` (seulement stdout)
- [ ] Une erreur genere un log ERROR avec le message d'exception
- [ ] Un batch de 10 textes logue "batch demarre, 10 textes, timeout=660s"

---

## Phase 2 — Tests routes REST (~3h)

### 2.1 Architecture de tests

**Choix technique** : Tests pytest avec `httpx.AsyncClient` en mode ASGI (in-process). Pas de serveur live requis.

**Pourquoi pas le pattern des tests existants** : Les tests MCP actuels (`Test/test_mcp_*.py`) se connectent a un serveur LIVE sur port 8060 via `urllib`. C'est un test d'integration end-to-end qui necessite le serveur + les modeles GPU charges. Impossible a executer en CI ou sans GPU.

**Approche** : Mocker les fonctions de chargement de modeles pour eviter le GPU, tester uniquement la logique FastAPI (validation, routing, reponses).

**Ce qu'on ne mocke PAS** : Les fonctions de validation (`validate_voice_name`, `resolve_language`), les schemas Pydantic, les helpers de reponse.

**Ce qu'on mocke** : `load_voice_design_model()`, `load_preset_voice_model()`, `load_clone_base_model()`, `model.generate()`, `model.create_voice_clone_prompt()`.

### 2.2 Configuration pytest

**Fichier** : `Test/pytest.ini`

```ini
[pytest]
asyncio_mode = auto
timeout = 30
testpaths = .
python_files = test_*.py
```

**Fichier** : `Test/conftest.py`

```python
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client():
    """Client HTTP in-process (pas de serveur live)."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

**Note** : `from main import app` est safe — tous les imports `qwen_tts` sont lazy. Les side effects (creation dossiers, creation app) sont acceptables en tests.

**Note** : `load_custom_voices()` n'est PAS appele a l'import (seulement dans `__main__` ou la lifespan). Les tests verront `custom_voices = {}`. C'est le comportement souhaite pour les tests unitaires.

### 2.3 Tests a implementer

**Fichier** : `Test/test_rest_endpoints.py`

```python
# Squelette — ~30 tests

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# --- Health & Info ---

async def test_health_check(client):
    """GET / retourne status ok avec device et version."""
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "device" in data

async def test_languages(client):
    """GET /languages retourne 10 langues."""
    r = await client.get("/languages")
    assert r.status_code == 200
    assert len(r.json()["languages"]) == 10

async def test_voices_list(client):
    """GET /voices retourne les 9 voix natives."""
    r = await client.get("/voices")
    assert r.status_code == 200
    data = r.json()
    assert len(data["native_voices"]) == 9

async def test_models_status(client):
    """GET /models/status retourne les etats de chargement."""
    r = await client.get("/models/status")
    assert r.status_code == 200
    data = r.json()
    assert "voice_design_loaded" in data
    assert data["voice_design_loaded"] is False  # Pas charge en test

async def test_generation_status(client):
    """GET /generation/status retourne les stats."""
    r = await client.get("/generation/status")
    assert r.status_code == 200
    data = r.json()
    assert data["busy"] is False
    assert "stats" in data

# --- Validation input ---

async def test_design_text_too_long(client):
    """POST /design refuse texte > 10000 chars."""
    r = await client.post("/design", json={
        "text": "x" * 10001,
        "voice_instruct": "voix grave",
        "language": "fr",
    })
    assert r.status_code == 422

async def test_design_missing_voice_instruct(client):
    """POST /design refuse sans voice_instruct."""
    r = await client.post("/design", json={
        "text": "Bonjour",
        "language": "fr",
    })
    assert r.status_code == 422

async def test_preset_invalid_voice(client):
    """POST /preset avec voix inexistante."""
    r = await client.post("/preset", data={
        "text": "Test",
        "voice": "voix_qui_nexiste_pas_xyz",
        "language": "fr",
    })
    assert r.status_code in [400, 404]

async def test_batch_too_many_texts(client):
    """POST /batch/preset refuse > 100 textes."""
    r = await client.post("/batch/preset", json={
        "texts": ["t"] * 101,
        "voice": "Serena",
    })
    assert r.status_code == 422

# --- Voix custom validation ---

async def test_custom_voice_name_too_short(client):
    """POST /voices/custom refuse nom < 3 chars."""
    r = await client.post("/voices/custom", data={
        "name": "ab",
        "source": "design",
        "voice_description": "test",
    })
    assert r.status_code == 400

async def test_custom_voice_reserved_name(client):
    """POST /voices/custom refuse noms reserves (voix natives)."""
    r = await client.post("/voices/custom", data={
        "name": "Serena",
        "source": "design",
        "voice_description": "test",
    })
    assert r.status_code == 400

async def test_custom_voice_invalid_chars(client):
    """POST /voices/custom refuse caracteres speciaux."""
    r = await client.post("/voices/custom", data={
        "name": "../hack",
        "source": "design",
        "voice_description": "test",
    })
    assert r.status_code == 400

async def test_custom_voice_not_found(client):
    """GET /voices/custom/{name} retourne 404 pour voix inexistante."""
    r = await client.get("/voices/custom/voix-inexistante-xyz")
    assert r.status_code == 404

# --- Clone prompts ---

async def test_list_prompts_empty(client):
    """GET /clone/prompts retourne liste vide."""
    r = await client.get("/clone/prompts")
    assert r.status_code == 200
    assert r.json()["prompts"] == []

async def test_delete_prompt_not_found(client):
    """DELETE /clone/prompts/{id} retourne 404 pour id inexistant."""
    r = await client.delete("/clone/prompts/inexistant-xyz")
    assert r.status_code == 404

# --- Tokenizer ---

async def test_tokenizer_encode_empty(client):
    """POST /tokenizer/encode refuse texte vide."""
    r = await client.post("/tokenizer/encode", json={"text": ""})
    assert r.status_code in [400, 422]

# ... (~15 tests supplementaires pour couvrir les cas d'erreur)
```

**Tests qui necessitent un mock TTS** (generation reelle) :

Le mock doit simuler le flux complet : chargement modele → generation → StreamingResponse WAV.

```python
import io
import struct

def _make_fake_wav(duration_ms=100, sample_rate=24000) -> bytes:
    """Genere un WAV valide minimal pour les tests."""
    num_samples = int(sample_rate * duration_ms / 1000)
    data_size = num_samples * 2  # 16 bits = 2 bytes
    buf = io.BytesIO()
    # RIFF header
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    # fmt chunk
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    # data chunk
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(b"\x00" * data_size)
    return buf.getvalue()


@patch("main.with_generation_lock")
async def test_preset_success(mock_lock, client):
    """POST /preset avec mock TTS retourne un WAV valide."""
    # with_generation_lock retourne les bytes WAV directement
    fake_wav = _make_fake_wav()
    mock_lock.return_value = fake_wav

    r = await client.post("/preset", data={
        "text": "Bonjour",
        "voice": "Serena",
        "language": "fr",
    })
    # La route retourne une StreamingResponse — le mock court-circuite
    # On verifie au minimum que la route ne crash pas avec un mock
    assert r.status_code in [200, 500]  # 500 si le mock ne simule pas assez


@patch("main.with_generation_lock")
async def test_design_success(mock_lock, client):
    """POST /design avec mock TTS."""
    mock_lock.return_value = _make_fake_wav()
    r = await client.post("/design", json={
        "text": "Bonjour",
        "voice_instruct": "Voix grave masculine",
        "language": "fr",
    })
    assert r.status_code in [200, 500]
```

**Note realiste** : Les mocks de `with_generation_lock` ne simulent pas parfaitement le flux car les routes construisent un `StreamingResponse` apres le lock. Il peut etre necessaire de mocker a un niveau plus bas (`model.generate`) ou d'accepter que certains tests de succes ne soient verifiables qu'en integration (serveur live). L'objectif principal des tests unitaires est de couvrir la **validation des inputs** et les **cas d'erreur**, pas la generation audio complete.

**Tests rate limiting** (apres PRD-004 phase 3) :

```python
async def test_rate_limiting_preset(client):
    """POST /preset retourne 429 apres depassement du rate limit."""
    # Envoyer 12 requetes rapides (limite = 10/min)
    responses = []
    for _ in range(12):
        r = await client.post("/preset", data={
            "text": "Test", "voice": "Serena", "language": "fr",
        })
        responses.append(r.status_code)
    # Au moins une reponse 429
    assert 429 in responses
    # Verifier format JSON du 429
    last_429 = [r for r in responses if r == 429]
    assert len(last_429) > 0
```

**Tests lifespan** (startup/shutdown PRD-004 phase 2) :

```python
from main import app
from httpx import AsyncClient, ASGITransport

async def test_lifespan_loads_custom_voices():
    """La lifespan charge les voix custom au demarrage."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Le lifespan s'execute a l'entree du context manager
        r = await client.get("/models/status")
        assert r.status_code == 200
        # custom_voices_count peut etre 0 (pas de voix sur disque en test)
        assert "custom_voices_count" in r.json()
```

**Estimation** : ~35 tests au total (info, validation, mock TTS, rate limit, lifespan).

### 2.5 Cohabitation avec les tests MCP existants

**Etat actuel** : `Test/test_mcp_integration.py` (7 tests) et `Test/test_mcp_audio.py` (4 tests) se connectent a un serveur **live** sur port 8060 via `urllib`. Ils necessitent le serveur demarre + modeles GPU charges.

**Decision** : Les **garder tels quels** comme tests d'integration end-to-end. Ils ne sont pas executables en CI mais valident le comportement reel avec GPU. Les nouveaux tests pytest (REST) sont complementaires : ils valident la logique FastAPI sans GPU.

**Structure finale** :

```
Test/
├── pytest.ini                    # Config pytest (ignore test_mcp_*)
├── conftest.py                   # Fixture client async
├── requirements-test.txt         # Dependencies pytest
├── test_rest_endpoints.py        # ~35 tests pytest (NOUVEAU, sans GPU)
├── test_mcp_integration.py       # 7 tests urllib (EXISTANT, serveur live)
├── test_mcp_audio.py             # 4 tests urllib (EXISTANT, serveur live)
├── test_mcp_endpoints.sh         # Script bash (EXISTANT)
└── run_tests.sh                  # Script bash (EXISTANT)
```

**Dans `pytest.ini`**, exclure les tests MCP (ils ne fonctionnent pas sans serveur live) :

```ini
[pytest]
asyncio_mode = auto
timeout = 30
testpaths = .
python_files = test_rest_*.py
```

Le `python_files = test_rest_*.py` limite pytest aux nouveaux tests. Les tests MCP restent executables manuellement : `python Test/test_mcp_integration.py` (avec serveur demarre).

**Criteres de validation** :
- [ ] `cd VoxQwen && python -m pytest Test/ -v` passe (~35 tests, < 30s)
- [ ] Tests executables sans GPU (modeles mockes)
- [ ] Les tests MCP existants ne sont pas casses (executables manuellement)
- [ ] Couverture : validation inputs, erreurs 4xx, routes info, rate limit, lifespan

---

### 2.4 Dependencies de test

**Fichier** : `Test/requirements-test.txt`

```
pytest>=8.0
pytest-asyncio>=0.23
pytest-timeout>=2.3
httpx>=0.27
```

Installation : `pip install -r Test/requirements-test.txt`

---

## Phase 3 — Dependances (~30 min)

### 3.1 Lock file

**Probleme** : `requirements.txt` utilise `>=` partout. Risque : `torch` change de format d'embedding dans une mise a jour → les voix custom ne se chargent plus.

**Solution** :

```bash
cd VoxQwen
source venv/bin/activate
pip freeze > requirements-lock.txt
```

Commiter `requirements-lock.txt`. Garder `requirements.txt` comme source de verite (versions minimales). En production :

```bash
pip install -r requirements-lock.txt  # Versions exactes
```

**Documenter dans README** :
- `requirements.txt` = versions minimales (pour developper)
- `requirements-lock.txt` = versions exactes (pour deployer)

**Criteres de validation** :
- [ ] `requirements-lock.txt` genere et commite
- [ ] `pip install -r requirements-lock.txt` dans un venv vierge fonctionne
- [ ] README documente la difference

---

## Phase 4 — Endpoint /health (~30 min)

### 4.1 Endpoint /health

**Probleme** : `GET /` (ligne 831) retourne `status: "ok"` avec device et noms de modeles, mais ne dit pas si les modeles sont charges, si le GPU est accessible, ni si les voix custom sont lisibles. Pas utilisable comme probe de sante.

**GET /models/status** (ligne 1674) est plus riche (modeles charges, prompts, voix) mais n'a pas de code 503 en cas de probleme.

**Solution** : Endpoint `/health` qui retourne 200 ou 503.

```python
@app.get("/health", tags=["Monitoring"], include_in_schema=False)
async def health_probe():
    """Probe de sante pour monitoring/load balancer."""
    healthy = True
    checks = {}

    # GPU accessible ?
    try:
        if DEVICE == "mps":
            if hasattr(torch.mps, "current_allocated_memory"):
                _ = torch.mps.current_allocated_memory()
            checks["gpu"] = "ok"
        elif DEVICE.startswith("cuda"):
            _ = torch.cuda.memory_allocated()
            checks["gpu"] = "ok"
        else:
            checks["gpu"] = "cpu"
    except Exception:
        checks["gpu"] = "error"
        healthy = False

    # Repertoire modeles existe ?
    checks["models_dir"] = "ok" if MODELS_DIR.exists() else "missing"
    if not MODELS_DIR.exists():
        healthy = False

    # Repertoire voix custom accessible ?
    checks["voices_dir"] = "ok" if CUSTOM_VOICES_DIR.exists() else "missing"

    return JSONResponse(
        content={
            "status": "healthy" if healthy else "unhealthy",
            "version": API_VERSION,
            "device": DEVICE,
            "checks": checks,
        },
        status_code=200 if healthy else 503,
    )
```

**Criteres de validation** :
- [ ] `GET /health` retourne 200 et `status: "healthy"` en fonctionnement normal
- [ ] `GET /health` retourne 503 si GPU inaccessible ou models_dir manquant
- [ ] Utilisable comme liveness probe (pas d'auth, pas de rate limit)

---

## Fichiers modifies

| Fichier | Phase | Modification |
|---------|-------|-------------|
| `main.py` | 1.1 | `setup_logging()` remplace lignes 111-112 |
| `main.py` | 1.2 | ~15 lignes `logger.xxx()` aux points critiques |
| `main.py` | 4.1 | Endpoint `/health` |
| `.gitignore` | 1.1 | Ajout `logs/` |

## Fichiers crees

| Fichier | Phase | Role |
|---------|-------|------|
| `Test/test_rest_endpoints.py` | 2.3 | ~30 tests REST |
| `Test/pytest.ini` | 2.2 | Config pytest |
| `Test/conftest.py` | 2.2 | Fixture client async |
| `Test/requirements-test.txt` | 2.4 | Dependencies de test |
| `requirements-lock.txt` | 3.1 | Versions exactes pinnees |

---

## Ordre d'implementation

```
Phase 1 — Logging (~2h)
  1.1 setup_logging() + rotation fichier ......... 1h
  1.2 ~15 lignes logger aux points critiques ..... 1h

Phase 2 — Tests (~3h)
  2.2 pytest.ini + conftest.py ................... 30 min
  2.3 ~30 tests REST endpoints ................... 2h
  2.4 requirements-test.txt ...................... 10 min
  Run + fix ..................................... 20 min

Phase 3 — Dependances (~30 min)
  3.1 pip freeze > requirements-lock.txt ......... 30 min

Phase 4 — Monitoring (~30 min)
  4.1 Endpoint /health ........................... 30 min
```

**Effort total** : ~6h

---

## Criteres de succes global

- [ ] `logs/voxqwen.log` persiste entre les restarts (JSON, rotation 50 Mo max)
- [ ] Chaque requete TTS genere un log INFO (endpoint, voice, text_length)
- [ ] `python -m pytest Test/test_rest_endpoints.py -v` passe (~30 tests, < 30s)
- [ ] Tests executables sans GPU
- [ ] `requirements-lock.txt` commite
- [ ] `GET /health` retourne 200 ou 503
- [ ] VoxStudio n'est pas impacte (aucun changement d'API)

---

## Historique

| Version | Date | Modification |
|---------|------|-------------|
| v1.0 | 2026-03-20 | Creation |
| v2.0 | 2026-03-20 | Audit connus/inconnus : verification import safe (pas de chargement GPU), pattern tests existants (urllib vs test client), correction status "ok" (pas "running"), ajout details mock strategy, note side effects import |
| v2.1 | 2026-03-20 | Evaluation : tests mock TTS detailles (fake WAV, limites du mock), tests rate limiting et lifespan, cohabitation tests MCP existants (section 2.5), note doublon access log uvicorn |
