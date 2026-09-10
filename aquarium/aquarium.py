import cv2
import pygame
import numpy as np
import random
import math
import sys
import json
import zipfile
from pathlib import Path

try:
    from .world_view import WorldView
    from .loading import loading_screen, report_progress
    from .animal_behaviors import AnimalBehavior
    from .animal_rig import edit_rig, rebuild_rigged, rig_frame, validate_rig, gait_rate
except ImportError:
    from world_view import WorldView
    from loading import loading_screen, report_progress
    from animal_behaviors import AnimalBehavior
    from animal_rig import edit_rig, rebuild_rigged, rig_frame, validate_rig, gait_rate

# ==========================================================
# CONFIGURATION
# ==========================================================

CAMERA_ID = 0

SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 700
VIEW = WorldView(SCREEN_WIDTH, SCREEN_HEIGHT)

FISH_WIDTH = 180

# Le dessin scanne a la tete a gauche et la queue a droite.
FISH_HEAD_LEFT = True
SAVE_PATH = Path(__file__).resolve().with_name('aquarium.zip')

# Plus cette valeur est grande, plus on supprime de gris clair
WHITE_THRESHOLD = 210


# ==========================================================
# CAPTURE DU POISSON
# ==========================================================

def capture_fish():
    cap = cv2.VideoCapture(CAMERA_ID)

    if not cap.isOpened():
        print("Impossible d'ouvrir la caméra.")
        cap.release()
        return None

    print("Place la feuille avec le poisson devant la caméra.")
    print("ESPACE = capturer")
    print("ECHAP = quitter")

    captured = None

    while True:
        ret, frame = cap.read()

        if not ret:
            continue

        preview = frame.copy()

        cv2.putText(
            preview,
            "Place ton animal dans le cadre - ESPACE pour capturer",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )

        cv2.imshow("Scanner le poisson", preview)

        key = cv2.waitKey(1)

        if key == 27:
            cap.release()
            cv2.destroyAllWindows()
            return None

        elif key == 32:
            captured = frame.copy()
            break

    cap.release()
    cv2.destroyAllWindows()

    return captured


# ==========================================================
# EXTRACTION DU POISSON
# ==========================================================

def extract_fish(image):
    if image is None or image.size == 0:
        return None

    # Corriger les ombres de la feuille avant de chercher l'encre.
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    size = max(15, (min(gray.shape) // 12) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    paper = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    normalized = cv2.divide(gray, np.maximum(paper, 1), scale=255)
    ink = cv2.inRange(normalized, 0, 215)
    # Comparer la chromaticite au papier : un rose pale peut avoir
    # une saturation faible, surtout avec une feuille bleutee par la camera.
    lab = cv2.cvtColor(cv2.GaussianBlur(image, (3, 3), 0), cv2.COLOR_BGR2LAB)
    chroma = lab[:, :, 1:].astype(np.float32)
    border = np.concatenate((chroma[0], chroma[-1], chroma[:, 0], chroma[:, -1]))
    paper_chroma = np.median(border, axis=0)
    border_distance = np.linalg.norm(border - paper_chroma, axis=1)
    median = np.median(border_distance)
    noise = np.median(np.abs(border_distance - median))
    color_threshold = max(5.0, median + 4 * max(1.0, noise))
    ink[np.linalg.norm(chroma - paper_chroma, axis=2) > color_threshold] = 255
    # Raccorder seulement les petites interruptions du trait exterieur.
    gap = max(3, int(min(gray.shape) * 0.008) | 1)
    ink = cv2.morphologyEx(
        ink, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap, gap)),
    )
    contours, _ = cv2.findContours(
        ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    height, width = gray.shape
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        # Un bord de feuille ou de cadrage n'est pas un poisson.
        if x == 0 or y == 0 or x + w >= width or y + h >= height:
            continue
        if area >= max(30, height * width * 0.002):
            candidates.append(contour)
    if not candidates:
        print('Aucun poisson ferme detecte : recadrez avec une marge de papier.')
        return None

    contour = max(candidates, key=cv2.contourArea)
    mask = np.zeros(gray.shape, dtype=np.uint8)
    # Remplir le contour conserve les zones blanches et tous les details.
    cv2.drawContours(mask, [contour], -1, 255, cv2.FILLED)
    x, y, w, h = cv2.boundingRect(contour)
    x1, y1 = max(0, x - 2), max(0, y - 2)
    x2, y2 = min(width, x + w + 2), min(height, y + h + 2)
    fish = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2BGRA)
    fish[:, :, 3] = mask[y1:y2, x1:x2]
    return fish


CAMERA_FLIPS = {'horizontal': False, 'vertical': False}


def orient_camera(frame):
    horizontal, vertical = CAMERA_FLIPS['horizontal'], CAMERA_FLIPS['vertical']
    if horizontal or vertical:
        return cv2.flip(frame, -1 if horizontal and vertical else (1 if horizontal else 0))
    return frame


def scan_fish(kind=None):
    # Une seule boucle de fenetre : Pygame continue a traiter les evenements
    # pendant la capture, le cadrage et la validation.
    screen = pygame.display.get_surface()
    font = pygame.font.Font(None, 26)
    clock = pygame.time.Clock()
    cap = cv2.VideoCapture(CAMERA_ID)
    captured = None
    frame = None
    fish = None
    start = None
    selection = None
    state = 'capture'
    use_rig = False
    rig_checkbox = pygame.Rect(820, 48, 355, 32)
    flip_buttons = [('horizontal', pygame.Rect(20, 48, 260, 30)),
                    ('vertical', pygame.Rect(295, 48, 260, 30))]
    message = 'ESPACE : capturer | Echap : annuler'
    last_frame = pygame.time.get_ticks()

    def configure_rig():
        nonlocal use_rig, message
        rig = edit_rig(cv_to_pygame(fish), kind)
        if rig is not None:
            return fish, rig
        use_rig = False
        message = 'Squelette annule : clique pour reessayer | Entree : ajouter sans squelette'
        return None

    try:
        if not cap.isOpened():
            raise RuntimeError('Camera indisponible. Ferme les autres applications utilisant la camera.')
        while True:
            clock.tick(30)
            if state == 'capture':
                ok, current = cap.read()
                if ok and current is not None:
                    frame = orient_camera(current)
                    last_frame = pygame.time.get_ticks()
                elif pygame.time.get_ticks() - last_frame > 3000:
                    raise RuntimeError('La camera ne fournit aucune image.')
            screen.fill((20, 48, 65))
            view = None
            if frame is not None:
                display = frame if state == 'capture' else captured
                if state == 'preview':
                    alpha = fish[:, :, 3:4].astype(np.float32) / 255
                    display = (fish[:, :, :3] * alpha + np.array([175, 120, 20]) * (1-alpha)).astype(np.uint8)
                rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
                surface = pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), 'RGB')
                scale = min((SCREEN_WIDTH - 40) / surface.get_width(), (SCREEN_HEIGHT - 120) / surface.get_height())
                surface = pygame.transform.smoothscale(surface, (max(1, round(surface.get_width()*scale)), max(1, round(surface.get_height()*scale))))
                view = surface.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2+25))
                screen.blit(surface, view)
                if state == 'crop' and selection is not None:
                    pygame.draw.rect(screen, (80, 220, 255), selection, 2)
            screen.blit(font.render(message, True, 'white'), (20, 20))
            if state == 'capture':
                for axis, rect in flip_buttons:
                    active = CAMERA_FLIPS[axis]
                    pygame.draw.rect(screen, (50, 145, 95) if active else (45, 105, 145), rect, border_radius=5)
                    label = font.render(f'Miroir {axis} : {"oui" if active else "non"}', True, 'white')
                    screen.blit(label, label.get_rect(center=rect.center))
            if state == 'crop':
                screen.blit(font.render('Trace un rectangle autour de tout l animal avec une marge de papier.', True, 'white'), (20, 50))
            if kind is not None and state in ('crop', 'preview'):
                pygame.draw.rect(screen, (45, 145, 95) if use_rig else (40, 105, 145), rig_checkbox, border_radius=5)
                label = ('[X]' if use_rig else '[ ]') + ' Ajouter un squelette'
                screen.blit(font.render(label, True, 'white'), (rig_checkbox.x + 10, rig_checkbox.y + 5))
            pygame.display.flip()
            for event in pygame.event.get():
                if (kind is not None and state in ('crop', 'preview') and
                        event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and rig_checkbox.collidepoint(event.pos)):
                    use_rig = not use_rig
                    if use_rig and state == 'preview':
                        result = configure_rig()
                        if result is not None:
                            return result
                        continue
                    if use_rig and selection is not None and view is not None:
                        # Le clic detoure le cadre puis ouvre directement le squelette.
                        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
                    else:
                        message = ('Squelette active : trace le cadre puis Entree pour le modifier'
                                   if use_rig else 'Souris : cadrer | Entree : detourer | Echap : annuler')
                        continue
                if state == 'capture' and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for axis, rect in flip_buttons:
                        if rect.collidepoint(event.pos):
                            CAMERA_FLIPS[axis] = not CAMERA_FLIPS[axis]
                            if frame is not None:
                                frame = cv2.flip(frame, 1 if axis == 'horizontal' else 0)
                if event.type == pygame.QUIT:
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if state == 'capture' and event.key == pygame.K_SPACE and frame is not None:
                        captured = frame.copy()
                        state = 'crop'
                        message = 'Souris : cadrer | Entree : detourer | Echap : annuler'
                    elif state == 'crop' and event.key == pygame.K_RETURN and selection is not None and view is not None:
                        rect = selection.clip(view)
                        x1 = max(0, int((rect.left-view.left)*captured.shape[1]/view.width))
                        y1 = max(0, int((rect.top-view.top)*captured.shape[0]/view.height))
                        x2 = min(captured.shape[1], int((rect.right-view.left)*captured.shape[1]/view.width))
                        y2 = min(captured.shape[0], int((rect.bottom-view.top)*captured.shape[0]/view.height))
                        if x2-x1 < 5 or y2-y1 < 5:
                            message = 'Cadre trop petit : trace un nouveau rectangle.'
                            continue
                        crop = captured[y1:y2, x1:x2]
                        fish = extract_fish(crop)
                        if fish is None:
                            message = 'Animal non detecte : ajuste le rectangle puis Entree.'
                        else:
                            state = 'preview'
                            message = 'Entree : ajouter cet animal | R : recadrer | Echap : annuler'
                            if use_rig:
                                result = configure_rig()
                                if result is not None:
                                    return result
                    elif state == 'preview':
                        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            if kind is None:
                                return fish
                            if use_rig:
                                result = configure_rig()
                                if result is not None:
                                    return result
                                continue
                            return fish, None
                        if event.key == pygame.K_r:
                            state = 'crop'
                            message = 'Souris : cadrer | Entree : detourer | Echap : annuler'
                if state == 'crop' and view is not None:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and view.collidepoint(event.pos):
                        start = event.pos
                        selection = pygame.Rect(start, (0, 0))
                    if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP) and start is not None:
                        selection = pygame.Rect(start, (event.pos[0]-start[0], event.pos[1]-start[1]))
                        selection.normalize()
                        selection = selection.clip(view)
                        if event.type == pygame.MOUSEBUTTONUP:
                            start = None
    finally:
        cap.release()

# ==========================================================
# CONVERSION OPENCV -> PYGAME
# ==========================================================

def cv_to_pygame(image):
    image = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)

    image = np.rot90(image)
    image = np.flipud(image)

    surface = pygame.surfarray.make_surface(
        image[:, :, :3]
    )

    alpha = pygame.surfarray.make_surface(
        np.repeat(
            image[:, :, 3][:, :, None],
            3,
            axis=2
        )
    )

    surface = surface.convert_alpha()

    alpha_array = pygame.surfarray.array3d(alpha)[:, :, 0]

    pygame.surfarray.pixels_alpha(surface)[:] = alpha_array

    return surface


# ==========================================================
# BULLES
# ==========================================================

class Bubble:

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = random.randint(20, VIEW.world_width - 20)
        self.y = SCREEN_HEIGHT + random.randint(0, 300)

        self.radius = random.randint(3, 10)

        self.speed = random.uniform(0.5, 2)

        self.wave = random.random() * 10

    def update(self):

        self.y -= self.speed

        self.wave += 0.03

        self.x += math.sin(self.wave) * 0.3

        if self.y < -20:
            self.reset()

    def draw(self, screen):

        pygame.draw.circle(
            screen,
            (200, 230, 255),
            (int(self.x), int(self.y)),
            self.radius,
            1
        )


# ==========================================================
# POISSON
# ==========================================================

class Fish:
    kind = 'poisson'
    def __init__(self, image, rig=None):
        self.rig = validate_rig(rig, self.kind)
        self.source_image = image.copy()
        self.speed_scale = 1.0
        self.size_scale = 1.0
        self.rebuild_frames()
        self.x = VIEW.world_width / 2
        self.y = SCREEN_HEIGHT / 2
        self.direction = -1
        self.speed = random.uniform(90, 135)
        self.phase = 0.0
        self.turn_elapsed = None
        self.turn_duration = 0.8
        self.turn_from = self.direction
        self.until_turn = random.uniform(5, 10)
        self.target_y = self.y
        self.social_target = None
        self.social_face = None
        self.social_cooldown = random.uniform(1, 3)
        self.behavior = AnimalBehavior(self.kind)

    def set_size(self, scale):
        self.size_scale = max(0.05, min(2.0, float(scale)))
        self.rebuild_frames()
        self.x = max(self.width / 2 + 20, min(VIEW.world_width - self.width / 2 - 20, self.x))
        self.y = max(self.height / 2 + 30, min(SCREEN_HEIGHT - 100 - self.height / 2, self.y))
        self.target_y = self.y

    def rebuild_frames(self):
        if rebuild_rigged(self):
            return
        image = self.source_image
        ratio = min(FISH_WIDTH / image.get_width(), 240 / image.get_height()) * self.size_scale
        width = max(1, round(image.get_width() * ratio))
        height = max(1, round(image.get_height() * ratio))
        base = pygame.transform.smoothscale(image, (width, height))
        if not FISH_HEAD_LEFT:
            base = pygame.transform.flip(base, True, False)

        # La tete reste stable ; la deformation augmente vers la queue.
        amplitude = max(3, round(height * 0.055))
        self.frames_left = []
        for index in range(32):
            phase = index * math.tau / 32
            frame = pygame.Surface((width, height + amplitude * 2), pygame.SRCALPHA)
            for x in range(width):
                tail = max(0.0, (x / max(1, width - 1) - 0.45) / 0.55)
                offset = round(amplitude * tail ** 2 * math.sin(phase - tail * 2))
                frame.blit(base, (x, amplitude + offset), (x, 0, 1, height))
            self.frames_left.append(frame)
        self.frames_right = [pygame.transform.flip(f, True, False) for f in self.frames_left]
        self.width = width
        self.height = height + amplitude * 2

    def update(self, dt=1 / 60):
        dt = max(0.0, min(dt, 0.05))
        if self.behavior.update(self, dt, VIEW.world_width):
            return
        self.phase = (self.phase + dt * 2.2) % 1.0
        if self.social_target is not None:
            self.update_social(dt)
            return
        self.until_turn -= dt
        left = self.width / 2 + 20
        right = VIEW.world_width - left
        near_edge = ((self.direction < 0 and self.x <= left + 45) or
                     (self.direction > 0 and self.x >= right - 45))
        if self.turn_elapsed is None and (near_edge or self.until_turn <= 0):
            self.turn_elapsed = 0.0
            self.turn_from = self.direction

        heading = self.direction
        if self.turn_elapsed is not None:
            self.turn_elapsed = min(self.turn_duration, self.turn_elapsed + dt)
            progress = self.turn_elapsed / self.turn_duration
            heading = self.turn_from * math.cos(math.pi * progress)
            self.direction = self.turn_from if progress < 0.5 else -self.turn_from
            if progress >= 1:
                self.turn_elapsed = None
                self.until_turn = random.uniform(5, 10)
                self.target_y = random.uniform(self.height / 2 + 30,
                                               SCREEN_HEIGHT - 100 - self.height / 2)
        self.x = max(left, min(right, self.x + self.speed * heading * dt))
        self.y += (self.target_y - self.y) * min(1.0, dt * 0.7)

    def update_social(self, dt):
        tx, ty = self.social_target
        tx = max(self.width / 2 + 20, min(VIEW.world_width - self.width / 2 - 20, tx))
        ty = max(self.height / 2 + 30, min(SCREEN_HEIGHT - 100 - self.height / 2, ty))
        dx, dy = tx - self.x, ty - self.y
        desired = (1 if dx > 0 else -1) if abs(dx) > 4 else (self.social_face or self.direction)
        if desired != self.direction and self.turn_elapsed is None:
            self.turn_from = self.direction
            self.turn_elapsed = 0.0
        if self.turn_elapsed is not None:
            self.turn_elapsed = min(self.turn_duration, self.turn_elapsed + dt)
            self.direction = self.turn_from if self.turn_elapsed < self.turn_duration / 2 else -self.turn_from
            if self.turn_elapsed >= self.turn_duration:
                self.turn_elapsed = None
            return
        distance = math.hypot(dx, dy)
        step = min(distance, self.speed * 1.25 * dt)
        if distance > 1 and dx * self.direction >= 0:
            self.x += dx / distance * step
            self.y += dy / distance * step

    def draw(self, screen):
        index = int(self.phase * len(self.frames_left)) % len(self.frames_left)
        frames = self.frames_right if self.direction > 0 else self.frames_left
        image = rig_frame(self, frames[index])
        if self.turn_elapsed is not None:
            # Vue de profil, puis de face, puis de l'autre cote.
            progress = self.turn_elapsed / self.turn_duration
            scale = max(0.08, abs(math.cos(math.pi * progress)))
            image = pygame.transform.smoothscale(
                image, (max(1, round(image.get_width() * scale)), image.get_height()))
        bob = math.sin(self.phase * math.tau) * 1.5
        self.behavior.draw(screen, image, (self.x, self.y + bob))

# ==========================================================
# DECOR AQUARIUM
# ==========================================================

class Jellyfish(Fish):
    kind = 'meduse'

    def __init__(self, image, rig=None):
        super().__init__(image, rig=rig)
        self.drift_speed = random.choice((-1, 1)) * random.uniform(12, 22)
        self.drift_target = self.drift_speed
        self.drift_time = random.uniform(6, 12)

    def rebuild_frames(self):
        if rebuild_rigged(self):
            return
        image = self.source_image
        ratio = min(150 / image.get_width(), 200 / image.get_height()) * self.size_scale
        w, h = max(1, round(image.get_width() * ratio)), max(1, round(image.get_height() * ratio))
        base = pygame.transform.smoothscale(image, (w, h))
        self.width, self.height = w + 20, h + 12
        self.jelly_frames = []
        for index in range(32):
            phase = index * math.tau / 32
            frame = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            for y in range(h):
                depth = y / max(1, h - 1)
                tail = max(0, (depth - 0.35) / 0.65)
                row_width = max(1, round(w * (1 - 0.10 * math.sin(phase) * (1 - tail))))
                row = pygame.transform.smoothscale(base.subsurface((0, y, w, 1)), (row_width, 1))
                sway = round(8 * tail * math.sin(phase - depth * 5))
                frame.blit(row, ((self.width - row_width) // 2 + sway, y + 6))
            self.jelly_frames.append(frame)

    def update(self, dt=1 / 60):
        dt = max(0, min(dt, 0.05))
        if self.behavior.update(self, dt, VIEW.world_width):
            return
        self.phase = (self.phase + dt * 0.85) % 1
        self.until_turn -= dt
        top = self.height / 2 + 30
        bottom = SCREEN_HEIGHT - 100 - self.height / 2
        if self.y <= top + 2:
            self.direction = 1
        elif self.y >= bottom - 2:
            self.direction = -1
        elif self.until_turn <= 0:
            self.direction *= -1
            self.until_turn = random.uniform(5, 9)
        pulse = 12 + 28 * max(0, math.sin(self.phase * math.tau))
        self.y = max(top, min(bottom, self.y + self.direction * pulse * dt))
        self.drift_time -= dt
        left, right = self.width / 2 + 20, VIEW.world_width - self.width / 2 - 20
        if self.x < left + 40:
            self.drift_target = 18
        elif self.x > right - 40:
            self.drift_target = -18
        elif self.drift_time <= 0:
            self.drift_target = random.choice((-1, 1)) * random.uniform(12, 22)
            self.drift_time = random.uniform(6, 12)
        self.drift_speed += (self.drift_target - self.drift_speed) * (1 - math.exp(-dt * 1.5))
        self.x += (self.drift_speed + math.sin(self.phase * math.tau) * 4) * dt
        self.x = max(left, min(right, self.x))

    def draw(self, screen):
        frame = self.jelly_frames[int(self.phase * 32) % 32]
        frame = rig_frame(self, frame)
        self.behavior.draw(screen, frame, (self.x, self.y))


class Crab(Fish):
    kind = 'crabe'

    def __init__(self, image, rig=None):
        super().__init__(image, rig=rig)
        self.walk_time = random.uniform(2, 5)
        self.pause_time = 0.0
        self.on_sand()

    def on_sand(self):
        self.y = SCREEN_HEIGHT - 25 - self.height / 2
        self.target_y = self.y

    def set_size(self, scale):
        super().set_size(scale)
        self.on_sand()

    def rebuild_frames(self):
        if rebuild_rigged(self):
            return
        image = self.source_image
        ratio = min(160 / image.get_width(), 110 / image.get_height()) * self.size_scale
        w, h = max(1, round(image.get_width() * ratio)), max(1, round(image.get_height() * ratio))
        base = pygame.transform.smoothscale(image, (w, h))
        self.width, self.height = w, h + 12
        self.crab_frames = []
        # Garder le corps stable et faire alterner les appendices lateraux.
        for index in range(24):
            phase = index * math.tau / 24
            frame = pygame.Surface((w, h + 12), pygame.SRCALPHA)
            for x in range(w):
                side = (x / max(1, w - 1) - 0.5) * 2
                weight = max(0, (abs(side) - 0.3) / 0.7)
                offset = round(5 * weight * math.sin(phase + side * 7))
                frame.blit(base, (x, 6 + offset), (x, 0, 1, h))
            self.crab_frames.append(frame)

    def update(self, dt=1 / 60):
        dt = max(0, min(dt, 0.05))
        if self.behavior.update(self, dt, VIEW.world_width):
            return
        self.on_sand()
        if self.pause_time > 0:
            self.pause_time = max(0, self.pause_time - dt)
            return
        self.phase = (self.phase + dt * gait_rate(self, 2.5)) % 1
        left = self.width / 2 + 20
        right = VIEW.world_width - left
        self.x += self.direction * 42 * dt
        if self.x <= left:
            self.x, self.direction = left, 1
        elif self.x >= right:
            self.x, self.direction = right, -1
        self.walk_time -= dt
        if self.walk_time <= 0:
            self.pause_time = random.uniform(0.6, 1.8)
            self.walk_time = random.uniform(2, 5)
            if random.random() < 0.5:
                self.direction *= -1

    def draw(self, screen):
        frame = self.crab_frames[int(self.phase * 24) % 24]
        frame = rig_frame(self, frame)
        self.behavior.draw(screen, frame, (self.x, self.y))


class Starfish(Crab):
    kind = 'etoile'

    def rebuild_frames(self):
        if rebuild_rigged(self):
            return
        image = self.source_image
        ratio = min(130 / image.get_width(), 130 / image.get_height()) * self.size_scale
        w, h = max(1, round(image.get_width() * ratio)), max(1, round(image.get_height() * ratio))
        base = pygame.transform.smoothscale(image, (w, h))
        self.width, self.height = w + 8, h + 8
        self.star_frames = []
        for index in range(32):
            phase = index * math.tau / 32
            frame = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            for y in range(h):
                edge = abs(2 * y / max(1, h - 1) - 1)
                row_width = max(1, round(w * (1 - 0.025 * edge * (1 + math.sin(phase + y / max(1, h) * math.tau)))))
                row = pygame.transform.smoothscale(base.subsurface((0, y, w, 1)), (row_width, 1))
                offset = round(2 * edge * math.sin(phase + y / max(1, h) * math.tau))
                frame.blit(row, ((self.width - row_width) // 2 + offset, y + 4))
            self.star_frames.append(frame)

    def update(self, dt=1 / 60):
        dt = max(0, min(dt, 0.05))
        if self.behavior.update(self, dt, VIEW.world_width):
            return
        self.on_sand()
        self.phase = (self.phase + dt * 0.22) % 1
        if self.pause_time > 0:
            self.pause_time = max(0, self.pause_time - dt)
            return
        left, right = self.width / 2 + 20, VIEW.world_width - self.width / 2 - 20
        self.x += self.direction * 7 * dt
        if self.x <= left:
            self.x, self.direction = left, 1
        elif self.x >= right:
            self.x, self.direction = right, -1
        self.walk_time -= dt
        if self.walk_time <= 0:
            self.pause_time = random.uniform(2, 4)
            self.walk_time = random.uniform(6, 12)
            if random.random() < 0.3:
                self.direction *= -1

    def draw(self, screen):
        frame = self.star_frames[int(self.phase * 32) % 32]
        frame = rig_frame(self, frame)
        self.behavior.draw(screen, frame, (self.x, self.y))


class Turtle(Fish):
    kind = 'tortue'

    def __init__(self, image, rig=None):
        super().__init__(image, rig=rig)
        self.speed = random.uniform(32, 48)

    def rebuild_frames(self):
        if rebuild_rigged(self):
            return
        image = self.source_image
        ratio = min(190 / image.get_width(), 150 / image.get_height()) * self.size_scale
        w, h = max(1, round(image.get_width() * ratio)), max(1, round(image.get_height() * ratio))
        base = pygame.transform.smoothscale(image, (w, h))
        if not FISH_HEAD_LEFT:
            base = pygame.transform.flip(base, True, False)
        self.width, self.height = w + 12, h + 12
        self.frames_left = []
        # La carapace au centre reste stable, les nageoires battent aux bords.
        for index in range(32):
            phase = index * math.tau / 32
            frame = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            for y in range(h):
                edge = abs(2 * y / max(1, h - 1) - 1)
                fin = max(0, (edge - 0.35) / 0.65)
                offset = round(5 * fin * math.sin(phase + (0 if y < h / 2 else math.pi)))
                frame.blit(base, (6 + offset, y + 6), (0, y, w, 1))
            self.frames_left.append(frame)
        self.frames_right = [pygame.transform.flip(frame, True, False) for frame in self.frames_left]

    def update(self, dt=1 / 60):
        phase = self.phase
        super().update(dt)
        self.phase = (phase + max(0, min(dt, 0.05)) * 0.65) % 1


class FishInteractions:
    def __init__(self):
        self.pairs = []

    def start(self, first, second, kind=None):
        first, second = sorted((first, second), key=lambda fish: fish.x)
        self.pairs.append(dict(a=first, b=second,
                               kind=kind or random.choice(('jeu', 'bisou', 'poursuite')),
                               time=0.0, contact=0.0,
                               center=((first.x + second.x) / 2, (first.y + second.y) / 2)))

    def update(self, fishes, dt):
        fishes = [fish for fish in fishes if fish.kind == 'poisson']
        dt = max(0.0, min(dt, 0.05))
        busy = {fish for pair in self.pairs for fish in (pair['a'], pair['b'])}
        for fish in fishes:
            fish.social_cooldown = max(0, fish.social_cooldown - dt)
        for i, first in enumerate(fishes):
            if first in busy or first.social_cooldown > 0:
                continue
            for second in fishes[i + 1:]:
                if second in busy or second.social_cooldown > 0:
                    continue
                if math.hypot(first.x - second.x, first.y - second.y) < 290 and random.random() < 1 - math.exp(-1.2 * dt):
                    self.start(first, second)
                    busy.update((first, second))
                    break
        for pair in self.pairs[:]:
            a, b = pair['a'], pair['b']
            pair['time'] += dt
            t = pair['time']
            cx, cy = pair['center']
            # Garder les trajectoires communes loin des bords et du sable.
            cx = max(300, min(VIEW.world_width - 300, cx))
            margin = max(a.height, b.height) / 2 + 95
            cy = max(margin, min(SCREEN_HEIGHT - 100 - margin, cy))
            if pair['kind'] == 'bisou':
                a.social_target = (cx - a.width / 2, cy)
                b.social_target = (cx + b.width / 2, cy)
                a.social_face, b.social_face = 1, -1
                close = all(math.hypot(f.x - f.social_target[0], f.y - f.social_target[1]) < 7 for f in (a, b))
                if close and a.direction == 1 and b.direction == -1 and a.turn_elapsed is None and b.turn_elapsed is None:
                    pair['contact'] += dt
            elif pair['kind'] == 'jeu':
                angle = t * 0.65
                for fish, phase in ((a, angle), (b, angle + math.pi)):
                    fish.social_target = (cx + 130 * math.cos(phase), cy + 55 * math.sin(phase))
            else:
                # Le meneur dessine une boucle ; son partenaire suit sa queue.
                angle = t * 0.45
                a.social_target = (cx + 180 * math.sin(angle), cy + 55 * math.sin(angle * 2))
                b.social_target = (a.x - a.direction * (a.width + b.width) * 0.6, a.y + 15)
            if t > 12 or pair['contact'] > 1.5 or (pair['kind'] != 'bisou' and t > 8):
                for fish in (a, b):
                    fish.social_target = None
                    fish.social_face = None
                    fish.social_cooldown = random.uniform(5, 9)
                    fish.until_turn = random.uniform(2, 5)
                    fish.target_y = fish.y
                self.pairs.remove(pair)

    def draw(self, screen, font):
        for pair in self.pairs:
            a, b = pair['a'], pair['b']
            x = round((a.x + b.x) / 2)
            y = round(min(a.y - a.height / 2, b.y - b.height / 2) - 18)
            label = {'jeu': 'On joue !', 'bisou': 'Bisou', 'poursuite': 'Attrape-moi !'}[pair['kind']]
            text = font.render(label, True, (255, 235, 185))
            screen.blit(text, text.get_rect(midbottom=(x, y)))
            if pair['contact'] > 0:
                y -= round(pair['contact'] * 22) + 22
                color = (255, 100, 150)
                pygame.draw.circle(screen, color, (x - 5, y), 7)
                pygame.draw.circle(screen, color, (x + 5, y), 7)
                pygame.draw.polygon(screen, color, [(x - 11, y + 2), (x + 11, y + 2), (x, y + 15)])


def draw_aquarium(screen, time):

    # Eau
    screen.fill((20, 120, 175))

    # Rayons de lumière
    overlay = pygame.Surface(
        (screen.get_width(), SCREEN_HEIGHT),
        pygame.SRCALPHA
    )

    for x in range(0, screen.get_width(), 220):

        offset = math.sin(time * 0.0005 + x) * 40

        pygame.draw.polygon(
            overlay,
            (255, 255, 255, 10),
            [
                (x + offset, 0),
                (x + 100 + offset, 0),
                (x + 250, SCREEN_HEIGHT)
            ]
        )

    screen.blit(overlay, (0, 0))

    # Sable
    pygame.draw.rect(
        screen,
        (194, 166, 105),
        (
            0,
            SCREEN_HEIGHT - 70,
            screen.get_width(),
            70
        )
    )

    # Rochers

    for x in range(100, screen.get_width(), 325):

        pygame.draw.ellipse(
            screen,
            (90, 90, 80),
            (
                x,
                SCREEN_HEIGHT - 100,
                100,
                50
            )
        )

    # Algues

    for x in range(
        50,
        screen.get_width(),
        130
    ):

        height = random_seeded_height(x)

        pygame.draw.line(
            screen,
            (30, 120, 50),
            (
                x,
                SCREEN_HEIGHT - 70
            ),
            (
                x + math.sin(time * 0.002 + x) * 10,
                SCREEN_HEIGHT - height
            ),
            7
        )


def random_seeded_height(x):

    return 100 + ((x * 37) % 100)


# ==========================================================
# PROGRAMME PRINCIPAL
# ==========================================================

def save_aquarium(fishes, path=SAVE_PATH):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    records = []
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        for index, fish in enumerate(fishes):
            surface = fish.source_image
            rgba = np.frombuffer(pygame.image.tostring(surface, 'RGBA'), np.uint8)
            rgba = rgba.reshape(surface.get_height(), surface.get_width(), 4)
            ok, encoded = cv2.imencode('.png', cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
            if not ok:
                raise OSError('Impossible de sauvegarder un poisson')
            name = f'fish_{index}.png'
            archive.writestr(name, encoded.tobytes())
            records.append(dict(image=name, x=fish.x, y=fish.y, direction=fish.direction, size=fish.size_scale, kind=fish.kind, rig=fish.rig, speed=fish.speed_scale))
        archive.writestr('aquarium.json', json.dumps(dict(version=1, fishes=records, view=VIEW.settings())))
    temporary.replace(path)


def load_aquarium(path=SAVE_PATH):
    path = Path(path)
    if not path.exists():
        return []
    fishes = []
    with zipfile.ZipFile(path) as archive:
        data = json.loads(archive.read('aquarium.json'))
        if data['version'] != 1:
            raise ValueError('Version de sauvegarde inconnue')
        VIEW.restore(data.get('view', {}))
        for index, record in enumerate(data['fishes']):
            report_progress(f"Animal {index + 1}/{len(data['fishes'])} : {record.get('kind', 'poisson')}")
            encoded = np.frombuffer(archive.read(record['image']), np.uint8)
            pixels = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
            if pixels is None or pixels.ndim != 3 or pixels.shape[2] != 4:
                raise ValueError('Image de poisson invalide')
            animal_class = {'poisson': Fish, 'meduse': Jellyfish, 'crabe': Crab, 'etoile': Starfish, 'tortue': Turtle}[record.get('kind', 'poisson')]
            fish = animal_class(cv_to_pygame(pixels), rig=record.get('rig'))
            fish.set_size(record.get("size", 1.0))
            fish.speed_scale = max(0.05, min(2.0, float(record.get("speed", data.get("speed", 1.0)))))
            fish.x = max(fish.width / 2 + 20, min(VIEW.world_width - fish.width / 2 - 20, float(record['x'])))
            fish.y = max(fish.height / 2 + 30, min(SCREEN_HEIGHT - 100 - fish.height / 2, float(record['y'])))
            fish.target_y = fish.y
            fish.direction = -1 if record['direction'] < 0 else 1
            if isinstance(fish, Crab):
                fish.on_sand()
            fishes.append(fish)
    return fishes


class AquariumManager:
    def __init__(self):
        self.open = False
        self.scroll = 0
        self.dragging = None
        self.dragging_kind = "size"
        self.button = pygame.Rect(SCREEN_WIDTH - 205, 38, 190, 32)
        self.panel = pygame.Rect(170, 90, 860, 550)
        self.close = pygame.Rect(900, 106, 110, 32)
        self.rows = pygame.Rect(190, 168, 820, 440)

    def row_controls(self, index):
        y = self.rows.y + index * 150 - self.scroll
        return (pygame.Rect(520, y + 58, 235, 22),
                pygame.Rect(780, y + 12, 110, 32),
                pygame.Rect(780, y + 54, 110, 32))

    def handle(self, event, fishes, interactions):
        changed = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.button.collidepoint(event.pos):
                self.open = not self.open
                self.dragging = None
                return True, False
            if self.open and self.close.collidepoint(event.pos):
                self.open = False
                self.dragging = None
                return True, False
        if not self.open:
            return False, False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.open = False
            self.dragging = None
            return True, False
        if event.type == pygame.MOUSEWHEEL and self.dragging is None:
            self.scroll = max(0, min(max(0, len(fishes) * 150 - self.rows.height), self.scroll - event.y * 55))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rows.collidepoint(event.pos):
            for index, fish in enumerate(fishes):
                slider, duplicate, delete = self.row_controls(index)
                if duplicate.collidepoint(event.pos):
                    clone = type(fish)(fish.source_image, rig=fish.rig)
                    clone.x, clone.y = fish.x + 35, fish.y + 30
                    clone.direction = fish.direction
                    clone.set_size(fish.size_scale)
                    clone.speed_scale = fish.speed_scale
                    fishes.append(clone)
                    changed = True
                    break
                if delete.collidepoint(event.pos):
                    fishes.remove(fish)
                    changed = True
                    break
                if slider.move(0, 50).inflate(12, 16).collidepoint(event.pos):
                    self.dragging = fish
                    self.dragging_kind = "speed"
                    break
                if slider.inflate(12, 16).collidepoint(event.pos):
                    self.dragging_kind = "size"
                    self.dragging = fish
                    break
        if self.dragging is not None and event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            if self.dragging in fishes:
                slider = self.row_controls(fishes.index(self.dragging))[0]
                value = round(0.05 + 1.95 * max(0, min(1, (event.pos[0] - slider.x) / slider.width)), 2)
                if self.dragging_kind == "speed":
                    changed = value != self.dragging.speed_scale
                    self.dragging.speed_scale = value
                elif value != self.dragging.size_scale:
                    self.dragging.set_size(value)
                    changed = True
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.dragging = None
        if changed:
            # Liberer aussi le partenaire d'un poisson supprime ou redimensionne.
            for pair in interactions.pairs:
                for fish in (pair['a'], pair['b']):
                    fish.social_target = None
                    fish.social_face = None
                    fish.social_cooldown = 3
            interactions.pairs.clear()
            self.scroll = min(self.scroll, max(0, len(fishes) * 150 - self.rows.height))
        # Ctrl+S reste disponible pendant la gestion.
        return event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL), changed

    def draw(self, screen, font, fishes):
        def button(rect, text, color=(35, 110, 145)):
            pygame.draw.rect(screen, color, rect, border_radius=6)
            label = font.render(text, True, (255, 255, 255))
            screen.blit(label, label.get_rect(center=rect.center))
        button(self.button, 'Gerer les animaux')
        if not self.open:
            return
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 15, 30, 155))
        screen.blit(overlay, (0, 0))
        pygame.draw.rect(screen, (20, 48, 65), self.panel, border_radius=12)
        screen.blit(font.render(f'Mes animaux ({len(fishes)})', True, 'white'), (192, 112))
        button(self.close, 'Fermer')
        previous_clip = screen.get_clip()
        screen.set_clip(self.rows)
        if not fishes:
            screen.blit(font.render('Aucun animal. Clique sur Ajouter un animal apres fermeture.', True, 'white'), (205, 200))
        for index, fish in enumerate(fishes):
            slider, duplicate, delete = self.row_controls(index)
            y = slider.y - 58
            if y + 150 <= self.rows.top or y >= self.rows.bottom:
                continue
            pygame.draw.rect(screen, (32, 70, 88), (195, y + 3, 810, 142), border_radius=6)
            image = fish.source_image
            ratio = min(120 / image.get_width(), 82 / image.get_height())
            thumb = pygame.transform.smoothscale(image, (max(1, round(image.get_width() * ratio)), max(1, round(image.get_height() * ratio))))
            screen.blit(thumb, thumb.get_rect(center=(275, y + 54)))
            name = {'poisson': 'Poisson', 'meduse': 'Meduse', 'crabe': 'Crabe', 'etoile': 'Etoile', 'tortue': 'Tortue'}[fish.kind]
            screen.blit(font.render(f'{name} {index + 1}', True, 'white'), (360, y + 24))
            screen.blit(font.render(f'Taille : {fish.size_scale:.0%}', True, 'white'), (520, y + 20))
            pygame.draw.line(screen, (110, 160, 180), (slider.left, slider.centery), (slider.right, slider.centery), 5)
            pygame.draw.circle(screen, (255, 220, 100), (round(slider.x + (fish.size_scale - 0.05) / 1.95 * slider.width), slider.centery), 9)
            speed = slider.move(0, 50)
            screen.blit(font.render(f'Vitesse : {fish.speed_scale:.0%}', True, 'white'), (520, y + 85))
            pygame.draw.line(screen, (110, 160, 180), speed.midleft, speed.midright, 5)
            pygame.draw.circle(screen, (130, 230, 190), (round(speed.x + (fish.speed_scale - 0.05) / 1.95 * speed.width), speed.centery), 9)
            button(duplicate, 'Dupliquer')
            button(delete, 'Supprimer', (160, 65, 65))
        screen.set_clip(previous_clip)
        screen.blit(font.render('Molette : defiler | Ctrl+S : sauvegarder les modifications', True, (215, 230, 240)), (192, 616))


def main():
    pygame.init()
    fullscreen = False
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED)
    fullscreen_button = pygame.Rect(15, 650, 180, 34)
    pygame.display.set_caption('Aquarium virtuel')
    font = pygame.font.Font(None, 24)
    status = ''
    try:
        with loading_screen('Chargement des animaux'):
            fishes = load_aquarium()
        status = f'{len(fishes)} animal(aux) recharge(s)' if fishes else 'Clique sur Ajouter un animal pour commencer'
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, cv2.error) as error:
        fishes = []
        status = 'Sauvegarde illisible : ' + str(error)
        print(status)
    status_until = pygame.time.get_ticks() + 8000
    bubbles = [Bubble() for _ in range(40)]
    interactions = FishInteractions()
    manager = AquariumManager()
    add_button = pygame.Rect(SCREEN_WIDTH - 410, 38, 195, 32)
    choices = [('Poisson', Fish, pygame.Rect(370, 265, 220, 50)),
               ('Meduse', Jellyfish, pygame.Rect(610, 265, 220, 50)),
               ('Crabe', Crab, pygame.Rect(370, 330, 220, 50)),
               ('Etoile de mer', Starfish, pygame.Rect(610, 330, 220, 50)),
               ('Tortue marine', Turtle, pygame.Rect(490, 395, 220, 50))]
    choosing = False
    clock = pygame.time.Clock()
    running = True
    dirty = False
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if not manager.open and not choosing:
                consumed, changed = VIEW.handle(event, fishes, interactions)
                dirty = dirty or changed
                if consumed:
                    continue
            toggle_fullscreen = event.type == pygame.KEYDOWN and event.key == pygame.K_F11
            controls_visible = not choosing and not manager.open
            if controls_visible and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                toggle_fullscreen = toggle_fullscreen or fullscreen_button.collidepoint(event.pos)
            if toggle_fullscreen:
                fullscreen = not fullscreen
                screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED | (pygame.FULLSCREEN if fullscreen else 0))
                continue
            animal_class = None
            if choosing:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    choosing = False
                    continue
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for label, cls, rect in choices:
                        if rect.collidepoint(event.pos):
                            animal_class = cls
                    choosing = False
                if animal_class is None and event.type != pygame.QUIT:
                    continue
            elif not manager.open and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and add_button.collidepoint(event.pos):
                choosing = True
                continue
            if animal_class is not None:
                try:
                    scanned = scan_fish(animal_class.kind)
                except (cv2.error, pygame.error, RuntimeError, OSError) as error:
                    import traceback
                    traceback.print_exc()
                    status = 'Scan impossible : ' + str(error).splitlines()[0]
                    status_until = pygame.time.get_ticks() + 15000
                    clock.tick()
                    dt = 0
                    continue
                if scanned is not None:
                    pixels, rig = scanned
                    animal = animal_class(cv_to_pygame(pixels), rig=rig)
                    animal.x = VIEW.x + random.uniform(animal.width / 2 + 60, SCREEN_WIDTH - animal.width / 2 - 60)
                    animal.y = random.uniform(animal.height / 2 + 30, SCREEN_HEIGHT - 100 - animal.height / 2)
                    animal.target_y = animal.y
                    if isinstance(animal, Crab):
                        animal.on_sand()
                    fishes.append(animal)
                    dirty = True
                    status = 'Animal ajoute ! Ctrl+S pour sauvegarder'
                else:
                    status = 'Ajout annule'
                status_until = pygame.time.get_ticks() + 6000
                clock.tick()
                dt = 0
                continue
            consumed, changed = manager.handle(event, fishes, interactions)
            dirty = dirty or changed
            if consumed:
                continue
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s and event.mod & pygame.KMOD_CTRL:
                    try:
                        save_aquarium(fishes)
                        dirty = False
                        status = 'Aquarium sauvegarde'
                    except (OSError, ValueError, cv2.error) as error:
                        status = 'Echec de sauvegarde : ' + str(error)
                    status_until = pygame.time.get_ticks() + 6000
        VIEW.update(dt, manager.open or choosing or VIEW.open)
        world = VIEW.background(draw_aquarium, pygame.time.get_ticks())
        for bubble in bubbles:
            bubble.update()
            bubble.draw(world)
        if manager.open or choosing or VIEW.open:
            dt = 0
        interactions.update(fishes, min(dt, 0.05))
        for fish in fishes:
            remaining = min(dt, 0.1) * fish.speed_scale
            while remaining > 0:
                step = min(remaining, 0.025)
                fish.update(step)
                remaining -= step
        for fish in fishes:
            fish.draw(world)
        interactions.draw(world, font)
        screen.blit(world, (-round(VIEW.x), 0))
        hint = f'Ctrl+S : sauvegarder | Echap : quitter | {len(fishes)} animal(aux)'
        if dirty:
            hint += ' | Non sauvegarde'
        screen.blit(font.render(hint, True, (255, 255, 255)), (15, 12))
        if pygame.time.get_ticks() < status_until:
            screen.blit(font.render(status, True, (255, 240, 170)), (15, 38))
        pygame.draw.rect(screen, (35, 110, 145), add_button, border_radius=6)
        label = font.render('Ajouter un animal', True, 'white')
        screen.blit(label, label.get_rect(center=add_button.center))
        pygame.draw.rect(screen, (35, 110, 145), fullscreen_button, border_radius=6)
        label = font.render('Mode fenetre' if fullscreen else 'Plein ecran', True, 'white')
        screen.blit(label, label.get_rect(center=fullscreen_button.center))
        VIEW.draw(screen, font)
        manager.draw(screen, font, fishes)
        if choosing:
            shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 15, 30, 170))
            screen.blit(shade, (0, 0))
            pygame.draw.rect(screen, (20, 48, 65), (350, 210, 500, 400), border_radius=12)
            screen.blit(font.render('Quel animal veux-tu scanner ?', True, 'white'), (410, 240))
            for label, cls, rect in choices:
                pygame.draw.rect(screen, (35, 110, 145), rect, border_radius=8)
                text = font.render(label, True, 'white')
                screen.blit(text, text.get_rect(center=rect.center))
            screen.blit(font.render('Meduse : cloche en haut, tentacules en bas.', True, 'white'), (390, 460))
            screen.blit(font.render('Crabe : de face, pattes vers le bas.', True, 'white'), (410, 485))
            screen.blit(font.render('Etoile : vue de dessus, les cinq bras visibles.', True, 'white'), (390, 510))
            screen.blit(font.render('Tortue : vue de dessus, tete a gauche.', True, 'white'), (400, 535))
            screen.blit(font.render('Echap ou clic a cote : annuler', True, 'white'), (440, 575))
        pygame.display.flip()
    pygame.quit()


# ==========================================================
# DEMARRAGE
# ==========================================================

if __name__ == "__main__":
    main()
