# Les mondes des animaux — Android

Projet Android natif en Kotlin, premier jalon du portage du projet Python.

## Ouvrir et lancer

1. Dans Android Studio, **Open** puis sélectionner ce dossier `android`.
2. Laisser la synchronisation Gradle se terminer. Utiliser le JDK intégré à Android Studio.
3. Installer le SDK **Android 16 / API 36** et les Build Tools **36.0.0** si Studio les demande.
4. Choisir un téléphone/tablette connecté ou un émulateur, puis **Run ▶**.

Android minimum : **8.0 / API 26**. Portrait, paysage et redimensionnement sont pris en charge.

Depuis PowerShell, dans ce dossier :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-local.ps1
```

Le script compile l’APK, lance les tests locaux et Android Lint. Il utilise le Java
d’Android Studio, range les caches dans des dossiers ignorés du projet et réutilise
la clé de débogage d’Android Studio si elle existe. L’option ExecutionPolicy concerne
seulement ce processus ; aucun réglage Windows permanent n’est changé.

APK installable : `app/build/outputs/apk/debug/app-debug.apk`.
Rapports : `app/build/reports/tests/testDebugUnitTest/index.html` et
`app/build/reports/lint-results-debug.html`.

## Fonctions disponibles

- **Nouveau monde** : nommer et créer un monde vide, enregistré sur l’appareil,
  sans dépendre d’aucune archive préexistante. Aussi disponible dans **Mes mondes**.
- Lecture directe des archives de la bibliothèque Python : `world.json`, `mer.zip`,
  `prairie.zip`, dessins PNG et métadonnées de squelette.
- Cinq mondes de développement embarqués ; le monde actif du projet Python est
  sélectionné au premier lancement.
- **Mes mondes → Importer un ZIP** : copie locale d’une archive de monde combiné,
  via le sélecteur de fichiers Android. Les ZIP des programmes mer/prairie seuls
  ne sont pas des mondes combinés.
- **Ajouter un animal** : photo ou import d’image, choix parmi les 22 espèces,
  cadrage tactile, rotation, détourage réglable, aperçu sur damier, inversion et
  taille de 25 à 200 %. L’ajout est sauvegardé automatiquement dans le monde courant.
  Les dessins et squelettes existants sont conservés sans réencoder leurs PNG.
- Défilement au doigt, zoom à deux doigts et boutons de zoom.
- Raccourcis **Mer**, **Plage**, **Prairie**, pause et balayages horizontal/vertical.
  La barre de boutons peut défiler horizontalement sur un petit écran.
- Mémorisation du monde courant, de la caméra, du zoom, de la pause et des balayages.
- Décors et dessins rendus avec Android Canvas ; déplacements et animations simples.
- Chargement hors du fil d’interface, erreurs récupérables, arrêt des animations
  lorsque l’application passe en arrière-plan.

Les mondes créés utilisent aussi le format ZIP Python, avec populations vides et
aperçu PNG. Les fichiers originaux sélectionnés dans le sélecteur Android ne sont
pas modifiés. Les ajouts modifient la copie privée du monde, après validation puis
remplacement atomique du ZIP. Un exemple embarqué reçoit une copie locale sous le
même identifiant. Le déplacement des animaux
pendant l’animation n’est pas encore enregistré dans les ZIP. Seuls les paramètres
de consultation sont mémorisés séparément.

Aucune permission caméra, Internet ou accès général au stockage n’est demandée :
la prise de vue est déléguée à l’application appareil photo, avec un accès temporaire
à un fichier via FileProvider. Les images choisies passent par le sélecteur Android.
Le détourage s’effectue sur l’appareil. Les mondes sont dans le stockage privé ; une
désinstallation peut les supprimer. L’export sera ajouté avec la gestion complète.
Limites d’import actuelles : 32 Mo par archive, 200 animaux, budget d’images décodées
de 16 millions de pixels. Une archive invalide ne remplace pas le monde affiché.

## Scanner un dessin

1. Ouvrir un monde, puis **Ajouter un animal**.
2. Choisir l’espèce dans la liste **Mer / Prairie**, puis **Prendre une photo** ou
   **Choisir une image**.
3. Placer le cadre autour d’un seul dessin, avec une marge de papier clair.
   Les quatre coins se déplacent au doigt ; on peut aussi déplacer le cadre entier.
4. Appuyer sur **Détourer le dessin**. Le damier montre les zones transparentes.
5. Si nécessaire, **Revoir le cadre** et ajuster le détourage : une valeur plus forte
   retire davantage de papier. Les zones blanches enfermées par le contour sont
   conservées. Le composant principal est retenu, les petites taches isolées sont
   éliminées. Une feuille bien éclairée et un contour fermé donnent les meilleurs
   résultats ; l’espèce est choisie par l’utilisateur.
6. Régler la taille et cocher l’inversion si le dessin regarde à droite, puis
   **Ajouter au monde**. L’application revient au bon habitat.

Les photos de travail sont limitées à 32 Mo et réduites avant traitement. Le brouillon
survit à une rotation ; la photo normalisée est aussi conservée temporairement pour
la recréation du processus. Les fichiers du scan sont nettoyés après ajout ou abandon.
L’ajout n’inclut pas encore l’édition de squelette.

## Vérification

Les tests de caméra couvrent les limites du monde, le zoom centré sur les doigts,
les formats d’écran et les positions invalides. Les tests Robolectric exécutent
le lecteur et le créateur de ZIP pour Android 8 et Android 16, avec les cinq archives
réelles, les images, les squelettes conservés et plusieurs archives invalides.
Ils couvrent également la création et la réouverture d’un monde vide.
Les tests du scan couvrent le papier blanc/gris, les couleurs pâles, les blancs
intérieurs, la transparence, l’orientation EXIF et la reprise après retour de photo.
Les tests d’ajout vérifient les deux habitats, la conservation des anciens dessins,
l’absence de doublon lors d’une nouvelle tentative et la protection du ZIP en cas d’échec.

`ScanFlowTest` est un test instrumenté pour tablette/émulateur : il simule le retour
de la caméra, passe par les vrais écrans, recrée l’activité, détoure et sauvegarde
dans un monde de test isolé, puis le rouvre. Il ne déclenche pas le capteur photo.

Pour synchroniser les exemples après avoir changé les mondes Python :

```powershell
python .\tools\sync_worlds.py
```

Le script copie les archives et produit `app/src/main/assets/worlds/index.json`
avec leur nombre d’animaux et empreinte SHA-256. Il ne modifie pas les originaux.

## Suite du portage complet

1. Animations articulées et comportements/interactions des 22 espèces.
2. Amélioration du scan à partir des essais sur de vrais dessins et appareils photo.
3. Éditeur tactile des articulations et aperçu animé.
4. Modification, duplication et suppression des animaux.
5. Gestion complète des mondes : renommage, suppression, export et sauvegarde des populations.
6. Réglages complets, performances et accessibilité sur plusieurs appareils.
7. Préparation Google Play : identité définitive, icône, signature de publication,
   AAB, fiche du store et informations de confidentialité adaptées aux fonctions finales.

**Cette version 0.2 est une version de développement, pas encore le portage complet
ni une application prête à publier.** L’identifiant `fr.mondesdesanimaux.app` est
provisoire ; le fixer avant la première publication. Aucune clé de publication n’est
créée ni incluse dans le dépôt. Les dessins embarqués sont des exemples de travail
du projet ; sélectionner les exemples définitifs avant publication.

Références techniques : [AGP 9.0](https://developer.android.com/build/releases/agp-9-0-0-release-notes),
[Gradle 9.1 et Java 25](https://docs.gradle.org/9.1.0/release-notes.html),
[Robolectric](https://robolectric.org/getting-started/),
[niveau d’API Google Play](https://developer.android.com/google/play/requirements/target-sdk).
