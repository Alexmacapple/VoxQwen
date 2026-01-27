## Liens et Ressources
- **Vidéo Source :** [Neural Falcon - Run Qwen3-TTS Locally](https://www.youtube.com/watch?v=FcNSdGY6Kj8)
- **Dépôt GitHub Local :** [NeuralFalcon/Qwen3-TTS-Local](https://www.google.com/url?sa=E&source=gmail&q=https://github.com/NeuralFalcon/Qwen3-TTS-Local)
- **Google Colab :** [Qwen3-TTS-Colab](https://github.com/NeuralFalconYT/Qwen3-TTS-Colab
- **Hugging Face :** [Qwen3-TTS Space](https://huggingface.co/spaces/Qwen/Qwen3-TTS)
## Prérequis Système
Avant de commencer, les outils suivants doivent être installés :
- **Python 3.10** (Impératif pour la compatibilité des bibliothèques).
- **Git** (Pour la gestion du code source).
- **NVIDIA GPU** (Indispensable pour le traitement IA).
- **Visual Studio Community** (Avec les outils de développement C++).
## 1. Installation technique
### A. Clonage et environnement
Ouvrez votre terminal dans le dossier de destination et exécutez :
```
git clone https://github.com/NeuralFalcon/Qwen3-TTS-Local
cd Qwen3-TTS-Local
python -m venv venv
venv\Scripts\activate
```
### B. Installation de PyTorch (CUDA)
Vérifiez votre version via `nvidia-smi`.
- **Pour CUDA 11.8 :**
> pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

- **Pour CUDA 12.x :**
> pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
### C. Dépendances et Corrections
Installez les bibliothèques principales puis appliquez le correctif pour CTranslate2 :
```
pip install -r requirements.txt
pip uninstall ctranslate2 -y
pip install ctranslate2==3.24.0
```
## 2. Configuration de l'Interface (UI)

Le logiciel propose trois fonctionnalités majeures :
### Voice Design (1.7B)
Génère une voix à partir d'une description textuelle. Requiert une puissance de calcul importante.
### Voice Cloning (Clonage)
Permet d'imiter une voix cible. Vous devez fournir un échantillon audio (référence) de 10 à 30 secondes.
- Utilisez le modèle **1.7B** pour la qualité.
- Utilisez le modèle **0.6B** pour la rapidité ou les petites configurations.
### Text-to-Speech (Custom Voice)
Transforme le texte en parole.
- **SentenceX :** Découpe automatiquement les longs textes pour éviter les saturations de mémoire.
- **Whisper :** Utilisé pour transcrire automatiquement vos fichiers de référence.
## 3. Optimisation selon le Matériel
### Configuration Modeste (4 Go VRAM)
- Utilisez exclusivement les modèles **0.6 Billion**.
- Ne cochez pas l'option **Generate Subtitle** pour éviter les plantages.
- Privilégiez l'utilisation de textes courts ou moyennement longs.
### Configuration Haute Performance (8 Go+ VRAM)
- Utilisez les modèles **1.7 Billion**.
- Vous pouvez activer la génération de sous-titres et le "Voice Design".
- **Flash Attention :** Installez ce module pour accélérer le rendu :
> pip install flash-attn --no-build-isolation
## 4. Automatisation (Fichier .bat)
Pour lancer le programme sans terminal manuel, créez un fichier `run.bat` à la racine du projet :
Extrait de code
```
@echo off
cd /d "%~dp0"
call .\venv\Scripts\activate
python app.py
pause
```
## 5. Notes de dépannage
- **Premier Lancement :** Le téléchargement des modèles s'effectue automatiquement au premier démarrage. Cela peut durer 5 à 10 minutes selon votre connexion.
- **Vérification GPU :** En cas de doute, lancez cette commande dans l'environnement activé :
> python -c "import torch; print(torch.cuda.is_available())"`

Elle doit retourner `True`
- **Erreurs de mémoire :** Si le logiciel s'arrête brutalement, réduisez la taille du texte d'entrée ou passez sur un modèle 0.6B.
## 6. Compléments techniques
### Précision sur Visual Studio
L'installation de "Visual Studio Community" ne suffit pas seule. Lors de l'installation, vous devez impérativement cocher la charge de travail suivante :
- **Développement Desktop en C++** (Desktop development with C++) C'est ce module qui permet à Python de compiler les outils comme `flash-attn` ou certains composants de `ctranslate2`. Sans cela, l'étape V échouera.
### Le paramètre "Auto Transcribe"
Dans l'interface (Gradio), pour le clonage de voix :
- **Si activé :** Le logiciel utilise Whisper pour deviner ce qui est dit dans votre fichier audio de référence.
- **Si désactivé :** Vous devez taper manuellement le texte exact de l'audio de référence dans le champ prévu. _Note : L'auto-transcription est recommandée pour gagner du temps, mais consomme plus de VRAM._
### Sortie des fichiers (Output)
La vidéo ne montre pas où sont stockés les fichiers générés :
- Les audios se trouvent généralement dans un dossier nommé `outputs` ou `temp` créé à la racine du projet.
- Les sous-titres générés sont au format `.srt`.
## 7. Plan B : utilisation via Google Colab
Si votre matériel local (GPU) sature malgré les modèles 0.6B, la vidéo mentionne un lien Colab. Voici comment l'utiliser :
1. Ouvrez le lien : [NeuralFalconYT/Qwen3-TTS-Colab](https://github.com/NeuralFalconYT/Qwen3-TTS-Colab).
2. Cliquez sur le bouton "Open in Colab".
3. Allez dans le menu **Exécution > Modifier le type d'exécution** et vérifiez que **T4 GPU** est sélectionné.
4. Exécutez les cellules une par une (bouton "Play").
5. Une URL `gradio.live` apparaîtra à la fin pour ouvrir l'interface dans votre navigateur.
## 8. Résumé des erreurs fréquentes (Checklist de secours)

|**Erreur**|**Cause probable**|**Solution**|
|---|---|---|
|`NVIDIA-SMI is not recognized`|Pilotes NVIDIA non installés|Installer les derniers pilotes "Game Ready" ou "Studio".|
|`Error: No module named 'torch'`|Environnement virtuel non activé|Relancer `venv\Scripts\activate`.|
|`Out of Memory (OOM)`|Texte trop long ou modèle 1.7B|Passer au modèle 0.6B ou découper le texte.|
|`Microsoft Visual C++ 14.0 is required`|Visual Studio incomplet|Réinstaller VS avec l'option "Développement C++".|
## 9. Dépendance Système Invisible : FFmpeg
FFmpeg est un outil de traitement audio/vidéo indispensable qui ne s'installe pas via Python.
1. **Téléchargement :** Allez sur [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) et téléchargez `ffmpeg-git-full.7z`.
2. **Installation :** Extrayez le dossier, renommez-le `ffmpeg` et placez-le à la racine de votre disque (ex: `C:\ffmpeg`).
3. **Variable d'environnement :**
    - Recherchez "Modifier les variables d'environnement système" dans Windows.    
    - Dans "Variables système", modifiez `Path` et ajoutez `C:\ffmpeg\bin`.    
4. **Vérification :** Tapez `ffmpeg -version` dans un nouveau terminal. Si cela répond, le système peut traiter les fichiers audio.
## 10. Maintenance et Mise à jour
Le projet peut recevoir des améliorations. Pour mettre à jour votre installation sans tout réinstaller :
1. Ouvrez un terminal dans le dossier `Qwen3-TTS-Local`.
2. Tapez :
> git pull
>  .\venv\Scripts\activate
> pip install -r requirements.txt

## 11. Support des langues
Bien que l'interface soit en anglais, **Qwen3-TTS est multilingue**.
- Il supporte nativement le **français**, l'anglais, le chinois, le japonais et l'allemand.
- Pour le clonage, si vous parlez français dans l'audio de référence, le modèle détectera la langue (via Whisper) et pourra générer du texte en français avec votre timbre de voix.

