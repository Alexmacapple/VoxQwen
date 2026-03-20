"""
Tests REST endpoints VoxQwen — sans GPU, sans serveur live.

Utilise httpx.AsyncClient en mode ASGI (in-process).
Les modeles ne sont PAS charges : on teste uniquement
la validation, le routing et les reponses d'erreur.
"""

import pytest


# ─── Health & Info ───────────────────────────────────────────────────────────

async def test_health_check(client):
    """GET / retourne status ok avec device et version."""
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "device" in data


async def test_health_probe(client):
    """GET /health retourne status healthy."""
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "device" in data
    assert "checks" in data


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
    assert data["native_count"] == 9
    assert len(data["voices"]) >= 9


async def test_models_status(client):
    """GET /models/status retourne les etats de chargement."""
    r = await client.get("/models/status")
    assert r.status_code == 200
    data = r.json()
    assert "voice_design_loaded" in data
    assert data["voice_design_loaded"] is False


async def test_generation_status(client):
    """GET /generation/status retourne les stats."""
    r = await client.get("/generation/status")
    assert r.status_code == 200
    data = r.json()
    assert data["busy"] is False
    assert "stats" in data


async def test_generation_status_has_gpu_memory(client):
    """GET /generation/status contient gpu_memory."""
    r = await client.get("/generation/status")
    assert r.status_code == 200
    assert "gpu_memory" in r.json()


# ─── Validation input ────────────────────────────────────────────────────────

async def test_design_text_too_long(client):
    """POST /design refuse texte > 10000 chars."""
    r = await client.post("/design", json={
        "text": "x" * 10001,
        "voice_instruct": "voix grave",
        "language": "fr",
    })
    assert r.status_code == 422


async def test_design_empty_text(client):
    """POST /design refuse texte vide."""
    r = await client.post("/design", json={
        "text": "",
        "voice_instruct": "voix grave",
        "language": "fr",
    })
    assert r.status_code == 422


async def test_design_missing_text(client):
    """POST /design refuse sans champ text."""
    r = await client.post("/design", json={
        "voice_instruct": "voix grave",
        "language": "fr",
    })
    assert r.status_code == 422


async def test_batch_too_many_texts(client):
    """POST /batch/preset refuse > 100 textes."""
    r = await client.post("/batch/preset", json={
        "texts": ["t"] * 101,
        "voice": "Serena",
    })
    assert r.status_code == 422


async def test_batch_empty_texts(client):
    """POST /batch/preset refuse liste vide."""
    r = await client.post("/batch/preset", json={
        "texts": [],
        "voice": "Serena",
    })
    assert r.status_code == 422


# ─── Custom voices validation ────────────────────────────────────────────────

async def test_custom_voice_name_too_short(client):
    """POST /voices/custom refuse nom < 3 chars."""
    r = await client.post("/voices/custom", data={
        "name": "ab",
        "source": "design",
        "voice_description": "test",
    })
    assert r.status_code == 400


async def test_custom_voice_name_reserved(client):
    """POST /voices/custom refuse noms reserves (voix natives)."""
    r = await client.post("/voices/custom", data={
        "name": "Serena",
        "source": "design",
        "voice_description": "test",
    })
    assert r.status_code == 400


async def test_custom_voice_name_invalid_chars(client):
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


async def test_custom_voice_delete_not_found(client):
    """DELETE /voices/custom/nonexistent retourne 404."""
    r = await client.delete("/voices/custom/nonexistent")
    assert r.status_code == 404


# ─── Clone prompts ───────────────────────────────────────────────────────────

async def test_list_prompts_empty(client):
    """GET /clone/prompts retourne liste vide."""
    r = await client.get("/clone/prompts")
    assert r.status_code == 200
    assert r.json()["prompts"] == []


async def test_delete_prompt_not_found(client):
    """DELETE /clone/prompts/{id} retourne 404 pour id inexistant."""
    r = await client.delete("/clone/prompts/inexistant-xyz")
    assert r.status_code == 404


# ─── Voices reload ───────────────────────────────────────────────────────────

async def test_voices_reload(client):
    """POST /voices/reload retourne 200."""
    r = await client.post("/voices/reload")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "reloaded"
    assert "count" in data


# ─── General error handling ──────────────────────────────────────────────────

async def test_404_unknown_route(client):
    """GET /nonexistent retourne 404."""
    r = await client.get("/nonexistent")
    assert r.status_code == 404


# ─── Preset voice validation ────────────────────────────────────────────────

async def test_preset_empty_text(client):
    """POST /preset refuse texte vide."""
    r = await client.post("/preset", data={
        "text": "",
        "voice": "Serena",
        "language": "fr",
    })
    assert r.status_code == 422


async def test_preset_text_too_long(client):
    """POST /preset refuse texte > 10000 chars."""
    r = await client.post("/preset", data={
        "text": "x" * 10001,
        "voice": "Serena",
        "language": "fr",
    })
    assert r.status_code == 422


# ─── Batch design validation ────────────────────────────────────────────────

async def test_batch_design_too_many_texts(client):
    """POST /batch/design refuse > 100 textes."""
    r = await client.post("/batch/design", json={
        "texts": ["t"] * 101,
        "voice_instruct": "voix grave",
    })
    assert r.status_code == 422


async def test_batch_design_empty_texts(client):
    """POST /batch/design refuse liste vide."""
    r = await client.post("/batch/design", json={
        "texts": [],
        "voice_instruct": "voix grave",
    })
    assert r.status_code == 422
