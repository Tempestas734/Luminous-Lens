# Luminous Lens

Luminous Lens est une application web Flask pour importer, visualiser et explorer des fichiers DICOM directement dans le navigateur.

L'application est orientee autour d'un viewer image en premier, avec fenetrage, navigation par coupes, consultation des tags DICOM et gestion d'une archive locale.

## Fonctionnalites

- Import de fichiers `.dcm` et `.dicom`
- Validation basique des fichiers DICOM au moment de l'upload
- Viewer image avec affichage direct apres import
- Fenetrage `Window Center / Window Width`
- Prise en charge des DICOM multi-coupes / multi-frames
- Fenetrage par coupe lorsque les metadonnees DICOM le fournissent
- Navigation par coupe avec slider
- Lecture automatique des coupes avec vitesses `0.5x`, `1x`, `2x`, `3x`
- Zoom, deplacement et affichage adapte a la zone visible
- Vue metadata / tags avec recherche
- Archive locale avec miniatures
- Suppression d'une selection d'etudes dans l'archive
- Suppression complete de l'archive
- Import direct depuis la page archive
- Gestion de session avec limite de stockage

## Stack Technique

- Backend: Flask
- Traitement DICOM: `pydicom`
- Image: `Pillow`, `numpy`
- Frontend: HTML, Tailwind CSS, JavaScript

## Installation

1. Creer un environnement virtuel:

```bash
python -m venv .venv
```

2. Activer l'environnement:

Windows:

```bash
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

3. Installer les dependances:

```bash
pip install -r requirements.txt
```

## Lancement

Option 1:

```bash
python app.py
```

Option 2 sous Windows:

```bash
run_app.bat
```

Puis ouvrir:

```text
http://127.0.0.1:5000
```

## Utilisation

1. Importer un fichier DICOM depuis la page d'accueil ou l'archive.
2. L'image s'ouvre directement dans le viewer.
3. Ajuster le fenetrage avec les sliders.
4. Si le fichier contient plusieurs coupes, naviguer avec le slider ou lancer la lecture automatique.
5. Ouvrir la vue tags pour consulter les metadonnees DICOM.
6. Utiliser l'archive pour rouvrir, selectionner ou supprimer des etudes.

## Structure Du Projet

```text
tp/
|-- app.py
|-- run_app.bat
|-- requirements.txt
|-- README.md
|-- static/
|   |-- app.js
|   |-- style.css
|   `-- tailwind-config.js
|-- templates/
|   |-- base.html
|   |-- index.html
|   |-- image_view.html
|   |-- recent.html
|   |-- view.html
|   |-- _footer.html
|   `-- _navbar.html
`-- uploads/
```

## Notes Importantes

- Les fichiers sont stockes localement dans le dossier `uploads/`.
- L'archive actuelle est locale au projet.
- La session applique une limite de stockage de 2 GB.
- L'application reduit la taille de rendu web pour limiter l'usage memoire.
- Les valeurs de tags tres longues ou binaires sont tronquees / resumees dans la vue metadata.

## Limites

- Cette application n'est pas un dispositif medical.
- Le viewer est adapte a de l'exploration et de la demonstration, pas a un usage clinique certifie.
- Le rendu depend de la qualite et de la structure des metadonnees DICOM fournies par le fichier.

## Avertissement

Ce projet est destine a l'apprentissage, a l'experimentation et a la visualisation technique. Ne pas l'utiliser comme outil de diagnostic clinique sans validation reglementaire appropriee.
