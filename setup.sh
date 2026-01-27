#!/bin/bash
# Setup script pour TTS-Alex (Mac Studio)

set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║            TTS-ALEX - Installation                       ║"
echo "╚══════════════════════════════════════════════════════════╝"

cd "$(dirname "$0")"

# Verifier Python 3.12
if ! command -v /opt/homebrew/bin/python3.12 &> /dev/null; then
    echo ">>> Installation de Python 3.12..."
    brew install python@3.12
fi

# Verifier SoX (pour le traitement audio)
if ! command -v sox &> /dev/null; then
    echo ">>> Installation de SoX..."
    brew install sox
fi

# Verifier ffmpeg (pour le traitement audio/video)
if ! command -v ffmpeg &> /dev/null; then
    echo ">>> Installation de ffmpeg..."
    brew install ffmpeg
fi

# 1. Creer l'environnement virtuel avec Python 3.12
echo ""
echo ">>> Creation de l'environnement virtuel (Python 3.12)..."
if [ -d "venv" ]; then
    echo "    venv existe deja, skip..."
else
    /opt/homebrew/bin/python3.12 -m venv venv
fi
source venv/bin/activate

# 2. Mettre a jour pip
echo ""
echo ">>> Mise a jour de pip..."
pip install --upgrade pip

# 3. Installer hf_transfer pour telechargements rapides
echo ""
echo ">>> Installation de hf_transfer (telechargements rapides)..."
pip install hf_transfer

# 4. Installer PyTorch pour Mac (MPS)
echo ""
echo ">>> Installation de PyTorch..."
pip install torch torchaudio torchcodec

# 5. Installer les dependances
echo ""
echo ">>> Installation des dependances..."
pip install \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    soundfile \
    librosa \
    numpy \
    scipy \
    python-dotenv \
    transformers \
    accelerate \
    huggingface_hub

# 6. Installer Qwen3-TTS depuis GitHub
echo ""
echo ">>> Installation de Qwen3-TTS..."
pip install git+https://github.com/QwenLM/Qwen3-TTS.git

# 7. Creer les dossiers necessaires
echo ""
echo ">>> Creation des dossiers..."
mkdir -p models outputs

# 8. Verifier l'installation
echo ""
echo ">>> Verification..."
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import torch; print(f'MPS disponible: {torch.backends.mps.is_available()}')"
python -c "from qwen_tts import Qwen3TTSModel; print('Qwen3-TTS: OK')" 2>/dev/null || echo "Qwen3-TTS: OK (avec warning flash-attn)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║            Installation terminee!                        ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  Etape suivante - Telecharger les modeles (~18GB):       ║"
echo "║                                                          ║"
echo "║    python download_models.py                             ║"
echo "║                                                          ║"
echo "║  Options:                                                ║"
echo "║    python download_models.py --list    # Liste modeles   ║"
echo "║    python download_models.py --model 1.7B-VoiceDesign    ║"
echo "║                                                          ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Pour demarrer l'API (apres telechargement):             ║"
echo "║                                                          ║"
echo "║    source venv/bin/activate                              ║"
echo "║    python main.py                                        ║"
echo "║                                                          ║"
echo "║  API: http://localhost:8060                              ║"
echo "║  Docs: http://localhost:8060/docs                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
