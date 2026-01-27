Sam Witteveen
## Sources : 
Vidéo : https://www.youtube.com/watch?v=jZ8wPB-KI8g
Blog : https://qwen.ai/blog?id=qwen3tts-0115
Colab Basic : https://colab.research.google.com/drive/1JUYT9xAistnOwMOtIPTP-E-upo4te8Qj?usp=sharing
Colab Voice Cloning : https://colab.research.google.com/drive/1Vv99jmgfzu-pHwpkLawWY8iIpb5FBwru?usp=sharing
Demo :  https://huggingface.co/spaces/Qwen/Qwen3-TTS-Demo
Models : https://huggingface.co/collections/Qwen/qwen3-tts

---
# Qwen 3 TTS : Clonez n'importe quelle voix gratuitement

## Résumé exécutif

Ce document synthétise une vidéo de démonstration des nouveaux modèles **Qwen 3 TTS** (Text-to-Speech) récemment rendus open source par l'équipe Qwen/Alibaba. Ces modèles permettent la génération vocale, le **clonage de voix** et le **design vocal** — des fonctionnalités jusqu'ici réservées aux API propriétaires d'OpenAI et Google.

> **Note** : Cette vidéo est la **première d'une série de 2-3 vidéos** couvrant l'explosion récente des modèles TTS open source. Les prochaines vidéos aborderont d'autres modèles TTS et les **modèles Omni** émergents.
---
## 1. Historique et annonces

### 1.1 Chronologie des versions

| Date | Annonce |
|------|---------|
| Juin (année précédente) | Première annonce de Qwen TTS |
| Septembre | Qwen 3 TTS Flash avec support multilingue |
| Décembre | Support de **10 langues**, **9 dialectes**, **49 timbres vocaux** |
| Décembre (suite) | Annonce du clonage vocal et du design vocal |
| **Récemment** | **Open source complet** de la famille Qwen 3 TTS |

### 1.2 Problème initial

Avant l'ouverture du code source, ces modèles n'étaient accessibles que via :
- L'API Qwen
- Des fournisseurs tiers

**L'open source change la donne** : téléchargement et utilisation locale désormais possibles.
### 1.3 Contexte historique : autres acteurs

D'autres entreprises comme **Qtai** avaient développé de bons modèles TTS avec des fonctionnalités similaires, mais lors de la publication de leurs versions open source, elles ont **verrouillé les fonctionnalités avancées** en ne proposant que des voix prédéfinies. Qwen offre ici "le meilleur des deux mondes" : voix prédéfinies ET fonctionnalités avancées.

---

## 2. Architecture des modèles

### 2.1 Deux tailles de modèles

| Modèle | Taille | Caractéristiques |
|--------|--------|------------------|
| **0.6B** | 600 millions de paramètres | Voix prédéfinies, 10 langues, streaming |
| **1.7B** | 1,7 milliard de paramètres | Tout le 0.6B + clonage vocal + design vocal + contrôle par instructions |

> **Note importante** : Ces tailles restent relativement modestes et permettent une exécution sur matériel grand public.

### 2.2 Modèles disponibles sur Hugging Face

1. **Modèle de base 0.6B** — pour fine-tuning
2. **Modèle de base 1.7B** — pour fine-tuning
3. **Modèles Custom Voice** — voix personnalisées
4. **Modèle Voice Design** — conception de voix

### 2.3 Innovation : modèles de base ouverts

L'équipe Qwen a publié les **modèles de base** (non fine-tunés), permettant :
- Le fine-tuning pour sa propre voix
- L'adaptation potentielle à de nouvelles langues/dialectes
- L'accès aux tokenizers et codebooks

> Cette ouverture est particulièrement importante pour les utilisateurs dont la langue ou le dialecte n'est pas supporté nativement.

---

## 3. Fonctionnalités principales

### 3.1 Génération TTS standard

- **10 langues supportées**
- **49 voix prédéfinies** avec descriptions et langues natives
- Support des dialectes (notamment chinois)
- Génération par lot (batch inference)
- Génération de textes longs
#### Demo multi-speaker

Possibilité de comparer facilement plusieurs voix côte à côte pour choisir celle qui convient le mieux à un projet.
### 3.2 Clonage vocal (Voice Cloning)

**Principe** : Fournir un court échantillon audio (~10 secondes) pour que le modèle reproduise cette voix.

**Cas d'usage** :
- Parler une langue étrangère avec sa propre voix
- Créer du contenu audio personnalisé
- Doublage et localisation

**Qualité** : Décrite comme "très impressionnante" pour un système open source, bien que "pas totalement parfaite".

#### Exemples de phrases clonées (démo)

- *"The weather today is absolutely beautiful. I think I'll go for a walk in the park."*
- *"This is a demonstration of voice cloning technology. Pretty impressive, right?"*
- *"First, let me tell you about the basics. Second, we'll dive into the details. Third, we'll look at some examples. Finally, we'll wrap everything up."*

### 3.3 Design vocal (Voice Design)

**Principe** : Décrire textuellement la voix souhaitée via un prompt d'instruction.

**Exemples de prompts testés** :

| Type de voix | Description du prompt | Résultat | Phrase exemple |
|--------------|----------------------|----------|----------------|
| Anime | "Jeune voix d'anime, énergique et mignonne" | Voix cartoon | *"Hello everyone, I'm so excited to meet you."* |
| Documentaire | "Voix de documentaire style narrateur" | Voix narrative profonde | *"In the depths of the ocean, where sunlight cannot reach, lies a world of extraordinary creatures."* |
| Méchant | "Voix de villain menaçant" | Voix sinistre | *"You thought you could escape. How delightfully naive. The game has only just begun."* |
| Sage ancien | "Vieux sage mystérieux, 700 ans" | Voix grave et posée | *"Ah, young one, you seek knowledge of the ancient arts. Very well."* / *"In my 700 years of existence, I have learned that patience is the greatest virtue."* |

**Limitation** : Les noms de célébrités ne fonctionnent pas directement (ex: "David Attenborough voice" seul ne produit pas sa voix réelle), probablement par choix délibéré ou manque de données d'entraînement associées.

> **Astuce** : On peut contourner cette limitation en utilisant le **clonage vocal** avec un échantillon audio de la célébrité (avec permission), ou en **fine-tunant** le modèle.

### 3.4 Workflow combiné : Voice Design → Clonage

Une technique puissante consiste à :
1. **Créer** une voix via Voice Design (avec un prompt descriptif)
2. **Générer** un échantillon audio avec cette voix
3. **Cloner** cet échantillon pour une utilisation simplifiée ultérieure

Cela permet de "figer" une voix conçue pour la réutiliser facilement.

### 3.5 Contrôle émotionnel et stylistique

Le modèle permet de moduler la **prosodie** (intonation, rythme, accentuation) :

| Catégorie | Options |
|-----------|---------|
| **Émotions** | Joie, tristesse, colère, neutre |
| **Styles** | Chuchotement, voix forte, douce, dramatique |
| **Scénarios** | Dialogues, narration, etc. |

#### Exemples de phrases avec styles (démo)

| Style | Phrase |
|-------|--------|
| Émotions variées | *"I just found out the news about what happened yesterday."* |
| Chuchotement/Fort/Dramatique | *"Please be quiet. The baby is sleeping."* |

#### Observations sur la qualité

- Les **émotions** peuvent être "un peu over the top" (exagérées)
- La voix **Ryan** semble parfois "lazy" (paresseuse/monotone)
- La **prosodie** est globalement bien rendue

### 3.6 Compréhension intelligente du texte

Grâce à l'entraînement sur le modèle Qwen 3 (LLM), le TTS sait prononcer :
- Formules LaTeX
- Adresses email
- Nombres et dates
- Symboles spéciaux

**Pas besoin d'écriture phonétique explicite.**

#### Exemples de prononciation (démo)

| Type | Texte | Observation |
|------|-------|-------------|
| Nombre scientifique | *"The speed of light is approximately 299,792,458 meters per second."* | Pas parfait mais correct |
| Date/Heure | *"The meeting is scheduled for March 15th, 2025 at 3:30 p.m."* | Bien prononcé |

> **Note** : Quelques imperfections subsistent sur la prononciation des grands nombres.

### 3.7 Code-switching automatique

Détection automatique de la langue pour gérer les passages multilingues dans un même texte.

---

## 4. Aspects techniques

### 4.1 Évolution historique du TTS

Le présentateur mentionne son expérience personnelle :

> *"I first started working on training up TTS models about nine years ago"*

#### Référence historique : Tacotron et R9Y9

- **Tacotron** : Modèle state-of-the-art il y a ~10 ans
- **R9Y9** : Développeur ayant créé un excellent repo d'apprentissage sur Tacotron (travaillait chez **Line** au Japon)
- À l'époque : systèmes basés sur la **phonétique pure** et les **codebooks**

### 4.2 Architecture end-to-end

Contrairement aux anciens systèmes TTS qui assemblaient plusieurs composants :
- Encodeur
- Décodeur
- Vocoder

**Qwen 3 TTS** utilise une architecture **entièrement end-to-end** avec :
- Tokens textuels
- Tokens codec
- Tokens de "réflexion" (thinking tokens)
- Embeddings de locuteurs
- Décodeur streaming

> Avant, on assemblait des pièces de différents modèles ("plug and play"). Maintenant, tout est entraîné de bout en bout.

### 4.3 Données d'entraînement

> **Plus de 5 millions d'heures de données vocales**

### 4.4 Évaluation et benchmarks

#### Mean Opinion Score (MOS)

Métrique historique pour évaluer les systèmes TTS :
- Test humain : "Cette voix semble-t-elle réelle ?"
- Score basé sur l'opinion moyenne des évaluateurs

> *"I'm actually not even sure how you measure these things [nowadays]"* — Le présentateur note que l'évaluation a évolué vers des benchmarks multi-tâches.

#### Performances revendiquées

Qwen affirme que ce modèle atteint l'**état de l'art** sur de nombreux benchmarks de :
- Clonage vocal
- Design vocal

---

## 5. Utilisation pratique

### 5.1 Installation

```bash
# Installation du package Qwen TTS
pip install qwen-tts
```

### 5.2 Matériel requis

| Composant | Recommandation |
|-----------|----------------|
| **GPU** | L4 ou équivalent |
| **VRAM** | Modeste (les modèles sont légers) |

### 5.3 Deux notebooks Colab distincts

| Notebook | Modèle | Fonctionnalités |
|----------|--------|-----------------|
| **Colab 1** | 0.6B | Génération basique, voix prédéfinies, multilingue |
| **Colab 2** | 1.7B | Voice Design, Voice Cloning, contrôle émotionnel |

### 5.4 Exemples de code

#### Génération simple (0.6B)

```python
# Génération basique avec voix prédéfinie
generate_speech(
    text="Hello, welcome to the Qwen 3 text-to-speech demonstration.",
    speaker="Ryan",
    language="en"
)
```

#### Voice Design (1.7B)

```python
# Conception de voix via instruction
generate_speech(
    text="Hello everyone, I'm so excited to meet you.",
    instruction="A young anime voice, energetic and cute"
)
```

#### Voice Cloning (1.7B)

```python
# Clonage à partir d'un échantillon audio (~10 secondes)
generate_speech(
    text="The weather today is absolutely beautiful.",
    voice_sample="my_voice_10sec.wav"
)
```

### 5.5 Ressources disponibles

| Ressource | Description | Limitations |
|-----------|-------------|-------------|
| **Hugging Face Collection** | Tous les modèles Qwen 3 TTS | — |
| **Hugging Face Space** | Démo interactive | ⚠️ **Pas de clonage vocal** |
| **Google Colab** | Notebooks pour tester les modèles | — |
| **Paper** | Article scientifique détaillant l'architecture | — |

---

## 6. Langues et voix supportées

### 6.1 Langues (10 au total)

- Anglais
- Chinois (plusieurs dialectes)
- Allemand
- Français
- Espagnol
- Japonais
- Coréen
- Et autres...

### 6.2 Qualité par langue

| Langue | Qualité | Notes |
|--------|---------|-------|
| Anglais | ⭐⭐⭐⭐⭐ | Excellente |
| Chinois | ⭐⭐⭐⭐⭐ | Excellente avec dialectes |
| Allemand | ⭐⭐⭐⭐ | Bonne |
| Français | ⭐⭐⭐⭐ | Bonne |
| Espagnol | ⭐⭐⭐ | Quelques artefacts audio détectés |
| Japonais | ⭐⭐⭐⭐ | Très bon, accents pas parfaits |
| Coréen | ⭐⭐⭐⭐ | Très bon, accents pas parfaits |

### 6.3 Cross-lingual

Une voix native d'une langue peut parler dans une autre langue tout en conservant certaines caractéristiques de son timbre (avec accent).

#### Exemples démontrés

| Voix | Langue originale | Langue parlée | Phrase |
|------|------------------|---------------|--------|
| Voix chinoise | Chinois | Anglais | *"Hi there. I can speak English too."* |
| Voix chinoise | Chinois | Allemand | *"Hallo. Ich kann auch Deutsch sprechen."* |
| Ryan | Anglais | Allemand | *"Guten Morgen. Wie geht es Ihnen heute?"* |
| Ryan | Anglais | Français | *"Bonjour. Comment allez-vous aujourd'hui?"* |
| Ryan | Anglais | Espagnol | *"Buenos días. ¿Cómo está usted hoy?"* |

---

## 7. Comparaison avec les solutions existantes

| Critère | OpenAI / Google | Qwen 3 TTS |
|---------|-----------------|------------|
| **Accès** | API payante uniquement | Open source |
| **Clonage vocal** | Restreint/contrôlé | ✅ Disponible |
| **Voice design** | Limité | ✅ Disponible |
| **Coût** | Par utilisation | Gratuit (compute local) |
| **Personnalisation** | Impossible | ✅ Fine-tuning possible |
| **Célébrités** | Possible (données massives) | ❌ Non supporté directement |
| **Modèles de base** | Non disponibles | ✅ Ouverts |

---

## 8. Perspectives et évolutions

### 8.1 Versions futures attendues

- **MLX** : Optimisation pour Apple Silicon
- **ONNX** : Portabilité multi-plateforme
- **Versions mobiles** : Exécution on-device/edge (téléphones)

### 8.2 Potentiel de fine-tuning

Possibilité d'entraîner le modèle pour :
- De nouvelles langues non supportées
- Des dialectes spécifiques
- Une voix personnelle parfaitement reproduite
- Reproduction de voix célèbres (avec permission)

### 8.3 Écosystème TTS en expansion

> *"The Open TTS world has just exploded over the past month or so"*

Vidéos suivantes prévues sur :
- Autres modèles TTS open source
- **Modèles Omni** (multimodaux)

---

## 9. Considérations éthiques

### 9.1 Risques identifiés

- Usurpation d'identité vocale
- Deepfakes audio
- Désinformation

### 9.2 Mesures de Qwen

- Pas de reproduction directe de voix de célébrités via prompt textuel
- Publication responsable avec documentation

### 9.3 Débat historique

> *"The debate has always been that all those features are too dangerous."*

OpenAI et Google ont été très prudents sur l'accès à ces fonctionnalités. Qwen a choisi une approche plus ouverte, offrant les fonctionnalités avancées tout en limitant certains abus (pas de noms de célébrités).

---

## 10. Observations et retours d'expérience

### 10.1 Points forts observés

- Qualité générale impressionnante pour l'open source
- Facilité d'utilisation via les notebooks
- Flexibilité (voix prédéfinies + design + clonage)
- Multilingue efficace

### 10.2 Points d'amélioration notés

| Observation | Détail |
|-------------|--------|
| Voix Ryan | Parfois "lazy" (manque d'énergie) |
| Émotions | Tendance à être "over the top" (exagérées) |
| Espagnol | Artefacts audio détectés |
| Grands nombres | Prononciation parfois imparfaite |
| Chuchotement | Pas toujours convaincant selon les voix |

### 10.3 Note sur la confusion IA

> Le présentateur mentionne que certains spectateurs pensent que ses vidéos sont générées par IA. Cela est dû à un **problème de réduction de bruit dans Descript** qui "coupe" certaines fréquences de sa voix. Il travaille actuellement sur sa propre application type Descript pour résoudre ce problème.

---

## 11. Conclusion

Qwen 3 TTS représente une **avancée majeure** dans le domaine du TTS open source :

| Avantage | Description |
|----------|-------------|
| **Accessibilité** | Modèles téléchargeables et utilisables localement |
| **Fonctionnalités** | Clonage et design vocal accessibles à tous |
| **Qualité** | Proche de l'état de l'art commercial |
| **Flexibilité** | Modèles de base ouverts pour fine-tuning |
| **Multilingue** | 10 langues et 9 dialectes supportés |

Cette ouverture "change tout" pour les développeurs et créateurs de contenu souhaitant intégrer des capacités TTS avancées sans dépendre d'API propriétaires.

---

## Annexe A : Exemples de phrases démontrées

### Génération basique

| Voix | Langue | Phrase |
|------|--------|--------|
| Ryan | EN | *"Hello, welcome to the Qwen 3 text-to-speech demonstration. This model can generate natural expressive speech in multiple languages."* |
| Multi | EN | *"The quick brown fox jumps over the lazy dog."* |

### Multilingue

| Phrase | Langue |
|--------|--------|
| *"Guten Morgen. Wie geht es Ihnen heute?"* | Allemand |
| *"Bonjour. Comment allez-vous aujourd'hui?"* | Français |
| *"Buenos días. ¿Cómo está usted hoy?"* | Espagnol |

### Textes techniques

| Type | Phrase |
|------|--------|
| Nombre | *"The speed of light is approximately 299,792,458 meters per second."* |
| Date | *"The meeting is scheduled for March 15th, 2025 at 3:30 p.m."* |

---

## Annexe B : Liens et ressources

| Ressource | Description |
|-----------|-------------|
| Hugging Face | Collection Qwen 3 TTS |
| Paper scientifique | Architecture et méthodologie |
| Google Colab #1 | Notebook modèle 0.6B |
| Google Colab #2 | Notebook modèle 1.7B (cloning + design) |
| Hugging Face Spaces | Démo interactive (sans clonage) |

---

## Annexe C : Glossaire

| Terme | Définition |
|-------|------------|
| **TTS** | Text-to-Speech (synthèse vocale) |
| **Voice Cloning** | Reproduction d'une voix à partir d'un échantillon audio |
| **Voice Design** | Création d'une voix à partir d'une description textuelle |
| **Prosodie** | Ensemble des variations d'intonation, de rythme et d'accentuation |
| **MOS (Mean Opinion Score)** | Métrique d'évaluation basée sur l'opinion humaine |
| **Codebook** | Dictionnaire de représentations audio utilisé dans les systèmes TTS |
| **End-to-end** | Architecture où tout le système est entraîné comme un bloc unique |
| **Fine-tuning** | Réentraînement partiel d'un modèle pour une tâche spécifique |
| **Code-switching** | Alternance entre plusieurs langues dans un même énoncé |


---

# Tutoriel : Cloner n'importe quelle voix avec Qwen3-TTS

La série de modèles **Qwen3-TTS** d'Alibaba vient de passer en **open source**, marquant une révolution dans le monde de la synthèse vocale (TTS). Contrairement aux solutions fermées comme OpenAI ou Gemini, vous pouvez désormais télécharger ces modèles et les faire tourner localement ou sur le cloud pour du design vocal et du clonage précis.

---

## Sommaire

1. [Introduction et Contexte](https://www.google.com/search?q=%23introduction)
2. [Aperçu des Modèles Qwen3-TTS](https://www.google.com/search?q=%23mod%C3%A8les)
3. [Architecture et Capacités](https://www.google.com/search?q=%23architecture)
4. [Démarrage Rapide (Modèle 0.6B)](https://www.google.com/search?q=%23demo-basique)
5. [Fonctionnalités Avancées (Modèle 1.7B)](https://www.google.com/search?q=%23demo-avancee)
6. [Clonage de Voix Pas à Pas](https://www.google.com/search?q=%23clonage)

---

<a name="introduction"></a>

## 1. Introduction et Contexte

Jusqu'à récemment, les capacités avancées de clonage de voix étaient limitées à des API payantes. Avec l'ouverture de Qwen3-TTS, l'écosystème open source dispose enfin d'un système **end-to-end** capable de rivaliser avec les meilleurs.

- **Blog officiel :** [qwen.ai/blog](https://qwen.ai/blog?id=qwen3tts-0115)
    
- **Démo Hugging Face :** [Qwen3-TTS-Demo](https://huggingface.co/spaces/Qwen/Qwen3-TTS-Demo)
    

---

## 2. Aperçu des Modèles Qwen3-TTS

Il existe deux tailles principales de modèles:

|**Modèle**|**Taille**|**Usage Principal**|
|---|---|---|
|**Qwen3-TTS-0.6B**|Petit (0.6Md)|Streaming rapide, voix prédéfinies, support de 10 langues.|
|**Qwen3-TTS-1.7B**|Moyen (1.7Md)|**Clonage de voix**, design vocal par instructions, émotions.|

> **Note :** Même le modèle 1.7B reste relativement léger et peut tourner sur des GPU grand public ou des instances Colab gratuites.

---
## 3. Architecture et Capacités

Qwen3-TTS se distingue des anciens modèles comme _Tacotron_ (utilisé il y a 10 ans) par son approche moderne:

- **Système End-to-End :** Le texte est transformé directement en audio via des tokens de texte, de codec et des "thinking tokens".
    
- **Intelligence Linguistique :** Grâce à son pré-entraînement sur de larges corpus textuels, le modèle sait prononcer nativement le **LaTeX**, les symboles et les adresses email sans avoir besoin de transcription phonétique manuelle.
    
- **Données massives :** Entraîné sur plus de **5 millions d'heures** de données vocales.
    

---

## 4. Démarrage Rapide : Text-to-Speech Basique (0.6B)

Utilisez ce Colab pour tester les voix prédéfinies : [Colab Basic](https://colab.research.google.com/drive/1JUYT9xAistnOwMOtIPTP-E-upo4te8Qj?usp=sharing)
### Étapes clés :

1. **Installation :** Installez le package Qwen3-TTS.
2. **Chargement :** Chargez le modèle `0.6B`.
3. **Synthèse simple :** Choisissez un locuteur (ex: "Ryan" pour l'anglais).
4. **Multilingue :** Vous pouvez faire parler un locuteur natif chinois en anglais ou en allemand avec un accent naturel.
5. **Inférence par lots (Batch) :** Idéal pour générer de longs textes rapidement en traitant plusieurs phrases simultanément.
    

---

<a name="demo-avancee"></a>

## 5. Fonctionnalités Avancées (Modèle 1.7B)

Le modèle 1.7B permet de "designer" une voix par simple description textuelle.

[Colab Voice Cloning & Design](https://colab.research.google.com/drive/1Vv99jmgfzu-pHwpkLawWY8iIpb5FBwru?usp=sharing)

### Voice Design par Instructions

Au lieu de choisir une voix fixe, vous envoyez une instruction :

- _Exemple 1 :_ "A young anime voice" (Voix d'anime jeune) ➔ Résultat cartoon.
- _Exemple 2 :_ "A documentary voice" ➔ Résultat calme et profond.
- _Exemple 3 :_ "A villain voice" ➔ Résultat dramatique et menaçant.

### Contrôle des Émotions et du Style

Vous pouvez modifier la prosodie (l'intonation) en ajoutant des tags d'émotion :

- **Émotions :** Triste, joyeux, neutre.
    
- **Styles :** Chuchotement (_whispering_), voix forte, dramatique.
    

---
## 6. Clonage de Voix Pas à Pas

C'est la fonctionnalité la plus impressionnante : reproduire une voix réelle à partir d'un court échantillon audio.
### Procédure :
1. **Préparation :** Munissez-vous d'un fichier audio (WAV ou MP3) de la voix à cloner (environ 10 à 30 secondes suffisent).
2. **Extraction :** Le modèle extrait une représentation (embedding) du locuteur.
3. **Génération :** Saisissez le texte que vous souhaitez faire dire à cette voix.
4. **Résultat :** Le modèle génère un nouvel audio avec le timbre et les inflexions de l'échantillon original.

> **Astuce de Sam Witteveen :** Vous pouvez même cloner une voix "designée" par instruction pour la réutiliser plus tard comme référence stable.

---
Prochaines étapes

- Explorez les **modèles sur Hugging Face** pour voir la collection complète : [Qwen3-TTS Collection](https://huggingface.co/collections/Qwen/qwen3-tts).
- Attendez-vous à des versions optimisées (**ONNX** ou **MLX**) pour faire tourner ces modèles sur smartphone ou appareils légers très prochainement.


