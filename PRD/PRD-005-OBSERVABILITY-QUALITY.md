# PRD-005 — Observabilite et qualite

**Version** : v1.0
**Date** : 2026-03-20
**Statut** : A faire
**Priorite** : Haute
**Effort estime** : 1 jour

---

## Contexte

VoxQwen a un logger minimal (2 lignes de setup, 6 appels dans tout le code), pas de persistance des logs, aucun test sur les routes REST (seulement MCP), et des dependances non pinnees. Ce PRD couvre l'**observabilite** (savoir ce qui se passe en production) et la **qualite** (avoir confiance dans les changements).

### Dependance

Ce PRD peut etre implemente en parallele du PRD-004 (Production Safety). Les deux sont independants, sauf que PRD-004 phase 5.1 (print → logger) doit etre fait avant le logging structure de ce PRD.

---

## Phase 1 — Logging production (~2h)

### 1.1 Setup logging structure

**Probleme** : `main.py:111-112` configure un logger basique sans handler, sans formatter, sans fichier. Tout va sur stdout. Apres un restart, aucune trace des erreurs precedentes.

**Solution** :

```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging():
    """Configure le logging pour la production."""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Format JSON pour les fichiers (parseable)
    json_formatter = logging.Formatter(
        '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    )

    # Format lisible pour la console
    console_formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s %(message)s"
    )

    # Fichier avec rotation (10 Mo, 5 fichiers max = 50 Mo)
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

    # Logger racine voxqwen
    logger = logging.getLogger("voxqwen")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Reduire le bruit des bibliotheques
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger
```

Appeler `setup_logging()` au tout debut du module (avant toute autre initialisation).

**Ajouter** `logs/` au `.gitignore` de VoxQwen.

**Fichier** : `main.py` lignes 111-112 (remplacer)

**Criteres de validation** :
- [ ] `logs/voxqwen.log` cree au demarrage
- [ ] Chaque ligne du fichier est du JSON valide
- [ ] Rotation a 10 Mo (verifiable avec un test de charge)
- [ ] Console garde le format lisible
- [ ] Apres restart, les logs precedents sont toujours dans le fichier

---

### 1.2 Couverture des logs

**Probleme** : 6 appels logger dans 2876 lignes. Les routes principales, les chargements de modeles et les erreurs ne sont pas logges.

**Solution** : Ajouter des logs aux points critiques.

| Point | Niveau | Message | Ligne actuelle |
|-------|--------|---------|----------------|
| Demarrage serveur | INFO | Version, device, voix | 2842 (print) |
| Chargement modele | INFO | Nom, duree, VRAM | 447-541 (print) |
| Erreur chargement modele | ERROR | Nom, exception | 460 (absent) |
| Requete TTS recue | INFO | Endpoint, voice, text length | routes /preset, /design, /clone |
| Requete TTS terminee | INFO | Endpoint, duree | Deja dans with_generation_lock |
| Upload audio | INFO | Filename, size, duration | /clone, /voices/custom |
| Creation voix custom | INFO | Nom, source | /voices/custom |
| Suppression voix | WARNING | Nom | DELETE /voices/custom |
| Erreur generation | ERROR | Endpoint, exception | routes /preset, /design, /clone |
| Rate limit | WARNING | IP, endpoint | Automatique par slowapi |
| Startup complet | INFO | Duree total startup | Fin lifespan startup |

**Estimation** : ~15 lignes `logger.xxx()` a ajouter dans le code existant.

**Criteres de validation** :
- [ ] Un appel `POST /preset` genere 2 lignes de log (debut + fin)
- [ ] Un chargement de modele genere un log avec duree
- [ ] Une erreur generation genere un log ERROR avec traceback
- [ ] Les logs sont lisibles et utiles pour le debug

---

## Phase 2 — Tests routes REST (~3h)

### 2.1 Tests d'integration REST

**Probleme** : Les seuls tests existants (`Test/test_mcp_integration.py`, `test_mcp_audio.py`) couvrent les routes MCP. Les 21 routes REST principales n'ont aucun test.

**Solution** : Creer un fichier de tests pytest couvrant les routes critiques.

**Fichier** : `Test/test_rest_endpoints.py`

**Routes a tester** (priorite GPU = le plus risque) :

| Route | Tests | Mock |
|-------|-------|------|
| `GET /` | Status, device, version | Non |
| `GET /languages` | Liste 10 langues | Non |
| `GET /voices` | Voix natives + custom | Non |
| `GET /models/status` | Modeles charges | Non |
| `GET /generation/status` | Stats generation | Non |
| `POST /preset` | Succes, voix invalide, texte vide | Mock TTS |
| `POST /preset/instruct` | Succes, instruct vide | Mock TTS |
| `POST /design` | Succes, texte > 10000 chars | Mock TTS |
| `POST /clone` | Audio manquant, format invalide | Mock TTS |
| `POST /voices/custom` | Nom invalide, nom reserve, succes | Mock TTS |
| `GET /voices/custom/{name}` | Existant, inexistant | Non |
| `DELETE /voices/custom/{name}` | Existant, inexistant | Non |
| `POST /batch/preset` | > 100 textes, textes vides | Mock TTS |
| Rate limiting | 429 apres N appels | Non |

**Approche** : Utiliser `httpx.AsyncClient` avec `app=app` (test in-process, pas de serveur). Mocker les appels `model.generate()` pour eviter de charger les modeles 18 Go pendant les tests.

```python
# Test/test_rest_endpoints.py (squelette)
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

# Import de l'app sans charger les modeles
import sys
sys.modules['qwen_tts'] = MagicMock()

from main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_health_check(client):
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "running"
    assert "device" in data

@pytest.mark.asyncio
async def test_voices_list(client):
    r = await client.get("/voices")
    assert r.status_code == 200
    data = r.json()
    assert len(data["native_voices"]) == 9

@pytest.mark.asyncio
async def test_preset_invalid_voice(client):
    r = await client.post("/preset", data={
        "text": "Test",
        "voice": "voix_inexistante",
        "language": "fr"
    })
    assert r.status_code in [400, 404]

# ... etc.
```

**Estimation** : ~30 tests couvrant les cas de succes, d'erreur et de validation.

**Criteres de validation** :
- [ ] `pytest Test/test_rest_endpoints.py -v` passe sans erreur
- [ ] Les tests tournent sans GPU (modeles mockes)
- [ ] Couverture des routes critiques : /preset, /design, /clone, /voices/custom
- [ ] Au moins 1 test de rate limiting
- [ ] Temps d'execution < 30s (pas de generation reelle)

---

### 2.2 Configuration pytest

**Probleme** : Pas de `pytest.ini` ni de `conftest.py` dans VoxQwen. Les tests existants sont des scripts standalone (urllib).

**Solution** : Ajouter la config pytest.

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

# Desactiver le chargement automatique des modeles dans les tests
@pytest.fixture(autouse=True)
def no_model_loading(monkeypatch):
    """Empeche le chargement des modeles GPU pendant les tests."""
    monkeypatch.setattr("main.voice_design_model", None)
    monkeypatch.setattr("main.voice_clone_model", None)
    monkeypatch.setattr("main.preset_voice_model", None)
```

**Ajouter** dans `requirements.txt` (ou un `requirements-test.txt` dedie) :

```
pytest>=8.0
pytest-asyncio>=0.23
pytest-timeout>=2.3
httpx>=0.27
```

---

## Phase 3 — Dependances (~30 min)

### 3.1 Lock file

**Probleme** : `requirements.txt` utilise `>=` partout. Un `pip install` dans 6 mois peut installer des versions incompatibles. Risque particulier : `langgraph` ou `torch` change de format d'embedding → les voix custom ne se chargent plus.

**Solution** : Generer un lock file.

```bash
cd VoxQwen
source venv/bin/activate
pip freeze > requirements-lock.txt
```

Commiter `requirements-lock.txt` dans git. Garder `requirements.txt` comme source de verite (versions minimales). En production, installer avec le lock :

```bash
pip install -r requirements-lock.txt
```

**Criteres de validation** :
- [ ] `requirements-lock.txt` genere et commite
- [ ] `pip install -r requirements-lock.txt` dans un venv vierge fonctionne
- [ ] README documente la difference entre les deux fichiers

---

### 3.2 Suppression python-dotenv

**Statut** : Deja fait dans le commit precedent. Verifier qu'aucune regression.

---

## Phase 4 — Monitoring endpoint (~30 min)

### 4.1 Endpoint /health

**Probleme** : Pas d'endpoint `/health` standard. `GET /` retourne des infos utiles mais son nom ne suit pas les conventions de monitoring.

**Solution** : Ajouter un endpoint `/health` minimaliste pour les probes de sante.

```python
@app.get("/health", tags=["Monitoring"], include_in_schema=False)
async def health_check():
    """Probe de sante pour monitoring/load balancer."""
    healthy = True
    checks = {}

    # GPU accessible ?
    try:
        if DEVICE == "mps":
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

    # Au moins un modele chargeable ?
    checks["models_dir"] = "ok" if MODELS_DIR.exists() else "error"
    if not MODELS_DIR.exists():
        healthy = False

    # Voix custom accessibles ?
    checks["voices_dir"] = "ok" if CUSTOM_VOICES_DIR.exists() else "error"

    status_code = 200 if healthy else 503
    return JSONResponse(
        content={"status": "healthy" if healthy else "unhealthy", "checks": checks},
        status_code=status_code,
    )
```

**Criteres de validation** :
- [ ] `GET /health` retourne 200 quand tout va bien
- [ ] `GET /health` retourne 503 si GPU inaccessible
- [ ] Utilisable comme liveness probe

---

## Fichiers modifies

| Fichier | Phase | Modification |
|---------|-------|-------------|
| `main.py` | 1.1 | `setup_logging()`, remplacement logger setup |
| `main.py` | 1.2 | ~15 lignes logger ajoutees aux points critiques |
| `main.py` | 4.1 | Endpoint `/health` |
| `.gitignore` | 1.1 | Ajout `logs/` |

## Fichiers crees

| Fichier | Phase | Role |
|---------|-------|------|
| `Test/test_rest_endpoints.py` | 2.1 | ~30 tests REST |
| `Test/pytest.ini` | 2.2 | Config pytest |
| `Test/conftest.py` | 2.2 | Fixtures (mock modeles) |
| `requirements-lock.txt` | 3.1 | Versions exactes pinnees |

---

## Ordre d'implementation

```
Phase 1 — Logging (~2h)
  1.1 Setup logging structure .................. 1h
  1.2 Couverture logs aux points critiques ..... 1h

Phase 2 — Tests (~3h)
  2.1 Tests REST endpoints ..................... 2h30
  2.2 Config pytest ............................ 30 min

Phase 3 — Dependances (~30 min)
  3.1 Lock file ................................ 30 min

Phase 4 — Monitoring (~30 min)
  4.1 Endpoint /health ......................... 30 min
```

**Effort total** : ~6h

---

## Criteres de succes global

- [ ] `logs/voxqwen.log` persiste entre les restarts
- [ ] Chaque requete TTS genere 2 lignes de log (debut + fin)
- [ ] `pytest Test/ -v` passe (tests existants + nouveaux)
- [ ] ~30 tests REST couvrent les routes critiques
- [ ] `requirements-lock.txt` commite et fonctionnel
- [ ] `GET /health` retourne 200 ou 503
- [ ] Le deploiement VoxStudio n'est pas impacte (aucun changement d'API)

---

## Historique

| Version | Date | Modification |
|---------|------|-------------|
| v1.0 | 2026-03-20 | Creation (audit production du 2026-03-20) |
