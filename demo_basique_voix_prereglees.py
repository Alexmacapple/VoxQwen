#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstration Qwen3-TTS - Voix Prereglees (CustomVoice 0.6B)

Adapte du Google Colab pour Mac Studio local.
Utilise le modele CustomVoice avec 9 voix premium.

Usage:
    cd /Users/alex/LOIC/tts-alex
    source venv/bin/activate
    python python/demo_basique_voix_prereglees.py
"""

import os
import sys
import torch
import soundfile as sf
from pathlib import Path

# Configuration des chemins
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
MODELS_DIR = PROJECT_DIR / "models"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Chemin du modele local
CUSTOM_VOICE_MODEL = MODELS_DIR / "CustomVoice"


# ==============================================================================
# INFORMATIONS SUR LES VOIX
# ==============================================================================

SPEAKER_INFO = {
    "Vivian": ("Femme", "Chinois", "Voix feminine jeune, vive et legerement incisive"),
    "Serena": ("Femme", "Chinois", "Voix feminine jeune, chaleureuse et douce"),
    "Uncle_Fu": ("Homme", "Chinois", "Voix masculine mature avec un timbre grave et veloute"),
    "Dylan": ("Homme", "Chinois (Pekin)", "Voix masculine jeune de Pekin, claire et naturelle"),
    "Eric": ("Homme", "Chinois (Sichuan)", "Voix masculine enjouee de Chengdu, legerement rauque"),
    "Ryan": ("Homme", "Anglais", "Voix masculine dynamique avec un rythme soutenu"),
    "Aiden": ("Homme", "Anglais", "Voix masculine americaine ensoleillee avec des mediums clairs"),
    "Ono_Anna": ("Femme", "Japonais", "Voix feminine espiegle avec un timbre leger et agile"),
    "Sohee": ("Femme", "Coreen", "Voix feminine chaleureuse avec une riche emotion"),
}

LANGUES = ["Chinese", "English", "Japanese", "Korean", "German",
           "French", "Russian", "Portuguese", "Spanish", "Italian"]


# ==============================================================================
# FONCTIONS UTILITAIRES
# ==============================================================================

def get_device():
    """Detecte le meilleur device disponible."""
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def load_model():
    """Charge le modele CustomVoice."""
    from qwen_tts import Qwen3TTSModel

    print("=" * 60)
    print("CHARGEMENT DU MODELE")
    print("=" * 60)

    device = get_device()
    print(f"Device: {device}")

    if not CUSTOM_VOICE_MODEL.exists():
        print(f"ERREUR: Modele non trouve: {CUSTOM_VOICE_MODEL}")
        print("Telechargez-le avec:")
        print(f"  huggingface-cli download Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice --local-dir {CUSTOM_VOICE_MODEL}")
        sys.exit(1)

    print(f"Modele: {CUSTOM_VOICE_MODEL}")
    print("Chargement en cours...")

    model = Qwen3TTSModel.from_pretrained(
        str(CUSTOM_VOICE_MODEL),
        device_map=device,
        dtype=torch.float32,  # float32 pour MPS (float16 cause des NaN)
    )

    print("Modele charge avec succes!")
    print("=" * 60)
    return model


def generate_audio(model, text, language, speaker, filename):
    """Genere un fichier audio."""
    text_preview = text[:50] + "..." if len(text) > 50 else text
    print(f"Generation: \"{text_preview}\"")
    print(f"   Voix: {speaker} | Langue: {language}")

    wavs, sr = model.generate_custom_voice(
        text=text,
        language=language,
        speaker=speaker,
    )

    filepath = OUTPUTS_DIR / f"{filename}.wav"
    sf.write(str(filepath), wavs[0], sr)
    print(f"   Sauvegarde: {filepath}")

    return wavs, sr


def list_voices():
    """Affiche les voix disponibles."""
    print("\n" + "=" * 60)
    print("VOIX DISPONIBLES")
    print("=" * 60)

    for speaker, (genre, langue, desc) in SPEAKER_INFO.items():
        print(f"\n  {speaker}")
        print(f"     Genre: {genre} | Langue native: {langue}")
        print(f"     Description: {desc}")

    print("\n" + "=" * 60)
    print(f"LANGUES SUPPORTEES ({len(LANGUES)}):")
    print(", ".join(LANGUES))
    print("=" * 60)


# ==============================================================================
# DEMONSTRATIONS
# ==============================================================================

def demo_basique(model):
    """Demo de base - generation simple."""
    print("\n" + "=" * 60)
    print("DEMO 1: GENERATION BASIQUE")
    print("=" * 60)

    generate_audio(model,
        text="Bonjour ! Bienvenue dans la demonstration de synthese vocale Qwen3.",
        language="French",
        speaker="Serena",
        filename="basique_01_francais_serena"
    )

    generate_audio(model,
        text="Hello! Welcome to the Qwen3 text-to-speech demonstration.",
        language="English",
        speaker="Ryan",
        filename="basique_02_anglais_ryan"
    )

    generate_audio(model,
        text="你好！欢迎使用Qwen3语音合成模型。",
        language="Chinese",
        speaker="Vivian",
        filename="basique_03_chinois_vivian"
    )


def demo_comparaison(model):
    """Compare differentes voix avec le meme texte."""
    print("\n" + "=" * 60)
    print("DEMO 2: COMPARAISON DES VOIX")
    print("=" * 60)

    texte_fr = "Un renard roux et vif bondit par-dessus le chien endormi."

    for speaker in ["Serena", "Uncle_Fu", "Ryan"]:
        print(f"\n--- {speaker} ---")
        generate_audio(model,
            text=texte_fr,
            language="French",
            speaker=speaker,
            filename=f"comparaison_{speaker.lower()}"
        )


def demo_multilingue(model):
    """Un meme speaker parle plusieurs langues."""
    print("\n" + "=" * 60)
    print("DEMO 3: SERENA PARLE PLUSIEURS LANGUES")
    print("=" * 60)

    exemples = [
        ("French", "Bonjour ! Comment allez-vous aujourd'hui ?"),
        ("English", "Good morning! How are you doing today?"),
        ("German", "Guten Morgen! Wie geht es Ihnen heute?"),
        ("Spanish", "Buenos dias! Como esta usted hoy?"),
        ("Italian", "Buongiorno! Come sta oggi?"),
    ]

    for langue, texte in exemples:
        print(f"\n--- {langue} ---")
        generate_audio(model,
            text=texte,
            language=langue,
            speaker="Serena",
            filename=f"multilingue_serena_{langue.lower()}"
        )


def demo_voix_natives(model):
    """Chaque voix dans sa langue native."""
    print("\n" + "=" * 60)
    print("DEMO 4: VOIX NATIVES")
    print("=" * 60)

    exemples = [
        ("Japanese", "Ono_Anna", "こんにちは！今日はとても良い天気ですね。"),
        ("Korean", "Sohee", "안녕하세요! 오늘 날씨가 정말 좋네요."),
        ("Chinese", "Dylan", "北京欢迎您！这里有故宫和长城。"),
        ("Chinese", "Eric", "巴适得很！四川的火锅安逸惨了！"),
    ]

    for langue, speaker, texte in exemples:
        print(f"\n--- {speaker} ({langue}) ---")
        generate_audio(model,
            text=texte,
            language=langue,
            speaker=speaker,
            filename=f"natif_{speaker.lower()}"
        )


def demo_texte_long(model):
    """Generation de texte plus long."""
    print("\n" + "=" * 60)
    print("DEMO 5: TEXTE LONG")
    print("=" * 60)

    texte = """Il etait une fois, dans un petit village de Provence
    niche entre des collines couvertes de lavande et une riviere scintillante,
    une jeune inventrice nommee Maya. Elle passait ses journees a bricoler
    des engrenages et des ressorts, revant de machines capables de voler."""

    generate_audio(model,
        text=texte,
        language="French",
        speaker="Serena",
        filename="texte_long_histoire"
    )


def demo_batch(model):
    """Generation par lot."""
    print("\n" + "=" * 60)
    print("DEMO 6: GENERATION PAR LOT")
    print("=" * 60)

    textes = [
        "Premierement, nous rassemblons tous les ingredients.",
        "Ensuite, nous prechauffons le four a 180 degres.",
        "Puis, nous melangeons les ingredients secs.",
        "Enfin, nous faisons cuire pendant 25 minutes.",
    ]

    print(f"Generation de {len(textes)} audios en un seul appel...")

    wavs, sr = model.generate_custom_voice(
        text=textes,
        language=["French"] * len(textes),
        speaker=["Serena"] * len(textes),
    )

    for i, (texte, wav) in enumerate(zip(textes, wavs)):
        filepath = OUTPUTS_DIR / f"batch_etape_{i+1}.wav"
        sf.write(str(filepath), wav, sr)
        print(f"   Etape {i+1}: {filepath}")


def demo_detection_auto(model):
    """Detection automatique de la langue."""
    print("\n" + "=" * 60)
    print("DEMO 7: DETECTION AUTOMATIQUE DE LA LANGUE")
    print("=" * 60)

    exemples = [
        "Bonjour, ceci est une phrase en francais.",
        "这是一个中文句子。",
        "これは日本語の文章です。",
    ]

    for i, texte in enumerate(exemples):
        print(f"\n--- Detection auto: '{texte[:30]}...' ---")
        wavs, sr = model.generate_custom_voice(
            text=texte,
            language="Auto",
            speaker="Vivian",
        )
        filepath = OUTPUTS_DIR / f"detection_auto_{i+1}.wav"
        sf.write(str(filepath), wavs[0], sr)
        print(f"   Sauvegarde: {filepath}")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     QWEN3-TTS DEMO BASIQUE - VOIX PREREGLEES             ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Modele: CustomVoice 0.6B                                ║
    ║  9 voix premium | 10 langues                             ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    # Afficher les voix disponibles
    list_voices()

    # Charger le modele
    model = load_model()

    # Lancer les demos
    demo_basique(model)
    demo_comparaison(model)
    demo_multilingue(model)
    demo_voix_natives(model)
    demo_texte_long(model)
    demo_batch(model)
    demo_detection_auto(model)

    print("\n" + "=" * 60)
    print("DEMOS TERMINEES!")
    print(f"Fichiers audio dans: {OUTPUTS_DIR}")
    print("=" * 60)
    print("\nPour ecouter:")
    print(f"  open {OUTPUTS_DIR}")
    print("  afplay outputs/basique_01_francais_serena.wav")


if __name__ == "__main__":
    main()
