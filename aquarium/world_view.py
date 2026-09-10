"""Réglages du monde et navigation partagés par les deux scènes."""
import pygame


class WorldView:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.screens = 1
        self.auto = False
        self.scroll_speed = 1.0
        self.x = 0.0
        self.direction = 1
        self.open = False
        self.manual_until = 0
        self.surface = None
        self.button = pygame.Rect(210, 650, 150, 34)
        self.left = pygame.Rect(390, 650, 80, 34)
        self.right = pygame.Rect(730, 650, 80, 34)
        self.minus = pygame.Rect(390, 290, 60, 40)
        self.plus = pygame.Rect(750, 290, 60, 40)
        self.toggle = pygame.Rect(390, 365, 420, 42)
        self.slower = pygame.Rect(390, 425, 60, 40)
        self.faster = pygame.Rect(750, 425, 60, 40)
        self.close = pygame.Rect(650, 540, 160, 38)

    @property
    def world_width(self):
        return self.width * self.screens

    @property
    def visible_width(self):
        return self.width

    def settings(self):
        return dict(screens=self.screens, auto=self.auto, scroll_speed=self.scroll_speed)

    def restore(self, settings):
        self.screens = max(1, min(5, int(settings.get('screens', 1))))
        self.auto = settings.get('auto', False) is True
        self.scroll_speed = max(0.25, min(3.0, float(settings.get('scroll_speed', 1.0))))
        self.x = 0.0

    def handle(self, event, animals, interactions):
        if event.type == pygame.QUIT:
            return False, False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.open:
            self.open = False
            return True, False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.button.collidepoint(event.pos):
                self.open = not self.open
                return True, False
            if self.open:
                if self.close.collidepoint(event.pos):
                    self.open = False
                elif self.toggle.collidepoint(event.pos):
                    self.auto = not self.auto
                    self.manual_until = 0
                    return True, True
                elif self.slower.collidepoint(event.pos) or self.faster.collidepoint(event.pos):
                    delta = 0.25 if self.faster.collidepoint(event.pos) else -0.25
                    speed = max(0.25, min(3.0, self.scroll_speed + delta))
                    changed = speed != self.scroll_speed
                    self.scroll_speed = speed
                    return True, changed
                else:
                    count = self.screens
                    if self.minus.collidepoint(event.pos):
                        count = max(1, count - 1)
                    elif self.plus.collidepoint(event.pos):
                        count = min(5, count + 1)
                    if count != self.screens:
                        self.screens = count
                        self.x = min(self.x, self.world_width - self.visible_width)
                        interactions.pairs.clear()
                        for animal in animals:
                            margin = animal.width / 2 + 20
                            animal.x = max(margin, min(self.world_width - margin, animal.x))
                            animal.social_target = None
                            animal.social_face = None
                            if hasattr(animal, 'social_jump'):
                                animal.social_jump = 0
                        return True, True
                return True, False
        if self.open:
            # Laisser Ctrl+S atteindre la sauvegarde de la scène.
            saving = event.type == pygame.KEYDOWN and event.key == pygame.K_s and event.mod & pygame.KMOD_CTRL
            return not saving, False
        return False, False

    def update(self, dt, paused=False, mouse_enabled=True):
        if paused:
            return
        dt = min(dt, 0.1)
        keys = pygame.key.get_pressed()
        mouse = mouse_enabled and pygame.mouse.get_pressed()[0]
        pos = pygame.mouse.get_pos()
        movement = int(keys[pygame.K_RIGHT] or (mouse and self.right.collidepoint(pos))) - int(keys[pygame.K_LEFT] or (mouse and self.left.collidepoint(pos)))
        if movement:
            self.x += movement * 480 * self.scroll_speed * dt
            self.manual_until = pygame.time.get_ticks() + 3000
        elif self.auto and pygame.time.get_ticks() >= self.manual_until:
            self.x += self.direction * 90 * self.scroll_speed * dt
        limit = self.world_width - self.visible_width
        self.x = max(0, min(limit, self.x))
        if self.x >= limit:
            self.direction = -1
        elif self.x <= 0:
            self.direction = 1

    def background(self, draw, time):
        size = (self.world_width, self.height)
        if self.surface is None or self.surface.get_size() != size:
            self.surface = pygame.Surface(size).convert()
        # Dessiner dans un seul espace : aucun objet coup? aux limites des ?crans.
        draw(self.surface, time)
        return self.surface

    def draw(self, screen, font):
        def button(rect, text, active=True):
            pygame.draw.rect(screen, (35, 110, 145) if active else (70, 80, 85), rect, border_radius=6)
            label = font.render(text, True, 'white')
            screen.blit(label, label.get_rect(center=rect.center))

        button(self.button, 'Paramètres')
        button(self.left, '<', self.x > 0)
        button(self.right, '>', self.x < self.world_width - self.visible_width)
        label = font.render(f'Vue {1 + self.x / self.width:.1f} / {self.screens}', True, 'white')
        screen.blit(label, label.get_rect(center=(600, 667)))
        if not self.open:
            return
        shade = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        shade.fill((0, 15, 30, 180))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, (20, 48, 65), (340, 200, 520, 400), border_radius=12)
        screen.blit(font.render('Paramètres du monde', True, 'white'), (390, 225))
        button(self.minus, '-', self.screens > 1)
        button(self.plus, '+', self.screens < 5)
        label = font.render(f'Largeur : {self.screens} écran(s)', True, 'white')
        screen.blit(label, label.get_rect(center=(600, 310)))
        button(self.toggle, 'Balayage automatique : ' + ('activé' if self.auto else 'désactivé'))
        screen.blit(font.render('Flèches : déplacer la vue (priorité 3 secondes)', True, 'white'), (365, 495))
        button(self.slower, '-', self.scroll_speed > 0.25)
        button(self.faster, '+', self.scroll_speed < 3.0)
        label = font.render(f'Vitesse d?filement : {self.scroll_speed:g}x', True, 'white')
        screen.blit(label, label.get_rect(center=(600, 445)))
        button(self.close, 'Fermer')
