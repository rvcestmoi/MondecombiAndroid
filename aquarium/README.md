# Les mondes des animaux

## Version Android

Le projet Android est dans [`android/`](android/README.md). Ouvrir ce dossier dans
Android Studio puis lancer **Run**. Cette première version permet de créer un
monde vide, de charger les mondes Python et de les explorer au doigt. Le bouton
**Ajouter un animal** permet de photographier ou importer un dessin, de le détourer
et de l’enregistrer dans son habitat. Le portage des squelettes animés et de la
gestion complète des animaux reste à réaliser.

## Version Python

Depuis la racine du projet :

```powershell
python aquarium/monde_combine.py
```

La mer est en haut, la plage au milieu et la prairie en dessous. À l'ouverture,
la vue montre la jonction des trois espaces.

- Maintenir les flèches du clavier ou les boutons gauche/droite et Haut/Bas pour explorer.
- **Paramètres** : largeur commune de 1 à 5 écrans, vitesse horizontale et vitesse verticale de 0,25× à 3×.
- Les balayages automatiques horizontal et vertical sont activables séparément, avec un aller-retour aux limites du monde. La navigation manuelle suspend le balayage de l'axe concerné pendant trois secondes.
- **Ajouter : mer / prairie** : scanner un animal pour le milieu choisi.
- **Gérer : mer / prairie** : modifier, dupliquer ou supprimer les animaux.
- **F11** ou **Plein écran** : basculer entre fenêtre et plein écran.
- **H** : masquer ou réafficher toutes les commandes et les panneaux. Les flèches et le balayage automatique restent disponibles.
- Lorsque les commandes sont masquées, un clic gauche les réaffiche sans activer le bouton sous le clic.
- **Paramètres → Zoom global** : de 50 % à 200 %, pour agrandir ou réduire ensemble les décors et les animaux. Les commandes gardent leur taille. Le zoom est conservé avec Ctrl+S.
- **Ctrl+S** : sauvegarder les deux populations et les réglages. **Échap** ferme le panneau ouvert, ou quitte le programme.

Le bouton **Mes mondes** ouvre la biblioth?que :

- Cliquez dans le nom pour le modifier, puis sur **Sauvegarder**.
- Cliquez sur la miniature d'un monde pour le charger.
- **Nouveau monde** cr?e une sc?ne vide, avec les r?glages par d?faut.
- Le monde courant est sauvegard? avant de cr?er ou charger un autre monde.
- **Ctrl+S** met ? jour le monde courant (ou cr?e sa premi?re sauvegarde).
- Les fl?ches du panneau et la molette permettent de parcourir les pages.

Chaque archive du dossier `mondes` contient les animaux, les r?glages, la
position de la vue et une capture sans les commandes. Les anciennes sauvegardes
restent disponibles et servent de point de d?part au lancement ; ouvrez
**Mes mondes** pour retrouver les mondes enregistr?s dans la biblioth?que.
Les sauvegardes des programmes ind?pendants ne sont pas modifi?es.

Les deux programmes restent disponibles séparément :

```powershell
python aquarium/aquarium.py
python aquarium/animaux_terrestres.py
```

## Comportements des animaux

### Squelette facultatif après scan

Pendant le cadrage ou la validation du dessin, la case **Ajouter un squelette**
est décochée par défaut : sans la cocher, les animations habituelles restent
inchangées. Cette option existe dans le monde combiné et dans les deux
programmes indépendants.

Un clic sur **Ajouter un squelette** ouvre directement l’éditeur si le cadre
est déjà tracé ou le dessin déjà détouré. Si la case est cochée avant de tracer
le cadre, **Entrée** détoure le dessin puis ouvre automatiquement l’éditeur :

- Déplacer les points colorés sur le dos, le cou, la tête et les articulations
  du dessin. Pour une patte, les points 1, 2 et 3 sont la base, le genou et le pied.
- **Inverser le squelette** adapte le modèle à un animal dessiné tête à droite.
- **Aperçu animé** ou **Espace** alterne entre l’animation et l’édition des points.
- **Réinitialiser** remet le squelette de départ de l’espèce.
- **Valider** ou **Entrée** ajoute l’animal. **Échap** ou **Retour au cadrage**
  revient à la validation du scan, où la case peut être décochée.

Les 22 espèces disposent d’un modèle : marche articulée des quadrupèdes et de
la poule, bonds du lapin, battements d’ailes des oiseaux, nageoires et queue des
poissons et tortues, pattes et pinces du crabe, bras de l’étoile et tentacules de
la méduse. La cadence de marche tient compte de la longueur des pattes et de la
taille de l’animal. Les oiseaux ont des cadences propres à leur espèce et cessent
de battre des ailes pendant leurs séquences de vol plané.

Le dessin est déformé par le squelette en 2D ; le placement initial est un
gabarit à ajuster, pas une détection automatique des articulations. Les dessins
de profil aux membres bien séparés donnent les meilleurs résultats : les
parties cachées ou superposées ne peuvent pas être reconstituées à partir du scan.
L’aperçu permet de vérifier le résultat avant l’ajout.

Les articulations et l’orientation sont conservées avec les sauvegardes des
animaux et des mondes, ainsi que lors d’une duplication ou d’un changement de
taille. Les anciennes sauvegardes fonctionnent sans squelette. Les images de
l’animation sont calculées à l’ajout ou au chargement puis gardées en mémoire ;
le changement de taille réutilise ces images. Les dessins et squelettes
identiques partagent désormais le calcul, y compris lors d’une duplication.
Un cache local dans `.animation_cache/` évite de refaire ce calcul aux prochains
lancements. Il se reconstruit automatiquement s’il est absent ou illisible ;
les sauvegardes des mondes restent autonomes. Le cache partagé garde au plus
64 Mio en mémoire et 128 Mio sur disque (hors images utilisées par les animaux).

Au démarrage, seul le monde actif est chargé. Les anciennes populations ne
servent qu’en l’absence de monde enregistré. Un écran de progression apparaît
pendant le chargement et le premier calcul des animations ; on peut fermer la
fenêtre pendant cette étape.

Tests sans caméra ni fenêtre visible, depuis la racine :

```powershell
python -B -m unittest aquarium.test_animal_rig aquarium.test_world_library aquarium.test_animation_cache
```

Les animaux alternent spontanement deux petites animations propres a leur espece,
dans les trois programmes. Les rencontres entre animaux restent prioritaires.

| Animal | Comportement 1 | Comportement 2 |
| --- | --- | --- |
| chat | Étirement | Bond joueur |
| chien | Renifle le sol | Course joyeuse |
| lapin | Petits bonds rapides | Grignote |
| vache | Broute | Rumination |
| cochon | Fouille le sol | Se roule |
| mouton | Broute | Bondit |
| poule | Picore | Gratte le sol |
| cheval | Galop | Se cabre |
| lion | Rugit | Se repose |
| elephant | Se balance | Marche pesante |
| girafe | Étire le cou | Se penche pour brouter |
| zebre | Trottine | Broute |
| rhinoceros | Accélère | Frotte le sol |
| perroquet | Vol ondulant | Bat des ailes sur place |
| pigeon | Vol en cercle | Plane |
| moineau | Vol vif | Vole sur place |
| aigle | Grand cercle | Piqué puis remontée |
| poisson | Accélération | Explore en ondulant |
| meduse | Pulsations ascendantes | Dérive doucement |
| crabe | Course latérale | Fouille le sable |
| etoile | Pivote lentement | Explore le sable |
| tortue | Remonte respirer | Glisse sans effort |
