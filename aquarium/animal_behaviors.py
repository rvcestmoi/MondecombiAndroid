"""Petites séquences spontanées, indépendantes du décor et de la caméra."""
import math
import random

import pygame


# Nom, animation, durée, déplacement horizontal, amplitude verticale/rotation.
BEHAVIORS = {
    'chat': [('Étirement', 'stretch', 3, 0, 0), ('Bond joueur', 'hop', 2, 45, 24)],
    'chien': [('Renifle le sol', 'sniff', 3, 12, 9), ('Course joyeuse', 'hop', 3, 130, 10)],
    'lapin': [('Petits bonds rapides', 'hop', 3, 90, 30), ('Grignote', 'graze', 3, 0, 8)],
    'vache': [('Broute', 'graze', 4, 3, 12), ('Rumination', 'chew', 4, 0, 0)],
    'cochon': [('Fouille le sol', 'sniff', 4, 14, 14), ('Se roule', 'roll', 3, 0, 16)],
    'mouton': [('Broute', 'graze', 4, 5, 10), ('Bondit', 'hop', 2, 65, 22)],
    'poule': [('Picore', 'peck', 3, 5, 18), ('Gratte le sol', 'scratch', 3, -8, 5)],
    'cheval': [('Galop', 'hop', 4, 155, 12), ('Se cabre', 'rear', 2.5, 0, 25)],
    'lion': [('Rugit', 'roar', 3, 0, 10), ('Se repose', 'rest', 5, 0, 0)],
    'elephant': [('Se balance', 'sway', 4, 0, 7), ('Marche pesante', 'hop', 4, 36, 3)],
    'girafe': [('Étire le cou', 'stretch', 4, 0, 0), ('Se penche pour brouter', 'graze', 4, 0, 18)],
    'zebre': [('Trottine', 'hop', 4, 115, 9), ('Broute', 'graze', 3, 4, 12)],
    'rhinoceros': [('Accélère', 'hop', 3, 95, 4), ('Frotte le sol', 'scratch', 3, -5, 8)],
    'perroquet': [('Vol ondulant', 'wave', 4, 80, 30), ('Bat des ailes sur place', 'flutter', 3, 0, 7)],
    'pigeon': [('Vol en cercle', 'circle', 4, 42, 20), ('Plane', 'glide', 4, 105, 0)],
    'moineau': [('Vol vif', 'wave', 3, 145, 16), ('Vole sur place', 'flutter', 2, 0, 12)],
    'aigle': [('Grand cercle', 'circle', 5, 65, 38), ('Piqué puis remontée', 'dive', 4, 120, 80)],
    'poisson': [('Accélération', 'dart', 2, 190, 0), ('Explore en ondulant', 'wave', 4, 65, 25)],
    'meduse': [('Pulsations ascendantes', 'pulse', 4, 5, 65), ('Dérive doucement', 'wave', 5, 20, 15)],
    'crabe': [('Course latérale', 'dart', 2, 90, 0), ('Fouille le sable', 'scratch', 3, 0, 8)],
    'etoile': [('Pivote lentement', 'roll', 5, 0, 35), ('Explore le sable', 'wave', 5, 12, 0)],
    'tortue': [('Remonte respirer', 'surface', 5, 18, 0), ('Glisse sans effort', 'glide', 4, 50, 0)],
}


class AnimalBehavior:
    def __init__(self, kind):
        self.choices = BEHAVIORS.get(kind, [])
        self.active = None
        self.elapsed = 0.0
        self.wait = random.uniform(3, 9)
        self.last = None
        self.angle = self.lift = 0.0
        self.scale_x = self.scale_y = 1.0

    def reset_pose(self):
        self.angle = self.lift = 0.0
        self.scale_x = self.scale_y = 1.0

    def start(self, animal, choice=None):
        options = [c for c in self.choices if c != self.last] or self.choices
        self.active = choice or random.choice(options)
        self.last = self.active
        self.elapsed = 0.0
        self.origin_y = animal.ground_y if hasattr(animal, 'ground_y') else animal.y
        animal.turn_elapsed = None

    def update(self, animal, dt, world_width):
        # Les rencontres priment et interrompent proprement une activité solitaire.
        if animal.social_target is not None:
            self.active = None
            self.wait = random.uniform(4, 8)
            self.reset_pose()
            return False
        if dt <= 0:
            return self.active is not None
        if self.active is None:
            self.wait -= dt
            if self.wait > 0 or not self.choices:
                return False
            self.start(animal)
        self.elapsed += dt
        _, mode, duration, speed, amplitude = self.active
        t = min(1, self.elapsed / duration)
        envelope = math.sin(math.pi * t)
        wave = math.sin(self.elapsed * math.tau * 2)
        self.reset_pose()
        animal.phase = (animal.phase + dt * (0.15 if mode in ('glide', 'rest') else 2.5)) % 1
        animal.x += animal.direction * speed * dt * (math.cos(t * math.tau) if mode == 'circle' else 1)
        margin = animal.width / 2 + 20
        if animal.x <= margin:
            animal.x, animal.direction = margin, 1
        elif animal.x >= world_width - margin:
            animal.x, animal.direction = world_width - margin, -1
        if mode == 'hop':
            self.lift = abs(wave) * amplitude * envelope
        elif mode in ('graze', 'sniff', 'peck'):
            rhythm = max(0, wave) if mode == 'peck' else .7 + .3 * wave
            self.angle = animal.direction * amplitude * rhythm * envelope
        elif mode == 'chew':
            self.scale_x = 1 + .035 * wave * envelope
        elif mode == 'stretch':
            self.scale_x, self.scale_y = 1 + .12 * envelope, 1 - .12 * envelope
            if animal.kind == 'girafe':
                self.scale_x, self.scale_y = 1, 1 + .15 * envelope
        elif mode == 'rear':
            self.angle = -animal.direction * amplitude * envelope
            self.lift = animal.height * .12 * envelope
        elif mode in ('roll', 'sway', 'scratch', 'roar'):
            self.angle = amplitude * wave * envelope
            if mode == 'roar':
                self.scale_y = 1 + .08 * envelope
        elif mode == 'rest':
            self.scale_y = 1 - .25 * envelope
        elif mode == 'flutter':
            self.lift = amplitude * wave * envelope
        if mode in ('wave', 'circle', 'dive', 'pulse', 'surface'):
            delta = amplitude * math.sin(t * math.tau) if mode in ('wave', 'circle') else amplitude * envelope
            if mode == 'pulse':
                delta = -delta
                self.scale_x = 1 - .12 * max(0, wave) * envelope
            if mode == 'surface':
                delta = (animal.height / 2 + 35 - self.origin_y) * envelope
            if hasattr(animal, 'ground_y'):
                # Les oiseaux conservent leur bande de vol.
                animal.ground_y = max(200, min(440, self.origin_y + delta))
            elif animal.kind not in ('crabe', 'etoile'):
                animal.y = max(animal.height / 2 + 30, min(600 - animal.height / 2, self.origin_y + delta))
                animal.target_y = animal.y
        if hasattr(animal, 'on_ground'):
            animal.on_ground()
        elif hasattr(animal, 'on_sand'):
            animal.on_sand()
        if self.elapsed >= duration:
            self.active = None
            self.wait = random.uniform(6, 13)
            self.reset_pose()
        return True

    def draw(self, screen, frame, position, bottom=False):
        if self.scale_x != 1 or self.scale_y != 1:
            frame = pygame.transform.smoothscale(frame, (
                max(1, round(frame.get_width() * self.scale_x)),
                max(1, round(frame.get_height() * self.scale_y))))
        if self.angle:
            frame = pygame.transform.rotate(frame, self.angle)
        x, y = position
        anchor = (round(x), round(y - self.lift))
        rect = frame.get_rect(midbottom=anchor) if bottom else frame.get_rect(center=anchor)
        screen.blit(frame, rect)
