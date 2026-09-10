"""Bibliothèque de mondes : archives autonomes et aperçus intégrés."""
import io
import json
import tempfile
import uuid
import zipfile
from pathlib import Path

import pygame


class WorldLibrary:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.current = None
        self.name = 'Mon premier monde'
        self.open = False
        self.page = 0
        self.entries = []
        self.message = ''
        self.button = pygame.Rect(875, 42, 160, 34)
        self.field = pygame.Rect(160, 135, 420, 38)
        self.save_button = pygame.Rect(600, 135, 190, 38)
        self.new_button = pygame.Rect(810, 135, 220, 38)
        self.close = pygame.Rect(930, 90, 100, 30)
        self.previous = pygame.Rect(160, 590, 100, 32)
        self.next = pygame.Rect(930, 590, 100, 32)
        self.typing = False

    def remember_current(self):
        marker = self.folder / 'current.txt'
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(self.current.name, encoding='utf-8')
        temporary.replace(marker)

    def resume(self, view, habitats):
        marker = self.folder / 'current.txt'
        if marker.exists():
            filename = marker.read_text(encoding='utf-8').strip()
            if Path(filename).name != filename or not filename.endswith('.zip'):
                raise ValueError('Référence de monde invalide')
            self.load(self.folder / filename, view, habitats)
            return True
        # Migration : reprendre la dernière archive des versions précédentes.
        paths = sorted(self.folder.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
        if paths:
            self.load(paths[0], view, habitats)
            return True
        return False

    def refresh(self):
        self.entries = []
        for path in sorted(self.folder.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with zipfile.ZipFile(path) as archive:
                    data = json.loads(archive.read('world.json'))
                    thumb = pygame.image.load(io.BytesIO(archive.read('preview.png'))).convert()
                self.entries.append((path, data['name'], thumb))
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, pygame.error):
                # Un fichier illisible ne doit pas empêcher les autres de s'afficher.
                self.entries.append((path, 'Sauvegarde illisible', None))
        self.page = min(self.page, max(0, (len(self.entries) - 1) // 6))

    def save(self, view, habitats, preview):
        self.folder.mkdir(parents=True, exist_ok=True)
        destination = self.current or self.folder / (uuid.uuid4().hex + '.zip')
        temporary = destination.with_suffix('.tmp')
        data = dict(version=1, name=self.name.strip() or 'Monde sans nom',
                    settings=view.settings(), camera=[view.x, view.y])
        try:
            with tempfile.TemporaryDirectory() as directory:
                with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('world.json', json.dumps(data, ensure_ascii=False))
                    for habitat in habitats:
                        path = Path(directory) / (habitat.name + '.zip')
                        habitat.module.save_aquarium(habitat.animals, path)
                        archive.write(path, path.name)
                    image = io.BytesIO()
                    pygame.image.save(pygame.transform.smoothscale(preview, (300, 175)), image, 'preview.png')
                    archive.writestr('preview.png', image.getvalue())
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        self.current, self.name = destination, data['name']
        self.remember_current()
        self.refresh()

    def load(self, path, view, habitats):
        # Tout valider avant de remplacer les animaux actuellement affichés.
        populations = []
        with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(path) as archive:
            data = json.loads(archive.read('world.json'))
            if data['version'] != 1:
                raise ValueError('Version de monde inconnue')
            candidate = type(view)()
            candidate.restore(data['settings'])
            candidate.x, candidate.y = map(float, data.get('camera', [0, 350]))
            candidate.clamp_camera()
            name = str(data['name'])
            for habitat in habitats:
                file = Path(directory) / (habitat.name + '.zip')
                file.write_bytes(archive.read(file.name))
                original_view = habitat.module.VIEW
                try:
                    habitat.module.VIEW = type(view)()
                    populations.append(habitat.module.load_aquarium(file))
                finally:
                    habitat.module.VIEW = original_view
        view.restore(candidate.settings())
        view.x, view.y = candidate.x, candidate.y
        for habitat, animals in zip(habitats, populations):
            habitat.animals = animals
            habitat.interactions.pairs.clear()
            habitat.manager.scroll = 0
            habitat.manager.dragging = None
        self.current, self.name = path, name
        self.remember_current()

    def handle(self, event, view, habitats, capture):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.open = False
            self.typing = False
            return '', False
        if event.type == pygame.TEXTINPUT and self.typing:
            self.name = (self.name + event.text)[:40]
        if event.type == pygame.KEYDOWN and self.typing and event.key == pygame.K_BACKSPACE:
            self.name = self.name[:-1]
        if event.type == pygame.MOUSEWHEEL:
            self.page = max(0, min(max(0, (len(self.entries) - 1) // 6), self.page - event.y))
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return '', False
        self.typing = self.field.collidepoint(event.pos)
        if self.close.collidepoint(event.pos):
            self.open = False
        elif self.previous.collidepoint(event.pos):
            self.page = max(0, self.page - 1)
        elif self.next.collidepoint(event.pos):
            self.page = min(max(0, (len(self.entries) - 1) // 6), self.page + 1)
        elif self.save_button.collidepoint(event.pos):
            self.save(view, habitats, capture())
            return 'Monde sauvegardé : ' + self.name, True
        elif self.new_button.collidepoint(event.pos):
            self.save(view, habitats, capture())
            for habitat in habitats:
                habitat.animals = []
                habitat.interactions.pairs.clear()
                habitat.manager.scroll = 0
                habitat.manager.dragging = None
            view.restore({})
            view.y = 350
            self.current = None
            self.name = 'Nouveau monde'
            self.open = False
            return 'Nouveau monde vide — le précédent a été sauvegardé', True
        else:
            for index, (path, _, _) in enumerate(self.entries[self.page * 6:self.page * 6 + 6]):
                if self.card(index).collidepoint(event.pos):
                    self.save(view, habitats, capture())
                    self.load(path, view, habitats)
                    self.open = False
                    return 'Monde chargé : ' + self.name, True
        return '', False

    @staticmethod
    def card(index):
        return pygame.Rect(160 + index % 3 * 295, 190 + index // 3 * 195, 280, 180)

    def draw(self, screen, font):
        def button(rect, text):
            pygame.draw.rect(screen, (35, 110, 145), rect, border_radius=6)
            label = font.render(text, True, 'white')
            screen.blit(label, label.get_rect(center=rect.center))
        button(self.button, 'Mes mondes')
        if not self.open:
            return
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 15, 30, 190))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (20, 48, 65), (140, 80, 910, 555), border_radius=12)
        screen.blit(font.render('Mes mondes — cliquer sur une image pour charger', True, 'white'), (160, 98))
        button(self.close, 'Fermer')
        button(self.field, self.name + ('|' if self.typing else ''))
        button(self.save_button, 'Sauvegarder')
        button(self.new_button, 'Nouveau monde')
        for index, (path, name, thumb) in enumerate(self.entries[self.page * 6:self.page * 6 + 6]):
            rect = self.card(index)
            pygame.draw.rect(screen, (70, 145, 115) if path == self.current else (35, 80, 100), rect, border_radius=6)
            if thumb is not None:
                screen.blit(pygame.transform.smoothscale(thumb, (270, 145)), (rect.x + 5, rect.y + 5))
            screen.blit(font.render(name[:28], True, 'white'), (rect.x + 8, rect.y + 155))
        if not self.entries:
            screen.blit(font.render('Aucun monde sauvegardé. Donnez un nom puis sauvegardez.', True, 'white'), (200, 300))
        button(self.previous, '<')
        button(self.next, '>')
        text = self.message or 'Le monde courant est sauvegardé avant Nouveau ou Charger.'
        screen.blit(font.render(text[:78], True, (255, 225, 150)), (275, 598))
