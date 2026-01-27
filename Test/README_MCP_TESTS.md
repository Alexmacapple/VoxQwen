# Tests MCP - VoxQwen

Plan de tests pour valider l'intégration FastAPI-MCP de VoxQwen.

## Prérequis

```bash
# Serveur VoxQwen en cours d'exécution
source venv/bin/activate
python main.py
# API sur http://localhost:8060
```

## Structure des Tests

| Fichier | Description |
|---------|-------------|
| `test_mcp_endpoints.sh` | Tests bash rapides de tous les endpoints |
| `test_mcp_audio.py` | Tests Python avec validation audio |
| `test_mcp_integration.py` | Tests d'intégration complets |

## Exécution

```bash
# Tests rapides (bash)
./Test/test_mcp_endpoints.sh

# Tests complets (Python)
python Test/test_mcp_audio.py
python Test/test_mcp_integration.py
```

## Endpoints MCP Testés

### Lecture (GET)

| Endpoint | Description | Validation |
|----------|-------------|------------|
| `/mcp/languages` | Liste des langues | count=10, auto_detection=true |
| `/mcp/voices` | Liste des voix | 9 natives minimum |
| `/mcp/status` | Statut serveur | mcp_enabled=true |

### Génération (POST)

| Endpoint | Description | Validation |
|----------|-------------|------------|
| `/mcp/preset` | Voix préréglée | Audio base64 valide |
| `/mcp/design` | Voice Design | Audio base64 valide |
| `/mcp/preset/instruct` | Voix + émotions | Audio base64 valide |
| `/mcp/clone/prompt` | Créer prompt | prompt_id retourné |
| `/mcp/clone` | Clonage vocal | Audio base64 valide |

### Protocole MCP (SSE)

| Endpoint | Description | Validation |
|----------|-------------|------------|
| `/mcp` | SSE principal | Retourne session_id |

## Critères de Succès

- [ ] Tous les endpoints GET retournent HTTP 200
- [ ] Tous les endpoints POST retournent audio_base64 valide
- [ ] Audio décodable en WAV valide (header RIFF)
- [ ] Sample rate = 24000 Hz
- [ ] Endpoint SSE retourne session_id
- [ ] Rate limiting fonctionne (429 après 10 req/min)
