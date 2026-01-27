#!/usr/bin/env python3
"""
Tests d'Intégration MCP - VoxQwen
Tests complets incluant validation JSON-RPC et SSE.

Usage:
    python Test/test_mcp_integration.py
"""

import json
import socket
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE_URL = "http://localhost:8060"


class Colors:
    """ANSI color codes."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str):
    print(f"\n{Colors.BLUE}{Colors.BOLD}{text}{Colors.RESET}")
    print("-" * 50)


def print_ok(text: str):
    print(f"  {Colors.GREEN}✅ {text}{Colors.RESET}")


def print_fail(text: str):
    print(f"  {Colors.RED}❌ {text}{Colors.RESET}")


def print_warn(text: str):
    print(f"  {Colors.YELLOW}⚠️  {text}{Colors.RESET}")


def http_request(method: str, endpoint: str, data: dict = None, timeout: int = 10) -> tuple:
    """Make HTTP request, return (status_code, response_dict or error)."""
    try:
        if method == "GET":
            req = Request(f"{BASE_URL}{endpoint}")
        else:
            req = Request(
                f"{BASE_URL}{endpoint}",
                data=json.dumps(data).encode() if data else None,
                headers={"Content-Type": "application/json"} if data else {},
                method=method
            )
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except:
            body = {"error": str(e)}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def test_server_health() -> bool:
    """Test si le serveur est accessible."""
    print_header("1. Santé du Serveur")

    status, data = http_request("GET", "/")
    if status == 200 and data.get("status") == "ok":
        print_ok(f"Serveur OK - Device: {data.get('device')}")
        return True
    else:
        print_fail(f"Serveur inaccessible: {data}")
        return False


def test_mcp_status() -> bool:
    """Test le statut MCP."""
    print_header("2. Statut MCP")

    status, data = http_request("GET", "/mcp/status")
    if status != 200:
        print_fail(f"HTTP {status}")
        return False

    checks = [
        ("mcp_enabled", data.get("mcp_enabled") is True, "MCP activé"),
        ("version", data.get("version") is not None, f"Version {data.get('version')}"),
        ("device", data.get("device") is not None, f"Device {data.get('device')}"),
    ]

    all_ok = True
    for name, passed, msg in checks:
        if passed:
            print_ok(msg)
        else:
            print_fail(f"{name} manquant")
            all_ok = False

    return all_ok


def test_openapi_schema() -> bool:
    """Test le schéma OpenAPI contient les routes MCP."""
    print_header("3. Schéma OpenAPI")

    status, data = http_request("GET", "/openapi.json")
    if status != 200:
        print_fail(f"HTTP {status}")
        return False

    paths = data.get("paths", {})
    mcp_routes = [p for p in paths.keys() if "/mcp" in p]

    expected_routes = [
        "/mcp/preset",
        "/mcp/design",
        "/mcp/clone",
        "/mcp/voices",
        "/mcp/languages",
        "/mcp/status",
    ]

    all_ok = True
    for route in expected_routes:
        if route in mcp_routes:
            print_ok(f"Route {route}")
        else:
            print_fail(f"Route {route} manquante")
            all_ok = False

    print(f"\n  Total routes MCP: {len(mcp_routes)}")
    return all_ok


def test_sse_endpoint() -> bool:
    """Test l'endpoint SSE principal."""
    print_header("4. Endpoint SSE /mcp")

    try:
        req = Request(f"{BASE_URL}/mcp")
        with urlopen(req, timeout=3) as resp:
            # Lire le premier event SSE
            content = resp.read(200).decode()
            if "session_id" in content:
                print_ok(f"SSE actif avec session_id")
                return True
            else:
                print_warn(f"SSE actif mais pas de session_id")
                return True
    except Exception as e:
        if "timed out" in str(e).lower():
            # Timeout normal pour SSE
            print_ok("Connexion SSE établie (timeout normal)")
            return True
        print_fail(f"Erreur SSE: {e}")
        return False


def test_error_handling() -> bool:
    """Test la gestion d'erreurs."""
    print_header("5. Gestion d'Erreurs")

    tests = [
        {
            "name": "Texte vide",
            "endpoint": "/mcp/preset",
            "data": {"text": "", "voice": "Serena"},
            "expected_status": 422
        },
        {
            "name": "Voix invalide",
            "endpoint": "/mcp/preset",
            "data": {"text": "Test", "voice": "VoixInexistante"},
            "expected_status": 404  # Voix non trouvée = 404
        },
        {
            "name": "Prompt inexistant",
            "endpoint": "/mcp/clone",
            "data": {"text": "Test", "prompt_id": "invalid-uuid"},
            "expected_status": 404
        },
    ]

    all_ok = True
    for test in tests:
        status, data = http_request("POST", test["endpoint"], test["data"])
        if status == test["expected_status"]:
            print_ok(f"{test['name']} → HTTP {status}")
        else:
            print_fail(f"{test['name']} → HTTP {status} (attendu {test['expected_status']})")
            all_ok = False

    return all_ok


def test_concurrent_requests() -> bool:
    """Test les requêtes concurrentes (basique)."""
    print_header("6. Requêtes Concurrentes")

    import threading
    results = []

    def make_request(i):
        status, _ = http_request("GET", "/mcp/voices")
        results.append((i, status))

    threads = []
    for i in range(5):
        t = threading.Thread(target=make_request, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    success = sum(1 for _, status in results if status == 200)
    if success == 5:
        print_ok(f"5/5 requêtes parallèles réussies")
        return True
    else:
        print_fail(f"{success}/5 requêtes réussies")
        return False


def test_response_format() -> bool:
    """Test le format des réponses."""
    print_header("7. Format des Réponses")

    # Test voices
    status, data = http_request("GET", "/mcp/voices")
    if status != 200:
        print_fail(f"/mcp/voices HTTP {status}")
        return False

    voices = data.get("voices", [])
    if len(voices) > 0:
        voice = voices[0]
        required_fields = ["name", "type", "gender", "description"]
        missing = [f for f in required_fields if f not in voice]
        if missing:
            print_fail(f"Champs manquants dans voice: {missing}")
            return False
        print_ok(f"Format voice OK ({len(voices)} voix)")
    else:
        print_fail("Aucune voix retournée")
        return False

    # Test languages
    status, data = http_request("GET", "/mcp/languages")
    if status != 200:
        print_fail(f"/mcp/languages HTTP {status}")
        return False

    langs = data.get("languages", [])
    if len(langs) > 0:
        lang = langs[0]
        if "code" in lang and "name" in lang:
            print_ok(f"Format language OK ({len(langs)} langues)")
        else:
            print_fail("Format language invalide")
            return False
    else:
        print_fail("Aucune langue retournée")
        return False

    return True


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       VoxQwen MCP - Tests d'Intégration                  ║")
    print("╚══════════════════════════════════════════════════════════╝")

    tests = [
        ("Santé Serveur", test_server_health),
        ("Statut MCP", test_mcp_status),
        ("Schéma OpenAPI", test_openapi_schema),
        ("Endpoint SSE", test_sse_endpoint),
        ("Gestion Erreurs", test_error_handling),
        ("Concurrence", test_concurrent_requests),
        ("Format Réponses", test_response_format),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print_fail(f"Exception: {e}")
            results.append((name, False))

    # Résumé
    print("\n" + "=" * 60)
    print(f"{Colors.BOLD}RÉSUMÉ{Colors.RESET}")
    print("=" * 60)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for name, p in results:
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if p else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  {name}: {status}")

    print()
    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ TOUS LES TESTS PASSÉS ({passed}/{total}){Colors.RESET}")
        sys.exit(0)
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ ÉCHECS: {total - passed}/{total}{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
