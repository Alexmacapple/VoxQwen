#!/bin/bash
# Script de test automatisé pour Qwen3-TTS API
# Usage: ./Test/run_tests.sh

set -e

BASE_URL="http://localhost:8060"
OUTPUT_DIR="outputs"
PASSED=0
FAILED=0

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "╔══════════════════════════════════════════════════════════╗"
echo "║           TESTS API Qwen3-TTS                            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Fonction pour tester une route GET
test_get() {
    local name="$1"
    local url="$2"
    local expected="$3"

    printf "%-40s" "Test: $name"

    response=$(curl -s -w "\n%{http_code}" "$BASE_URL$url")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "200" ]; then
        if echo "$body" | grep -q "$expected"; then
            echo -e "${GREEN}✅ PASS${NC} (HTTP $http_code)"
            ((PASSED++))
        else
            echo -e "${RED}❌ FAIL${NC} (réponse inattendue)"
            ((FAILED++))
        fi
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP $http_code)"
        ((FAILED++))
    fi
}

# Fonction pour tester une route POST qui génère un fichier
test_post_audio() {
    local name="$1"
    local url="$2"
    local data="$3"
    local output="$4"

    printf "%-40s" "Test: $name"

    http_code=$(curl -s -X POST "$BASE_URL$url" $data --output "$OUTPUT_DIR/$output" -w "%{http_code}")

    if [ "$http_code" = "200" ]; then
        size=$(ls -l "$OUTPUT_DIR/$output" 2>/dev/null | awk '{print $5}')
        if [ "$size" -gt 1000 ]; then
            echo -e "${GREEN}✅ PASS${NC} (HTTP $http_code, ${size} bytes)"
            ((PASSED++))
        else
            echo -e "${RED}❌ FAIL${NC} (fichier trop petit)"
            ((FAILED++))
        fi
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP $http_code)"
        ((FAILED++))
    fi
}

# Vérifier que le serveur est accessible
echo "Vérification du serveur..."
if ! curl -s "$BASE_URL/" > /dev/null 2>&1; then
    echo -e "${RED}Erreur: Le serveur n'est pas accessible sur $BASE_URL${NC}"
    echo "Lancez d'abord: python main.py"
    exit 1
fi
echo -e "${GREEN}Serveur OK${NC}"
echo ""

# Créer le dossier output si nécessaire
mkdir -p "$OUTPUT_DIR"

echo "═══════════════════════════════════════════════════════════"
echo "TESTS GET (Routes d'information)"
echo "═══════════════════════════════════════════════════════════"

test_get "GET /" "/" '"status":"ok"'
test_get "GET /languages" "/languages" '"count":10'
test_get "GET /voices" "/voices" '"count":9'
test_get "GET /models/status" "/models/status" '"device":"mps"'
test_get "GET /clone/prompts" "/clone/prompts" '"prompts"'

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "TESTS POST (Génération audio)"
echo "═══════════════════════════════════════════════════════════"

# Test /preset
test_post_audio "POST /preset" "/preset" \
    '-F "text=Test automatique preset" -F "voice=Serena" -F "language=fr"' \
    "test_auto_preset.wav"

# Test /preset/instruct
test_post_audio "POST /preset/instruct" "/preset/instruct" \
    '-F "text=Test avec emotion" -F "voice=Serena" -F "instruct=Ton joyeux" -F "language=fr"' \
    "test_auto_preset_instruct.wav"

# Test /design
test_post_audio "POST /design" "/design" \
    '-H "Content-Type: application/json" -d "{\"text\":\"Test design\",\"voice_instruct\":\"Voix grave\",\"language\":\"fr\"}"' \
    "test_auto_design.wav"

# Test /clone (utilise test_auto_preset.wav comme référence)
if [ -f "$OUTPUT_DIR/test_auto_preset.wav" ]; then
    test_post_audio "POST /clone" "/clone" \
        "-F \"text=Test clonage\" -F reference_audio=@$OUTPUT_DIR/test_auto_preset.wav -F language=fr -F model=1.7B" \
        "test_auto_clone.wav"
else
    echo -e "Test: POST /clone                        ${YELLOW}⏭️ SKIP${NC} (pas de fichier référence)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "TESTS WORKFLOW PROMPT"
echo "═══════════════════════════════════════════════════════════"

# Test /clone/prompt
if [ -f "$OUTPUT_DIR/test_auto_preset.wav" ]; then
    printf "%-40s" "Test: POST /clone/prompt"
    response=$(curl -s -X POST "$BASE_URL/clone/prompt" \
        -F reference_audio=@$OUTPUT_DIR/test_auto_preset.wav \
        -F "reference_text=Test" \
        -F model=1.7B)

    if echo "$response" | grep -q "prompt_id"; then
        PROMPT_ID=$(echo "$response" | grep -o '"prompt_id":"[^"]*"' | cut -d'"' -f4)
        echo -e "${GREEN}✅ PASS${NC} (prompt_id: ${PROMPT_ID:0:8}...)"
        ((PASSED++))

        # Test /clone avec prompt_id
        test_post_audio "POST /clone (avec prompt_id)" "/clone" \
            "-F \"text=Test avec prompt\" -F \"prompt_id=$PROMPT_ID\" -F language=fr" \
            "test_auto_clone_prompt.wav"

        # Test DELETE /clone/prompts/{id}
        printf "%-40s" "Test: DELETE /clone/prompts/{id}"
        del_response=$(curl -s -X DELETE "$BASE_URL/clone/prompts/$PROMPT_ID")
        if echo "$del_response" | grep -q '"status":"deleted"'; then
            echo -e "${GREEN}✅ PASS${NC}"
            ((PASSED++))
        else
            echo -e "${RED}❌ FAIL${NC}"
            ((FAILED++))
        fi
    else
        echo -e "${RED}❌ FAIL${NC}"
        ((FAILED++))
    fi
else
    echo -e "Tests workflow prompt                    ${YELLOW}⏭️ SKIP${NC}"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "RÉSUMÉ"
echo "═══════════════════════════════════════════════════════════"
echo ""
TOTAL=$((PASSED + FAILED))
echo -e "Tests réussis:  ${GREEN}$PASSED${NC} / $TOTAL"
echo -e "Tests échoués:  ${RED}$FAILED${NC} / $TOTAL"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              TOUS LES TESTS SONT PASSÉS                  ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║              CERTAINS TESTS ONT ÉCHOUÉ                   ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
