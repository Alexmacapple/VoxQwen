# FastAPI-MCP : Transformez vos endpoints en outils pour agents IA

## Concept

FastAPI-MCP est une bibliothèque open source développée par @makhlevich qui permet de convertir automatiquement les endpoints d'une application FastAPI en outils compatibles MCP (Model Context Protocol), utilisables par des agents IA.

## Avantages clés

**Intégration native** : Fonctionne directement avec le système d'authentification FastAPI existant.

**Configuration minimale** : Aucun paramétrage requis, opérationnel immédiatement après installation.

**Préservation du code existant** : Les modèles, réponses et documentation restent intacts.

**Performance** : Fonctionne en ASGI pur, peut être monté sur une app existante ou exécuté en standalone.

## Implémentation

```python
# pip install fastapi-mcp
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

app = FastAPI()
mcp = FastApiMCP(app)
mcp.mount()
```

Trois lignes suffisent pour exposer tous les endpoints comme outils MCP.

## Ressources

- **Dépôt GitHub** : https://github.com/tadata-org/fastapi_mcp
- **Documentation** : https://fastapi-mcp.tadata.com/getting-started/welcome