"""Mer, plage et prairie : python aquarium/monde_combine.py."""
import json
import math
import random
import zipfile
from pathlib import Path
from types import SimpleNamespace

import cv2
import pygame

if __package__:
    from . import aquarium as sea
    from . import animaux_terrestres as land
    from .world_view import WorldView
    from .world_library import WorldLibrary
    from .loading import loading_screen
else:
    import aquarium as sea
    import animaux_terrestres as land
    from world_view import WorldView
    from world_library import WorldLibrary
    from loading import loading_screen


WIDTH, HEIGHT = 1200, 700
BEACH = 100
LAND_Y = HEIGHT + BEACH
WORLD_HEIGHT = LAND_Y + HEIGHT
SAVE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = SAVE_DIR / 'monde_combine.json'
ERRORS = (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, cv2.error)


def button(screen, font, rect, text):
    pygame.draw.rect(screen, (35, 110, 145), rect, border_radius=6)
    label = font.render(text, True, 'white')
    screen.blit(label, label.get_rect(center=rect.center))


class CombinedView(WorldView):
    def __init__(self):
        super().__init__(WIDTH, HEIGHT)
        self.y = 0.0
        self.zoom = 1.0
        self.controls_visible = True
        self.vertical_speed = 1.0
        self.vertical_auto = False
        self.vertical_direction = 1
        self.vertical_manual_until = 0
        self.up = pygame.Rect(840, 650, 90, 34)
        self.down = pygame.Rect(940, 650, 90, 34)
        self.minus.y = self.plus.y = 215
        self.toggle.y = 280
        self.slower.y = self.faster.y = 345
        self.vertical_slower = pygame.Rect(390, 410, 60, 40)
        self.vertical_faster = pygame.Rect(750, 410, 60, 40)
        self.vertical_toggle = pygame.Rect(390, 470, 420, 42)
        self.close.y = 590
        self.zoom_out = pygame.Rect(390, 520, 60, 40)
        self.zoom_in = pygame.Rect(750, 520, 60, 40)

    @property
    def visible_width(self):
        return min(self.world_width, round(WIDTH / self.zoom))

    @property
    def visible_height(self):
        return min(WORLD_HEIGHT, round(HEIGHT / self.zoom))

    def clamp_camera(self):
        self.x = max(0, min(self.world_width - self.visible_width, self.x))
        self.y = max(0, min(WORLD_HEIGHT - self.visible_height, self.y))

    def set_zoom(self, zoom):
        cx, cy = self.x + self.visible_width / 2, self.y + self.visible_height / 2
        previous = self.zoom
        self.zoom = max(0.5, min(2.0, round(zoom, 2)))
        self.x, self.y = cx - self.visible_width / 2, cy - self.visible_height / 2
        self.clamp_camera()
        return previous != self.zoom

    def draw_world(self, screen, world):
        self.clamp_camera()
        visible = world.subsurface((round(self.x), round(self.y), self.visible_width, self.visible_height))
        size = (round(self.visible_width * self.zoom), round(self.visible_height * self.zoom))
        scaled = pygame.transform.smoothscale(visible, size)
        screen.fill((20, 48, 65))
        screen.blit(scaled, scaled.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    def settings(self):
        return dict(super().settings(), vertical_speed=self.vertical_speed,
                    vertical_auto=self.vertical_auto, zoom=self.zoom)

    def restore(self, settings):
        super().restore(settings)
        self.zoom = max(0.5, min(2.0, float(settings.get('zoom', 1))))
        self.vertical_speed = max(0.25, min(3.0, float(settings.get('vertical_speed', 1))))
        self.y = 0.0
        self.vertical_auto = settings.get('vertical_auto', False) is True
        self.vertical_direction = 1
        self.vertical_manual_until = 0

    def handle(self, event, animals, interactions):
        if self.open and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.zoom_out.collidepoint(event.pos) or self.zoom_in.collidepoint(event.pos):
                delta = 0.1 if self.zoom_in.collidepoint(event.pos) else -0.1
                return True, self.set_zoom(self.zoom + delta)
            if self.vertical_toggle.collidepoint(event.pos):
                self.vertical_auto = not self.vertical_auto
                self.vertical_manual_until = 0
                return True, True
            if self.vertical_slower.collidepoint(event.pos) or self.vertical_faster.collidepoint(event.pos):
                delta = 0.25 if self.vertical_faster.collidepoint(event.pos) else -0.25
                speed = max(0.25, min(3.0, self.vertical_speed + delta))
                changed = speed != self.vertical_speed
                self.vertical_speed = speed
                return True, changed
        return super().handle(event, animals, interactions)

    def update(self, dt, paused=False):
        super().update(dt, paused, mouse_enabled=self.controls_visible)
        if paused:
            return
        keys = pygame.key.get_pressed()
        mouse = self.controls_visible and pygame.mouse.get_pressed()[0]
        pos = pygame.mouse.get_pos()
        movement = int(keys[pygame.K_DOWN] or (mouse and self.down.collidepoint(pos))) - int(keys[pygame.K_UP] or (mouse and self.up.collidepoint(pos)))
        dt = min(dt, 0.1)
        if movement:
            self.y += movement * 360 * self.vertical_speed * dt
            self.vertical_manual_until = pygame.time.get_ticks() + 3000
        elif self.vertical_auto and pygame.time.get_ticks() >= self.vertical_manual_until:
            self.y += self.vertical_direction * 90 * self.vertical_speed * dt
        limit = WORLD_HEIGHT - self.visible_height
        self.y = max(0, min(limit, self.y))
        if self.y >= limit:
            self.vertical_direction = -1
        elif self.y <= 0:
            self.vertical_direction = 1

    def draw(self, screen, font):
        # Réutiliser la barre de navigation, puis afficher le panneau étendu.
        opened = self.open
        self.open = False
        super().draw(screen, font)
        self.open = opened
        button(screen, font, self.up, 'Haut')
        button(screen, font, self.down, 'Bas')
        if not opened:
            return
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 15, 30, 180))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (20, 48, 65), (340, 140, 520, 500), border_radius=12)
        screen.blit(font.render('Paramètres mer et prairie', True, 'white'), (390, 165))
        for minus, plus, text in (
            (self.minus, self.plus, f'Largeur commune : {self.screens} écran(s)'),
            (self.slower, self.faster, f'Vitesse horizontale : {self.scroll_speed:g}x'),
            (self.vertical_slower, self.vertical_faster, f'Vitesse verticale : {self.vertical_speed:g}x'),
            (self.zoom_out, self.zoom_in, f'Zoom global : {self.zoom:.0%}'),
        ):
            button(screen, font, minus, '-')
            button(screen, font, plus, '+')
            label = font.render(text, True, 'white')
            screen.blit(label, label.get_rect(center=(600, minus.centery)))
        button(screen, font, self.toggle, 'Balayage horizontal : ' + ('activé' if self.auto else 'désactivé'))
        button(screen, font, self.vertical_toggle, 'Balayage vertical : ' + ('activé' if self.vertical_auto else 'désactivé'))
        screen.blit(font.render('Ctrl+S : sauvegarder le monde et les réglages', True, 'white'), (365, 565))
        button(screen, font, self.close, 'Fermer')


class Habitat:
    def __init__(self, module, name, interaction_class, choices):
        self.module, self.name = module, name
        self.path = SAVE_DIR / ('monde_' + name + '.zip')
        self.animals = []
        self.interactions = interaction_class()
        self.manager = module.AquariumManager()
        self.choices = choices

    def update(self, dt):
        self.interactions.update(self.animals, min(dt, 0.05))
        for animal in self.animals:
            remaining = min(dt, 0.1) * getattr(animal, 'speed_scale', 1)
            while remaining > 0:
                step = min(remaining, 0.025)
                animal.update(step)
                remaining -= step

    def draw(self, surface, font):
        animals = sorted(self.animals, key=lambda a: a.ground_y) if self.module is land else self.animals
        for animal in animals:
            animal.draw(surface)
        self.interactions.draw(surface, font)


def draw_meadow(surface):
    """Prolonger la plage par de l'herbe, sans intercaler le ciel de la prairie."""
    width = surface.get_width()
    surface.fill((104, 164, 84))
    for x in range(110, width - 80, 1000):
        pygame.draw.rect(surface, (126, 87, 57), (x - 12, 330, 24, 190))
        pygame.draw.circle(surface, (59, 131, 75), (x, 310), 80)
        pygame.draw.circle(surface, (79, 150, 78), (x - 35, 285), 55)
    for i, x in enumerate(range(30, width, 35)):
        for band in range(4):
            y = 30 + band * 170 + (i * 37) % 130
            pygame.draw.line(surface, (65, 125, 60), (x, y), (x + 2, y - 8), 2)
            pygame.draw.circle(surface, (255, 222, 135), (x + 2, y - 9), 3)


def render_world(view, habitats, font, time):
    size = (view.world_width, WORLD_HEIGHT)
    if view.surface is None or view.surface.get_size() != size:
        view.surface = pygame.Surface(size).convert()
    world = view.surface
    water = world.subsurface((0, 0, view.world_width, HEIGHT))
    meadow = world.subsurface((0, LAND_Y, view.world_width, HEIGHT))
    sea.draw_aquarium(water, time)
    draw_meadow(meadow)
    pygame.draw.rect(world, (224, 201, 143), (0, HEIGHT, view.world_width, BEACH))
    # Une rive ondulée continue sur toute la largeur, puis une lisière herbeuse.
    for x in range(-40, view.world_width, 70):
        offset = round(math.sin(time * 0.0015 + x * 0.01) * 4)
        pygame.draw.ellipse(world, (241, 232, 190), (x, HEIGHT - 8 + offset, 95, 20))
        pygame.draw.ellipse(world, (104, 164, 84), (x, LAND_Y - 12, 95, 25))
    for i, x in enumerate(range(25, view.world_width, 95)):
        pygame.draw.circle(world, (194, 166, 105), (x, HEIGHT + 35 + i * 17 % 35), 2)
    habitats[0].draw(water, font)
    habitats[1].draw(meadow, font)
    return world


def load_initial_world(view, habitats, library):
    # The active archive is authoritative; legacy saves are a first-run fallback.
    for habitat in habitats:
        habitat.module.VIEW = view
    if library.resume(view, habitats):
        return 'Monde repris : ' + library.name
    status = 'Flèches : explorer | Ctrl+S : sauvegarder | F11 : plein écran'
    settings = {}
    for habitat in habitats:
        try:
            habitat.animals = habitat.module.load_aquarium(habitat.path if habitat.path.exists() else habitat.module.SAVE_PATH)
            settings['screens'] = max(settings.get('screens', 1), habitat.module.VIEW.screens)
        except ERRORS as error:
            status = f'Chargement {habitat.name} impossible : {error}'
    try:
        if SETTINGS_PATH.exists():
            settings.update(json.loads(SETTINGS_PATH.read_text(encoding='utf-8')))
        view.restore(settings)
    except ERRORS as error:
        status = f'Réglages illisibles : {error}'
    for habitat in habitats:
        habitat.module.VIEW = view
        for animal in habitat.animals:
            animal.x = min(animal.x, view.world_width - animal.width / 2 - 20)
    # Montrer dès l'ouverture la mer, la plage et le début de la prairie.
    view.y = HEIGHT / 2
    return status


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.FULLSCREEN)
    pygame.display.set_caption('La mer, la plage et la prairie')
    font = pygame.font.Font(None, 24)
    view = CombinedView()
    habitats = [
        Habitat(sea, 'mer', sea.FishInteractions,
                [('Poisson', sea.Fish), ('Méduse', sea.Jellyfish), ('Crabe', sea.Crab),
                 ('Étoile de mer', sea.Starfish), ('Tortue', sea.Turtle)]),
        Habitat(land, 'prairie', land.Interactions,
                [(cls.label, cls) for cls in land.ANIMAL_TYPES.values()]),
    ]
    library = WorldLibrary(SAVE_DIR / 'mondes')
    try:
        with loading_screen('Chargement du monde'):
            status = load_initial_world(view, habitats, library)
    except (*ERRORS, pygame.error) as error:
        pygame.quit()
        raise RuntimeError('Impossible de reprendre le monde sauvegardé') from error
    add_buttons = [pygame.Rect(15 + i * 210, 42, 200, 34) for i in range(2)]
    manage_buttons = [pygame.Rect(435 + i * 210, 42, 200, 34) for i in range(2)]
    fullscreen_button = pygame.Rect(15, 650, 180, 34)
    fullscreen, running, dirty = True, True, False
    choosing = None
    autosave_retry_at = 0
    def capture():
        preview = pygame.Surface((WIDTH, HEIGHT))
        view.draw_world(preview, render_world(view, habitats, font, pygame.time.get_ticks()))
        return preview
    clock = pygame.time.Clock()
    while running:
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_h:
                view.controls_visible = not view.controls_visible
                if not view.controls_visible:
                    view.open = False
                    library.open = False
                    choosing = None
                    for habitat in habitats:
                        habitat.manager.open = False
                        habitat.manager.dragging = None
                continue
            if not view.controls_visible and event.type in (
                pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                pygame.MOUSEMOTION, pygame.MOUSEWHEEL,
            ):
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    view.controls_visible = True
                continue
            active = next((h for h in habitats if h.manager.open), None)
            modal = active is not None or choosing is not None or view.open or library.open
            if (event.type == pygame.KEYDOWN and event.key == pygame.K_F11) or (
                not modal and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and fullscreen_button.collidepoint(event.pos)
            ):
                fullscreen = not fullscreen
                screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | (pygame.FULLSCREEN if fullscreen else 0))
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_s and event.mod & pygame.KMOD_CTRL:
                try:
                    library.save(view, habitats, capture())
                    dirty = False
                    status = 'Monde combiné sauvegardé'
                except ERRORS as error:
                    status = f'Échec de sauvegarde : {error}'
                continue
            if library.open:
                try:
                    message, saved = library.handle(event, view, habitats, capture)
                    if message:
                        status = library.message = message
                    if saved:
                        dirty = False
                except (*ERRORS, pygame.error) as error:
                    status = library.message = 'Erreur : ' + str(error)
                continue
            if not modal and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and library.button.collidepoint(event.pos):
                library.refresh()
                library.message = ''
                library.open = True
                continue
            if active is not None:
                _, changed = active.manager.handle(event, active.animals, active.interactions)
                dirty |= changed
                continue
            if choosing is not None:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    choosing = None
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    habitat = choosing
                    choosing = None
                    for index, (_, cls) in enumerate(habitat.choices):
                        if choice_rect(index).collidepoint(event.pos):
                            try:
                                scanned = habitat.module.scan_fish(cls.kind)
                                if scanned is not None:
                                    pixels, rig = scanned
                                    animal = cls(habitat.module.cv_to_pygame(pixels), rig=rig)
                                    animal.x = max(animal.width / 2 + 20, min(
                                        view.world_width - animal.width / 2 - 20,
                                        view.x + view.visible_width / 2))
                                    habitat.animals.append(animal)
                                    view.y = 0 if habitat.module is sea else LAND_Y
                                    dirty = True
                            except (*ERRORS, pygame.error, RuntimeError) as error:
                                status = f'Scan impossible : {error}'
                            clock.tick()
                            dt = 0
                            break
                continue
            old_width = view.world_width
            consumed, changed = view.handle(event, [a for h in habitats for a in h.animals], SimpleNamespace(pairs=[]))
            if old_width != view.world_width:
                for habitat in habitats:
                    habitat.interactions.pairs.clear()
            dirty |= changed
            if consumed:
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for index, habitat in enumerate(habitats):
                    if add_buttons[index].collidepoint(event.pos):
                        choosing = habitat
                    elif manage_buttons[index].collidepoint(event.pos):
                        habitat.manager.open = True
        # Sauvegarder les curseurs au relâchement, les autres changements immédiatement.
        dragging = any(h.manager.dragging is not None for h in habitats)
        if dirty and (not running or (not dragging and pygame.time.get_ticks() >= autosave_retry_at)):
            try:
                library.save(view, habitats, capture())
                dirty = False
                autosave_retry_at = 0
                status = 'Sauvegarde automatique : ' + library.name
            except (*ERRORS, pygame.error) as error:
                status = library.message = 'Échec de sauvegarde automatique : ' + str(error)
                autosave_retry_at = pygame.time.get_ticks() + 5000
                running = True
        paused = library.open or view.open or choosing is not None or any(h.manager.open for h in habitats)
        view.update(dt, paused)
        for habitat in habitats:
            habitat.update(0 if paused else dt)
        world = render_world(view, habitats, font, pygame.time.get_ticks())
        view.draw_world(screen, world)
        if view.controls_visible:
            pygame.draw.rect(screen, (20, 48, 65), (0, 0, WIDTH, 84))
            pygame.draw.rect(screen, (20, 48, 65), (0, 642, WIDTH, 58))
            screen.blit(font.render(status[:115], True, 'white'), (15, 12))
            for index, habitat in enumerate(habitats):
                button(screen, font, add_buttons[index], 'Ajouter : ' + habitat.name)
                button(screen, font, manage_buttons[index], 'Gérer : ' + habitat.name)
            if dirty:
                screen.blit(font.render('Non sauvegardé', True, (255, 220, 100)), (1045, 50))
            button(screen, font, fullscreen_button, 'Mode fenêtre' if fullscreen else 'Plein écran')
            library.draw(screen, font)
            view.draw(screen, font)
            for habitat in habitats:
                if habitat.manager.open:
                    habitat.manager.draw(screen, font, habitat.animals)
            if choosing is not None:
                shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                shade.fill((0, 15, 30, 190))
                screen.blit(shade, (0, 0))
                screen.blit(font.render('Choisir un animal : ' + choosing.name, True, 'white'), (390, 130))
                for index, (label, _) in enumerate(choosing.choices):
                    button(screen, font, choice_rect(index), label)
                screen.blit(font.render('Echap ou clic à côté : annuler', True, 'white'), (440, 590))
            if library.open:
                library.draw(screen, font)
        pygame.display.flip()
    pygame.quit()


def choice_rect(index):
    return pygame.Rect(250 + index % 3 * 240, 180 + index // 3 * 65, 220, 48)


if __name__ == '__main__':
    main()
