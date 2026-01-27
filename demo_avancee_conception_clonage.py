#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstration Avancee Qwen3-TTS 1.7B
- Conception de voix (VoiceDesign)
- Controle par instructions (CustomVoice 1.7B)
- Clonage vocal (Base)

Adapte du Google Colab pour Mac Studio local.

Usage:
    cd /Users/alex/LOIC/tts-alex
    source venv/bin/activate
    python python/demo_avancee_conception_clonage.py

IMPORTANT: Necessite les modeles 1.7B telecharges:
    huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local-dir models/VoiceDesign
    huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --local-dir models/CustomVoice1.7B
    huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-Base --local-dir models/Base1.7B
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

# Chemins des modeles
VOICE_DESIGN_MODEL = MODELS_DIR / "VoiceDesign"
CUSTOM_VOICE_1_7B_MODEL = MODELS_DIR / "CustomVoice1.7B"
BASE_MODEL = MODELS_DIR / "Base1.7B"


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


def load_model(model_path, model_name):
    """Charge un modele Qwen3-TTS."""
    from qwen_tts import Qwen3TTSModel

    print(f"\n>>> Chargement du modele {model_name}...")
    device = get_device()
    print(f"    Device: {device}")

    if not model_path.exists():
        print(f"    ERREUR: Modele non trouve: {model_path}")
        print(f"    Telechargez-le d'abord (voir DOWNLOAD_MODELS.md)")
        return None

    model = Qwen3TTSModel.from_pretrained(
        str(model_path),
        device_map=device,
        dtype=torch.float32,  # float32 pour MPS
    )

    print(f"    Modele {model_name} charge!")
    return model


def save_audio(wavs, sr, filename, title=None):
    """Sauvegarde un fichier audio."""
    filepath = OUTPUTS_DIR / f"{filename}.wav"
    sf.write(str(filepath), wavs[0], sr)
    if title:
        print(f"   {title}: {filepath}")
    else:
        print(f"   Sauvegarde: {filepath}")
    return filepath


# ==============================================================================
# PARTIE 1: CONCEPTION DE VOIX (VoiceDesign)
# ==============================================================================

def demo_voice_design():
    """Demonstration de la conception de voix."""
    print("\n" + "=" * 60)
    print("PARTIE 1: CONCEPTION DE VOIX (VoiceDesign)")
    print("=" * 60)
    print("Creez des voix uniques avec des descriptions textuelles!")

    model = load_model(VOICE_DESIGN_MODEL, "VoiceDesign 1.7B")
    if model is None:
        print("Telechargez le modele:")
        print("  huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local-dir models/VoiceDesign")
        return None

    # Voix 1: Fille anime
    print("\n--- Voix 1: Fille anime mignonne ---")
    wavs, sr = model.generate_voice_design(
        text="Coucou tout le monde ! Je suis tellement contente de vous rencontrer !",
        language="French",
        instruct="Voix feminine jeune, environ 16 ans, tres mignonne et energique. Aigue avec un ton vif et joyeux."
    )
    save_audio(wavs, sr, "vd_01_fille_anime", "Fille anime")

    # Voix 2: Narrateur documentaire
    print("\n--- Voix 2: Narrateur documentaire ---")
    wavs, sr = model.generate_voice_design(
        text="Dans les profondeurs de l'ocean, la ou la lumiere ne penetre jamais, se cache un monde extraordinaire.",
        language="French",
        instruct="Voix masculine grave, 50-60 ans. Style narrateur documentaire. Parle lentement avec gravite."
    )
    save_audio(wavs, sr, "vd_02_narrateur", "Narrateur")

    # Voix 3: Adolescent nerveux
    print("\n--- Voix 3: Adolescent nerveux ---")
    wavs, sr = model.generate_voice_design(
        text="Euh, s-salut... Je me demandais si peut-etre... on pourrait reviser ensemble ?",
        language="French",
        instruct="Voix masculine jeune, 17 ans. Nerveux et timide, voix legerement tremblante avec hesitations."
    )
    save_audio(wavs, sr, "vd_03_ado_nerveux", "Ado nerveux")

    # Voix 4: Mechant mysterieux
    print("\n--- Voix 4: Mechant mysterieux ---")
    wavs, sr = model.generate_voice_design(
        text="Tu pensais pouvoir t'echapper ? Le jeu ne fait que commencer.",
        language="French",
        instruct="Voix masculine menacante, grave et soyeuse. Parle lentement avec sous-entendus sinistres."
    )
    save_audio(wavs, sr, "vd_04_mechant", "Mechant")

    # Meme texte, differentes voix
    print("\n--- Meme texte avec 4 voix differentes ---")
    texte = "Je n'arrive pas a croire que ca se passe vraiment."

    variations = [
        ("Enfant excitee", "Fille de 8 ans, tres aigue et excitee. Parle vite avec enthousiasme."),
        ("Adulte epuisee", "Femme de 35 ans, fatiguee. Soupire, parle lentement."),
        ("Ancien choque", "Homme de 70 ans, voix rauque, choque et incredule."),
        ("Ado sarcastique", "Fille de 16 ans, sarcasme qui degouline. Monotone."),
    ]

    for i, (nom, instruct) in enumerate(variations):
        print(f"   {nom}...")
        wavs, sr = model.generate_voice_design(text=texte, language="French", instruct=instruct)
        save_audio(wavs, sr, f"vd_05_variation_{i+1}", nom)

    # Voix francaises typiques
    print("\n--- Voix francaises personnalisees ---")

    voix_fr = [
        ("Bonjour a tous, bienvenue dans mon cours de philosophie.",
         "Professeur universitaire, 55 ans, voix posee et cultivee. Style Sorbonne.",
         "Professeur"),
        ("Bonjour ! Les croissants sont tout frais, ils sortent du four !",
         "Boulangere parisienne, 45 ans, chaleureuse et dynamique.",
         "Boulangere"),
        ("Suivez-moi, je vais vous faire decouvrir les secrets de ce chateau.",
         "Guide touristique passionnee, 35 ans, cultivee et enthousiaste.",
         "Guide"),
    ]

    for texte, instruct, nom in voix_fr:
        print(f"   {nom}...")
        wavs, sr = model.generate_voice_design(text=texte, language="French", instruct=instruct)
        save_audio(wavs, sr, f"vd_06_{nom.lower()}", nom)

    return model


# ==============================================================================
# PARTIE 2: CONTROLE PAR INSTRUCTIONS (CustomVoice 1.7B)
# ==============================================================================

def demo_custom_voice_instructions():
    """Demonstration du controle par instructions."""
    print("\n" + "=" * 60)
    print("PARTIE 2: CONTROLE PAR INSTRUCTIONS (CustomVoice 1.7B)")
    print("=" * 60)
    print("Controlez l'emotion et le style des voix prereglees!")

    model = load_model(CUSTOM_VOICE_1_7B_MODEL, "CustomVoice 1.7B")
    if model is None:
        print("Telechargez le modele:")
        print("  huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --local-dir models/CustomVoice1.7B")
        return None

    # Emotions sur le meme texte
    print("\n--- Meme texte avec differentes emotions ---")
    texte = "Je viens d'apprendre ce qui s'est passe hier."
    speaker = "Serena"

    emotions = [
        ("Joyeuse", "Ton tres joyeux et excite"),
        ("Triste", "Triste et melancolique, voix legerement brisee"),
        ("En colere", "En colere et frustree, parlant avec force"),
        ("Apeuree", "Effrayee et anxieuse, voix tremblante"),
        ("Neutre", ""),
    ]

    for emotion, instruct in emotions:
        print(f"   {emotion}...")
        wavs, sr = model.generate_custom_voice(
            text=texte,
            language="French",
            speaker=speaker,
            instruct=instruct
        )
        save_audio(wavs, sr, f"cv_01_emotion_{emotion.lower().replace(' ', '_')}", emotion)

    # Styles de parole
    print("\n--- Differents styles de parole ---")
    texte = "S'il vous plait, faites silence, le bebe dort."

    styles = [
        ("Chuchotement", "Chuchotant tres doucement et silencieusement"),
        ("Fort", "Parlant fort et clairement, projetant la voix"),
        ("Rapide", "Parlant tres vite, rythme presse"),
        ("Lent", "Parlant tres lentement et deliberement"),
        ("Dramatique", "Tres dramatique et theatral"),
    ]

    for style, instruct in styles:
        print(f"   {style}...")
        wavs, sr = model.generate_custom_voice(
            text=texte,
            language="French",
            speaker="Serena",
            instruct=instruct
        )
        save_audio(wavs, sr, f"cv_02_style_{style.lower()}", style)

    # Scenarios de jeu de role
    print("\n--- Scenarios de jeu de role ---")

    scenarios = [
        ("Uncle_Fu", "Bienvenue a ce match ! La tension est absolument electrique !",
         "Commentateur sportif, tres energique", "Commentateur"),
        ("Serena", "Notre chiffre d'affaires a augmente de 15 pour cent.",
         "Presentation professionnelle, confiante", "Business"),
        ("Uncle_Fu", "Et alors le dragon s'est retourne vers notre groupe...",
         "Maitre du donjon, mysterieux et dramatique", "JDR"),
        ("Serena", "La recette du jour, c'est une delicieuse omelette !",
         "Animatrice cuisine, joyeuse et chaleureuse", "Cuisine"),
    ]

    for speaker, texte, instruct, nom in scenarios:
        print(f"   {nom}...")
        wavs, sr = model.generate_custom_voice(
            text=texte,
            language="French",
            speaker=speaker,
            instruct=instruct
        )
        save_audio(wavs, sr, f"cv_03_scenario_{nom.lower()}", nom)

    return model


# ==============================================================================
# PARTIE 3: CLONAGE VOCAL (Base)
# ==============================================================================

def demo_voice_clone():
    """Demonstration du clonage vocal."""
    print("\n" + "=" * 60)
    print("PARTIE 3: CLONAGE VOCAL (Base 1.7B)")
    print("=" * 60)
    print("Clonez une voix a partir d'un audio de reference!")

    model = load_model(BASE_MODEL, "Base 1.7B")
    if model is None:
        print("Telechargez le modele:")
        print("  huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-Base --local-dir models/Base1.7B")
        return None

    # Verifier si on a un audio de reference
    ref_audio = PROJECT_DIR / "reference_audio.wav"

    if not ref_audio.exists():
        print(f"\n   ATTENTION: Pas d'audio de reference trouve!")
        print(f"   Placez un fichier audio (3-10 sec) ici: {ref_audio}")
        print(f"   Puis relancez ce script.")
        print(f"\n   Creation d'un exemple avec VoiceDesign...")

        # Creer un audio de reference avec VoiceDesign
        design_model = load_model(VOICE_DESIGN_MODEL, "VoiceDesign")
        if design_model:
            ref_text = "Bonjour, je suis un vieux sorcier sage qui connait les secrets de la magie."
            ref_instruct = "Homme age, 70 ans, voix grave et rocailleuse avec sagesse."

            wavs, sr = design_model.generate_voice_design(
                text=ref_text,
                language="French",
                instruct=ref_instruct
            )
            sf.write(str(ref_audio), wavs[0], sr)
            print(f"   Audio de reference cree: {ref_audio}")

            # Creer le prompt de clonage
            print("\n   Creation du prompt de clonage...")
            clone_prompt = model.create_voice_clone_prompt(
                ref_audio=(wavs[0], sr),
                ref_text=ref_text
            )

            # Generer des dialogues avec la voix clonee
            print("\n--- Dialogues avec la voix clonee ---")
            dialogues = [
                "Le chemin de la magie est long et perilleux, mon enfant.",
                "En sept cents ans de vie, j'ai appris que la patience est la plus grande des vertus.",
                "Mefie-toi de la foret sombre qui se trouve a l'est du royaume.",
            ]

            for i, texte in enumerate(dialogues):
                print(f"   Replique {i+1}...")
                wavs, sr = model.generate_voice_clone(
                    text=texte,
                    language="French",
                    voice_clone_prompt=clone_prompt
                )
                save_audio(wavs, sr, f"clone_sorcier_{i+1}", f"Replique {i+1}")
    else:
        print(f"   Audio de reference trouve: {ref_audio}")
        print("   IMPORTANT: Modifiez ref_text avec la transcription exacte!")

        ref_text = "Transcription exacte de votre audio de reference ici."

        # Clonage avec l'audio fourni
        textes = [
            "Ceci est un test de clonage vocal en francais.",
            "Le temps aujourd'hui est magnifique.",
            "Cette technologie est vraiment impressionnante.",
        ]

        for i, texte in enumerate(textes):
            print(f"   Generation {i+1}...")
            wavs, sr = model.generate_voice_clone(
                text=texte,
                language="French",
                ref_audio=str(ref_audio),
                ref_text=ref_text
            )
            save_audio(wavs, sr, f"clone_custom_{i+1}", f"Clone {i+1}")

    return model


# ==============================================================================
# PARTIE 4: WORKFLOW CONCEPTION + CLONAGE
# ==============================================================================

def demo_design_then_clone():
    """Workflow: concevoir une voix puis la cloner."""
    print("\n" + "=" * 60)
    print("PARTIE 4: WORKFLOW CONCEPTION + CLONAGE")
    print("=" * 60)
    print("1. Concevoir une voix avec VoiceDesign")
    print("2. Creer un prompt de clonage")
    print("3. Generer plusieurs repliques")

    # Charger VoiceDesign
    design_model = load_model(VOICE_DESIGN_MODEL, "VoiceDesign")
    if design_model is None:
        return

    # Etape 1: Concevoir la voix
    print("\n--- Etape 1: Conception de la voix ---")
    character_instruct = "Femme, 25 ans, voix enjouee et petillante. Parle avec enthousiasme comme une YouTubeuse."
    reference_text = "Salut tout le monde ! Bienvenue sur ma chaine ! Aujourd'hui on va parler de quelque chose de genial !"

    ref_wavs, sr = design_model.generate_voice_design(
        text=reference_text,
        language="French",
        instruct=character_instruct
    )
    ref_path = OUTPUTS_DIR / "youtubeuse_reference.wav"
    sf.write(str(ref_path), ref_wavs[0], sr)
    print(f"   Reference creee: {ref_path}")

    # Liberer la memoire
    del design_model
    torch.mps.empty_cache() if torch.backends.mps.is_available() else None

    # Charger le modele de clonage
    clone_model = load_model(BASE_MODEL, "Base 1.7B")
    if clone_model is None:
        print("   Modele Base non disponible, fin du workflow.")
        return

    # Etape 2: Creer le prompt de clonage
    print("\n--- Etape 2: Creation du prompt de clonage ---")
    clone_prompt = clone_model.create_voice_clone_prompt(
        ref_audio=(ref_wavs[0], sr),
        ref_text=reference_text
    )
    print("   Prompt de clonage cree!")

    # Etape 3: Generer les repliques
    print("\n--- Etape 3: Generation des repliques ---")
    repliques = [
        "N'oubliez pas de vous abonner et d'activer la cloche !",
        "Laissez-moi un commentaire pour me dire ce que vous en pensez !",
        "On se retrouve dans la prochaine video, bisous !",
        "Aujourd'hui je vais vous montrer mes 10 astuces preferees.",
    ]

    for i, replique in enumerate(repliques):
        print(f"   Replique {i+1}...")
        wavs, sr = clone_model.generate_voice_clone(
            text=replique,
            language="French",
            voice_clone_prompt=clone_prompt
        )
        save_audio(wavs, sr, f"youtubeuse_replique_{i+1}", f"Replique {i+1}")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     QWEN3-TTS DEMO AVANCEE                               ║
    ╠══════════════════════════════════════════════════════════╣
    ║  - VoiceDesign: Concevez des voix par description        ║
    ║  - CustomVoice 1.7B: Controlez emotions et styles        ║
    ║  - Voice Clone: Clonez n'importe quelle voix             ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    print("MODELES REQUIS (voir DOWNLOAD_MODELS.md):")
    print(f"  - VoiceDesign:    {VOICE_DESIGN_MODEL}")
    print(f"  - CustomVoice:    {CUSTOM_VOICE_1_7B_MODEL}")
    print(f"  - Base (Clone):   {BASE_MODEL}")

    # Menu de selection
    print("\n" + "=" * 60)
    print("CHOISISSEZ UNE DEMO:")
    print("  1 - VoiceDesign (conception de voix)")
    print("  2 - CustomVoice 1.7B (controle emotions)")
    print("  3 - Voice Clone (clonage vocal)")
    print("  4 - Workflow complet (conception + clonage)")
    print("  5 - Toutes les demos")
    print("=" * 60)

    choix = input("\nVotre choix (1-5): ").strip()

    if choix == "1":
        demo_voice_design()
    elif choix == "2":
        demo_custom_voice_instructions()
    elif choix == "3":
        demo_voice_clone()
    elif choix == "4":
        demo_design_then_clone()
    elif choix == "5":
        demo_voice_design()
        torch.mps.empty_cache() if torch.backends.mps.is_available() else None
        demo_custom_voice_instructions()
        torch.mps.empty_cache() if torch.backends.mps.is_available() else None
        demo_voice_clone()
    else:
        print("Choix invalide. Lancement de la demo VoiceDesign par defaut.")
        demo_voice_design()

    print("\n" + "=" * 60)
    print("DEMO TERMINEE!")
    print(f"Fichiers audio dans: {OUTPUTS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
