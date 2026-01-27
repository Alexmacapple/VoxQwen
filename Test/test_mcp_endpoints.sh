#!/bin/bash
# Tests MCP - VoxQwen
# Usage: ./Test/test_mcp_endpoints.sh

# Ne pas utiliser set -e pour voir tous les résultats

BASE_URL="http://localhost:8060"
PASS=0
FAIL=0
OUTPUT_DIR="$(dirname "$0")/outputs"

mkdir -p "$OUTPUT_DIR"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║           VoxQwen MCP - Tests Endpoints                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Fonction de test
test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected="$5"

    printf "%-40s" "Testing $name..."

    if [ "$method" = "GET" ]; then
        response=$(curl -s "$BASE_URL$endpoint")
    else
        response=$(curl -s -X POST "$BASE_URL$endpoint" -H "Content-Type: application/json" -d "$data")
    fi

    if echo "$response" | grep -q "$expected"; then
        echo "✅ PASS"
        PASS=$((PASS + 1))
    else
        echo "❌ FAIL"
        echo "  Expected: $expected"
        echo "  Got: $(echo "$response" | head -c 100)..."
        FAIL=$((FAIL + 1))
    fi
}

# Fonction pour tester génération audio
test_audio_generation() {
    local name="$1"
    local endpoint="$2"
    local data="$3"
    local output_file="$4"

    printf "%-40s" "Testing $name..."

    response=$(curl -s -X POST "$BASE_URL$endpoint" -H "Content-Type: application/json" -d "$data")

    if echo "$response" | grep -q "audio_base64"; then
        # Extraire et décoder l'audio
        echo "$response" | python3 -c "
import json, sys, base64
d = json.load(sys.stdin)
with open('$OUTPUT_DIR/$output_file', 'wb') as f:
    f.write(base64.b64decode(d['audio_base64']))
"
        # Vérifier le header WAV
        if head -c 4 "$OUTPUT_DIR/$output_file" | grep -q "RIFF"; then
            size=$(ls -lh "$OUTPUT_DIR/$output_file" | awk '{print $5}')
            echo "✅ PASS ($size)"
            PASS=$((PASS + 1))
        else
            echo "❌ FAIL (invalid WAV header)"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "❌ FAIL (no audio_base64)"
        echo "  Response: $(echo "$response" | head -c 100)..."
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Tests Endpoints GET ==="
echo ""

test_endpoint "GET /mcp/languages" "GET" "/mcp/languages" "" "count"
test_endpoint "GET /mcp/voices" "GET" "/mcp/voices" "" "native"
test_endpoint "GET /mcp/status" "GET" "/mcp/status" "" "mcp_enabled"

echo ""
echo "=== Tests Endpoints POST (Génération Audio) ==="
echo ""

test_audio_generation \
    "POST /mcp/preset" \
    "/mcp/preset" \
    '{"text":"Test preset MCP","voice":"Serena","language":"fr"}' \
    "test_preset.wav"

test_audio_generation \
    "POST /mcp/design" \
    "/mcp/design" \
    '{"text":"Test design MCP","voice_description":"Voix masculine grave","language":"fr"}' \
    "test_design.wav"

test_audio_generation \
    "POST /mcp/preset/instruct" \
    "/mcp/preset/instruct" \
    '{"text":"Test instruct MCP","voice":"Serena","instruct":"Ton joyeux","language":"fr"}' \
    "test_instruct.wav"

echo ""
echo "=== Test Endpoint SSE ==="
echo ""

printf "%-40s" "Testing GET /mcp (SSE)..."
sse_response=$(curl -s -m 2 "$BASE_URL/mcp" 2>&1 || true)
if echo "$sse_response" | grep -q "session_id"; then
    echo "✅ PASS (SSE active)"
    ((PASS++))
else
    echo "❌ FAIL"
    ((FAIL++))
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    RÉSULTATS                             ║"
echo "╠══════════════════════════════════════════════════════════╣"
printf "║  Tests réussis:  %-38s║\n" "$PASS"
printf "║  Tests échoués:  %-38s║\n" "$FAIL"
echo "╠══════════════════════════════════════════════════════════╣"

if [ $FAIL -eq 0 ]; then
    echo "║  ✅ TOUS LES TESTS SONT PASSÉS                          ║"
else
    echo "║  ❌ CERTAINS TESTS ONT ÉCHOUÉ                           ║"
fi

echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Fichiers audio générés dans: $OUTPUT_DIR/"
ls -lh "$OUTPUT_DIR"/*.wav 2>/dev/null || echo "(aucun fichier)"

exit $FAIL
