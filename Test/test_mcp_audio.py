#!/usr/bin/env python3
"""
Tests MCP Audio - VoxQwen
Valide la génération audio via les endpoints MCP.

Usage:
    python Test/test_mcp_audio.py
"""

import base64
import json
import os
import sys
import wave
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE_URL = "http://localhost:8060"
OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name: str, details: str = ""):
        self.passed += 1
        print(f"  ✅ {name}" + (f" ({details})" if details else ""))

    def fail(self, name: str, reason: str):
        self.failed += 1
        self.errors.append((name, reason))
        print(f"  ❌ {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Résultats: {self.passed}/{total} tests passés")
        if self.errors:
            print("\nErreurs:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")
        return self.failed == 0


def http_get(endpoint: str) -> dict:
    """GET request returning JSON."""
    req = Request(f"{BASE_URL}{endpoint}")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def http_post(endpoint: str, data: dict) -> dict:
    """POST request returning JSON."""
    req = Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def validate_wav(audio_bytes: bytes) -> dict:
    """Validate WAV audio and return metadata."""
    if audio_bytes[:4] != b"RIFF":
        raise ValueError("Invalid WAV: missing RIFF header")
    if audio_bytes[8:12] != b"WAVE":
        raise ValueError("Invalid WAV: missing WAVE format")

    # Parse WAV header
    import struct
    channels = struct.unpack("<H", audio_bytes[22:24])[0]
    sample_rate = struct.unpack("<I", audio_bytes[24:28])[0]
    bits_per_sample = struct.unpack("<H", audio_bytes[34:36])[0]

    return {
        "channels": channels,
        "sample_rate": sample_rate,
        "bits_per_sample": bits_per_sample,
        "size_bytes": len(audio_bytes),
        "duration_sec": len(audio_bytes) / (sample_rate * channels * bits_per_sample // 8)
    }


def test_get_endpoints(result: TestResult):
    """Test GET endpoints."""
    print("\n📖 Tests GET Endpoints")
    print("-" * 40)

    # /mcp/languages
    try:
        data = http_get("/mcp/languages")
        if data.get("count") == 10 and data.get("auto_detection") is True:
            result.ok("/mcp/languages", f"{data['count']} langues")
        else:
            result.fail("/mcp/languages", f"count={data.get('count')}")
    except Exception as e:
        result.fail("/mcp/languages", str(e))

    # /mcp/voices
    try:
        data = http_get("/mcp/voices")
        native_count = len([v for v in data.get("voices", []) if v.get("type") == "native"])
        if native_count >= 9:
            result.ok("/mcp/voices", f"{native_count} voix natives")
        else:
            result.fail("/mcp/voices", f"seulement {native_count} voix natives")
    except Exception as e:
        result.fail("/mcp/voices", str(e))

    # /mcp/status
    try:
        data = http_get("/mcp/status")
        if data.get("mcp_enabled") is True:
            result.ok("/mcp/status", f"v{data.get('version')}")
        else:
            result.fail("/mcp/status", "mcp_enabled=false")
    except Exception as e:
        result.fail("/mcp/status", str(e))


def test_audio_generation(result: TestResult):
    """Test audio generation endpoints."""
    print("\n🎵 Tests Génération Audio")
    print("-" * 40)

    tests = [
        {
            "name": "/mcp/preset",
            "endpoint": "/mcp/preset",
            "data": {"text": "Test audio preset.", "voice": "Serena", "language": "fr"},
            "output": "test_preset.wav"
        },
        {
            "name": "/mcp/design",
            "endpoint": "/mcp/design",
            "data": {"text": "Test audio design.", "voice_description": "Voix masculine grave", "language": "fr"},
            "output": "test_design.wav"
        },
        {
            "name": "/mcp/preset/instruct",
            "endpoint": "/mcp/preset/instruct",
            "data": {"text": "Test audio instruct.", "voice": "Serena", "instruct": "Ton enthousiaste", "language": "fr"},
            "output": "test_instruct.wav"
        },
    ]

    for test in tests:
        try:
            data = http_post(test["endpoint"], test["data"])

            if "audio_base64" not in data:
                result.fail(test["name"], "pas de audio_base64")
                continue

            audio_bytes = base64.b64decode(data["audio_base64"])
            wav_info = validate_wav(audio_bytes)

            # Vérifier sample rate
            if wav_info["sample_rate"] != 24000:
                result.fail(test["name"], f"sample_rate={wav_info['sample_rate']} (attendu 24000)")
                continue

            # Sauvegarder
            output_path = OUTPUT_DIR / test["output"]
            output_path.write_bytes(audio_bytes)

            result.ok(
                test["name"],
                f"{wav_info['size_bytes']/1024:.1f}KB, {wav_info['duration_sec']:.1f}s"
            )

        except Exception as e:
            result.fail(test["name"], str(e))


def test_clone_workflow(result: TestResult):
    """Test voice clone workflow (prompt creation + generation)."""
    print("\n🎤 Test Workflow Clone")
    print("-" * 40)

    # Ce test nécessite un fichier audio de référence
    # Utilisons un des fichiers générés précédemment
    ref_audio = OUTPUT_DIR / "test_preset.wav"

    if not ref_audio.exists():
        result.fail("Clone workflow", "Fichier de référence manquant (exécuter d'abord test_audio_generation)")
        return

    try:
        # Encoder l'audio en base64
        audio_b64 = base64.b64encode(ref_audio.read_bytes()).decode()

        # Créer un prompt
        prompt_data = http_post("/mcp/clone/prompt", {
            "reference_audio_base64": audio_b64,
            "reference_text": "Test audio preset.",
            "model": "0.6B",
            "name": "test-mcp-clone"
        })

        if "prompt_id" not in prompt_data:
            result.fail("/mcp/clone/prompt", "pas de prompt_id")
            return

        prompt_id = prompt_data["prompt_id"]
        result.ok("/mcp/clone/prompt", f"prompt_id={prompt_id[:8]}...")

        # Générer avec le prompt
        clone_data = http_post("/mcp/clone", {
            "text": "Ceci est un test de clonage vocal.",
            "prompt_id": prompt_id,
            "language": "fr"
        })

        if "audio_base64" in clone_data:
            audio_bytes = base64.b64decode(clone_data["audio_base64"])
            wav_info = validate_wav(audio_bytes)
            output_path = OUTPUT_DIR / "test_clone.wav"
            output_path.write_bytes(audio_bytes)
            result.ok("/mcp/clone", f"{wav_info['size_bytes']/1024:.1f}KB")
        else:
            result.fail("/mcp/clone", "pas de audio_base64")

    except Exception as e:
        result.fail("Clone workflow", str(e))


def test_rate_limiting(result: TestResult):
    """Test rate limiting (optionnel, peut prendre du temps)."""
    print("\n⏱️  Test Rate Limiting")
    print("-" * 40)
    print("  (Skipped - prend trop de temps)")


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║           VoxQwen MCP - Tests Audio                      ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # Vérifier que le serveur est accessible
    try:
        http_get("/")
        print(f"\n✅ Serveur accessible: {BASE_URL}")
    except Exception as e:
        print(f"\n❌ Serveur inaccessible: {BASE_URL}")
        print(f"   Erreur: {e}")
        print("\nAssurez-vous que le serveur est lancé:")
        print("  source venv/bin/activate && python main.py")
        sys.exit(1)

    result = TestResult()

    test_get_endpoints(result)
    test_audio_generation(result)
    test_clone_workflow(result)
    test_rate_limiting(result)

    success = result.summary()

    print(f"\nFichiers audio: {OUTPUT_DIR}/")
    for f in OUTPUT_DIR.glob("*.wav"):
        print(f"  - {f.name} ({f.stat().st_size/1024:.1f} KB)")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
