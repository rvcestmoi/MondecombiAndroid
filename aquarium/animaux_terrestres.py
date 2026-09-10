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
SAVE_PATH = Path(__file__).resolve().with_name('prairie.zip')

# Plus cette valeur est grande, plus on supprime de gris clair
WHITE_THRESHOLD = 210


# ==========================================================
# CAPTURE DU POISSON
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
        print('Aucun animal ferme detecte : recadrez avec une marge de papier.')
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

class Fish:
    kind = 'poisson'
    def __init__(self, image, rig=None):
        self.rig = validate_rig(rig, self.kind)
        self.source_image = image.copy()
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
        ratio = min(ratio, 300 / image.get_height())
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

class LandAnimal(Fish):
    kind = 'chat'
    label = 'Chat'
    walk_speed = 45

    def __init__(self, image, rig=None):
        super().__init__(image, rig=rig)
        self.rest = 0.0
        self.social_jump = 0.0
        self.walk_time = random.uniform(4, 9)
        self.ground_y = random.uniform(560, 660)
        self.on_ground()

    def on_ground(self):
        self.y = self.ground_y - self.height / 2
        self.target_y = self.y

    def set_size(self, scale):
        super().set_size(scale)
        self.on_ground()

    def rebuild_frames(self):
        if rebuild_rigged(self):
            return
        image = self.source_image
        ratio = min(200 / image.get_width(), 180 / image.get_height()) * self.size_scale
        w, h = max(1, round(image.get_width()*ratio)), max(1, round(image.get_height()*ratio))
        base = pygame.transform.smoothscale(image, (w,h))
        self.width, self.height = w+12, h+12
        self.frames_left = []
        for index in range(32):
            phase = index*math.tau/32
            frame = pygame.Surface((self.width,self.height),pygame.SRCALPHA)
            for y in range(h):
                leg = max(0, (y/max(1,h-1)-.55)/.45)
                offset = round(5*leg*math.sin(phase+y/max(1,h)*5))
                frame.blit(base,(6+offset,6+y),(0,y,w,1))
            self.frames_left.append(frame)
        self.frames_right = [pygame.transform.flip(frame,True,False) for frame in self.frames_left]

    def update(self, dt=1/60):
        dt=max(0,min(dt,.05))
        if self.behavior.update(self, dt, VIEW.world_width):
            return
        if self.social_target is not None:
            self.follow_partner(dt)
            return
        self.on_ground()
        if self.rest>0:
            self.rest=max(0,self.rest-dt)
            return
        self.phase=(self.phase+dt*gait_rate(self, 1.7))%1
        self.x+=self.direction*self.walk_speed*dt
        left,right=self.width/2+20,VIEW.world_width-self.width/2-20
        if self.x<=left: self.x,self.direction=left,1
        if self.x>=right: self.x,self.direction=right,-1
        self.walk_time-=dt
        if self.walk_time<=0:
            self.rest=random.uniform(1,3)
            self.walk_time=random.uniform(4,9)
            if random.random()<.5: self.direction*=-1

    def follow_partner(self, dt):
        tx, ground = self.social_target
        tx = max(self.width/2+20, min(VIEW.world_width-self.width/2-20, tx))
        dx = tx-self.x
        # Garder le regard vers le partenaire, meme en reculant.
        if self.social_face is not None:
            self.direction = self.social_face
        elif abs(dx)>1:
            self.direction = 1 if dx>0 else -1
        if abs(dx)>1:
            self.x += math.copysign(min(abs(dx),self.walk_speed*1.3*dt), dx)
        self.ground_y += (ground-self.ground_y)*min(1,dt*3)
        self.phase = (self.phase+dt*gait_rate(self, 1.7, self.walk_speed * 1.3 if abs(dx) > 1 else 0))%1
        self.on_ground()

    def draw(self, screen):
        frame=(self.frames_right if self.direction>0 else self.frames_left)[int(self.phase*32)%32]
        frame = rig_frame(self, frame)
        hop=self.social_jump + (abs(math.sin(self.phase*math.tau))*12 if self.kind=='lapin' and self.rest<=0 and self.social_target is None else 0)
        pygame.draw.ellipse(screen,(66,120,63),(self.x-self.width*.35,self.ground_y-5,self.width*.7,10))
        self.behavior.draw(screen, frame, (self.x, self.ground_y-hop + getattr(self, 'rig_padding', (0, 0))[1]), bottom=True)


class Cat(LandAnimal):
    kind, label, walk_speed = 'chat', 'Chat', 45


class Dog(LandAnimal):
    kind, label, walk_speed = 'chien', 'Chien', 65


class Rabbit(LandAnimal):
    kind, label, walk_speed = 'lapin', 'Lapin', 55


class Cow(LandAnimal):
    kind, label, walk_speed = 'vache', 'Vache', 28


class Pig(LandAnimal):
    kind, label, walk_speed = 'cochon', 'Cochon', 38


class Sheep(LandAnimal):
    kind, label, walk_speed = 'mouton', 'Mouton', 35


class Hen(LandAnimal):
    kind, label, walk_speed = 'poule', 'Poule', 48


class Horse(LandAnimal):
    kind, label, walk_speed = 'cheval', 'Cheval', 85


class Lion(LandAnimal):
    kind, label, walk_speed = 'lion', 'Lion', 52


class Elephant(LandAnimal):
    kind, label, walk_speed = 'elephant', 'Elephant', 24


class Giraffe(LandAnimal):
    kind, label, walk_speed = 'girafe', 'Girafe', 36


class Zebra(LandAnimal):
    kind, label, walk_speed = 'zebre', 'Zebre', 72


class Rhino(LandAnimal):
    kind, label, walk_speed = 'rhinoceros', 'Rhinoceros', 32


class Bird(LandAnimal):
    def __init__(self, image, rig=None):
        super().__init__(image, rig=rig)
        self.ground_y = random.uniform(220, 410)
        self.on_ground()

    def rebuild_frames(self):
        if rebuild_rigged(self):
            return
        image = self.source_image
        ratio = min(145 / image.get_width(), 105 / image.get_height()) * self.size_scale
        w, h = max(1, round(image.get_width()*ratio)), max(1, round(image.get_height()*ratio))
        base = pygame.transform.smoothscale(image, (w,h))
        self.width, self.height = w+12, h+12
        self.frames_left = []
        for index in range(32):
            phase = index*math.tau/32
            frame = pygame.Surface((self.width,self.height),pygame.SRCALPHA)
            # Le corps central reste stable ; les ailes se replient aux extremites.
            for x in range(w):
                weight = max(0, 1-abs(x/max(1,w-1)-.55)/.4)
                column_height = max(1, round(h*(1-.32*weight*(.5+.5*math.sin(phase)))))
                column = pygame.transform.smoothscale(base.subsurface((x,0,1,h)),(1,column_height))
                frame.blit(column,(x+6,(self.height-column_height)//2))
            self.frames_left.append(frame)
        self.frames_right = [pygame.transform.flip(frame,True,False) for frame in self.frames_left]

    def update(self, dt=1/60):
        dt=max(0,min(dt,.05))
        if self.behavior.update(self, dt, VIEW.world_width):
            return
        if self.social_target is not None:
            self.follow_partner(dt)
            return
        self.phase=(self.phase+dt*gait_rate(self, 2.4))%1
        self.x+=self.direction*self.walk_speed*dt
        left,right=self.width/2+20,VIEW.world_width-self.width/2-20
        if self.x<=left: self.x,self.direction=left,1
        elif self.x>=right: self.x,self.direction=right,-1
        self.ground_y=max(200,min(440,self.ground_y+math.sin(self.phase*math.tau)*16*dt))
        self.on_ground()

    def draw(self, screen):
        frame=(self.frames_right if self.direction>0 else self.frames_left)[int(self.phase*32)%32]
        frame = rig_frame(self, frame)
        self.behavior.draw(screen, frame, (self.x, self.ground_y-self.social_jump + getattr(self, 'rig_padding', (0, 0))[1]), bottom=True)


class Parrot(Bird):
    kind, label, walk_speed = 'perroquet', 'Perroquet', 75


class Pigeon(Bird):
    kind, label, walk_speed = 'pigeon', 'Pigeon', 90


class Sparrow(Bird):
    kind, label, walk_speed = 'moineau', 'Moineau', 110


class Eagle(Bird):
    kind, label, walk_speed = 'aigle', 'Aigle', 65


ANIMAL_TYPES = {cls.kind: cls for cls in (
    Cat, Dog, Rabbit, Cow, Pig, Sheep, Hen, Horse,
    Lion, Elephant, Giraffe, Zebra, Rhino, Parrot, Pigeon, Sparrow, Eagle,
)}


class Interactions:
    def __init__(self):
        self.pairs = []

    def start(self, a, b, kind=None):
        a,b=sorted((a,b),key=lambda animal:animal.x)
        self.pairs.append(dict(a=a,b=b,kind=kind or random.choice(('jeu','bisou','sauts')),
                               time=0.,contact=0.,x=(a.x+b.x)/2,ground=(a.ground_y+b.ground_y)/2))

    def update(self, animals, dt):
        dt=max(0,min(dt,.05))
        busy={animal for pair in self.pairs for animal in (pair['a'],pair['b'])}
        for animal in animals:
            animal.social_cooldown=max(0,animal.social_cooldown-dt)
        for i,a in enumerate(animals):
            if a in busy or a.social_cooldown>0: continue
            for b in animals[i+1:]:
                if b in busy or b.social_cooldown>0: continue
                if isinstance(a,Bird)!=isinstance(b,Bird): continue
                distance=math.hypot(a.x-b.x,a.ground_y-b.ground_y)
                if distance < (a.width+b.width)/2+140 and abs(a.ground_y-b.ground_y)<90 and random.random()<1-math.exp(-dt):
                    self.start(a,b); busy.update((a,b)); break
        for pair in self.pairs[:]:
            a,b=pair['a'],pair['b']; pair['time']+=dt
            t=pair['time']; gap=(a.width+b.width)/2
            margin=gap+25
            cx=max(margin,min(VIEW.world_width-margin,pair['x']))
            if pair['kind']=='jeu': cx+=math.sin(t*1.2)*min(60,max(0,VIEW.world_width/2-margin))
            a.social_target=(cx-a.width/2,pair['ground'])
            b.social_target=(cx+b.width/2,pair['ground'])
            a.social_face,b.social_face=1,-1
            close=all(abs(animal.x-animal.social_target[0])<5 and abs(animal.ground_y-pair['ground'])<4 for animal in (a,b))
            if close:
                pair['contact']+=dt
            if pair['kind'] in ('sauts','jeu'):
                for animal,offset in ((a,0),(b,0 if pair['kind']=='sauts' else math.pi)):
                    animal.social_jump=max(0,math.sin(t*5+offset))*min(32,animal.height*.25)
            if t>12 or (pair['kind']=='bisou' and pair['contact']>1.5) or (pair['kind']!='bisou' and t>7):
                for animal in (a,b):
                    animal.social_target=None; animal.social_face=None; animal.social_jump=0
                    animal.social_cooldown=random.uniform(5,9)
                self.pairs.remove(pair)

    def draw(self,screen,font):
        for pair in self.pairs:
            a,b=pair['a'],pair['b']
            x=round((a.x+b.x)/2); y=round(min(a.ground_y-a.height,b.ground_y-b.height)-40)
            label={'jeu':'On joue !','bisou':'Bisou','sauts':'On saute !'}[pair['kind']]
            text=font.render(label,True,(60,55,45)); screen.blit(text,text.get_rect(midbottom=(x,y)))
            if pair['kind']=='bisou' and pair['contact']>0:
                y-=25+round(pair['contact']*15)
                pygame.draw.circle(screen,(240,85,125),(x-5,y),7)
                pygame.draw.circle(screen,(240,85,125),(x+5,y),7)
                pygame.draw.polygon(screen,(240,85,125),[(x-11,y+2),(x+11,y+2),(x,y+15)])


def draw_prairie(screen, time):
    width = screen.get_width()
    screen.fill((153, 211, 239))
    pygame.draw.circle(screen, (255, 231, 139), (1040, 125), 48)
    for x in range(160, width, 340):
        for dx, dy, r in ((0, 0, 30), (32, -12, 40), (70, 0, 30)):
            pygame.draw.circle(screen, (245, 248, 246), (x + dx, 150 + dy), r)
    # Les collines se chevauchent sans ?tre d?coup?es en portions de fen?tre.
    for i, x in enumerate(range(-200, width, 700)):
        color = (137, 185, 109) if i % 2 == 0 else (121, 176, 99)
        pygame.draw.ellipse(screen, color, (x, 300 + (i % 2) * 20, 1000, 380))
    pygame.draw.rect(screen, (104, 164, 84), (0, 480, width, 220))
    for x in range(110, width - 80, 1000):
        pygame.draw.rect(screen, (126, 87, 57), (x - 12, 330, 24, 190))
        pygame.draw.circle(screen, (59, 131, 75), (x, 310), 80)
        pygame.draw.circle(screen, (79, 150, 78), (x - 35, 285), 55)
    for i, x in enumerate(range(30, width, 35)):
        y = 535 + (i * 37) % 150
        pygame.draw.line(screen, (65, 125, 60), (x, y), (x + 2, y - 8), 2)
        pygame.draw.circle(screen, (255, 222, 135), (x + 2, y - 9), 3)


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
                raise OSError('Impossible de sauvegarder un animal')
            name = f'fish_{index}.png'
            archive.writestr(name, encoded.tobytes())
            records.append(dict(image=name, x=fish.x, y=fish.y, direction=fish.direction, size=fish.size_scale, kind=fish.kind, rig=fish.rig, ground=fish.ground_y))
        archive.writestr('prairie.json', json.dumps(dict(version=1, fishes=records, view=VIEW.settings())))
    temporary.replace(path)


def load_aquarium(path=SAVE_PATH):
    path = Path(path)
    if not path.exists():
        return []
    fishes = []
    with zipfile.ZipFile(path) as archive:
        data = json.loads(archive.read('prairie.json'))
        if data['version'] != 1:
            raise ValueError('Version de sauvegarde inconnue')
        VIEW.restore(data.get('view', {}))
        for index, record in enumerate(data['fishes']):
            report_progress(f"Animal {index + 1}/{len(data['fishes'])} : {record.get('kind', 'poisson')}")
            encoded = np.frombuffer(archive.read(record['image']), np.uint8)
            pixels = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
            if pixels is None or pixels.ndim != 3 or pixels.shape[2] != 4:
                raise ValueError('Image d animal invalide')
            animal_class = ANIMAL_TYPES[record['kind']]
            fish = animal_class(cv_to_pygame(pixels), rig=record.get('rig'))
            fish.set_size(record.get("size", 1.0))
            fish.x = max(fish.width / 2 + 20, min(VIEW.world_width - fish.width / 2 - 20, float(record['x'])))
            fish.y = max(fish.height / 2 + 30, min(SCREEN_HEIGHT - 100 - fish.height / 2, float(record['y'])))
            fish.target_y = fish.y
            fish.direction = -1 if record['direction'] < 0 else 1
            low, high = (200, 440) if isinstance(fish, Bird) else (540, 670)
            fish.ground_y = max(low, min(high, float(record.get('ground', (low+high)/2))))
            fish.on_ground()
            fishes.append(fish)
    return fishes


class AquariumManager:
    def __init__(self):
        self.open = False
        self.scroll = 0
        self.dragging = None
        self.button = pygame.Rect(SCREEN_WIDTH - 205, 38, 190, 32)
        self.panel = pygame.Rect(170, 90, 860, 550)
        self.close = pygame.Rect(900, 106, 110, 32)
        self.rows = pygame.Rect(190, 168, 820, 440)

    def row_controls(self, index):
        y = self.rows.y + index * 110 - self.scroll
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
            self.scroll = max(0, min(max(0, len(fishes) * 110 - self.rows.height), self.scroll - event.y * 55))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rows.collidepoint(event.pos):
            for index, fish in enumerate(fishes):
                slider, duplicate, delete = self.row_controls(index)
                if duplicate.collidepoint(event.pos):
                    clone = type(fish)(fish.source_image, rig=fish.rig)
                    clone.x, clone.y = fish.x + 35, fish.y + 30
                    clone.direction = fish.direction
                    clone.ground_y = min(440 if isinstance(fish, Bird) else 670, fish.ground_y + 15)
                    clone.set_size(fish.size_scale)
                    fishes.append(clone)
                    changed = True
                    break
                if delete.collidepoint(event.pos):
                    fishes.remove(fish)
                    changed = True
                    break
                if slider.inflate(12, 16).collidepoint(event.pos):
                    self.dragging = fish
                    break
        if self.dragging is not None and event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            if self.dragging in fishes:
                slider = self.row_controls(fishes.index(self.dragging))[0]
                value = round(0.05 + 1.95 * max(0, min(1, (event.pos[0] - slider.x) / slider.width)), 2)
                if value != self.dragging.size_scale:
                    self.dragging.set_size(value)
                    changed = True
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.dragging = None
        if changed:
            # Liberer aussi le partenaire d'un poisson supprime ou redimensionne.
            for pair in interactions.pairs:
                for fish in (pair['a'], pair['b']):
                    fish.social_target = None
                    fish.social_jump = 0
                    fish.social_face = None
                    fish.social_cooldown = 3
            interactions.pairs.clear()
            self.scroll = min(self.scroll, max(0, len(fishes) * 110 - self.rows.height))
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
            if y + 110 <= self.rows.top or y >= self.rows.bottom:
                continue
            pygame.draw.rect(screen, (32, 70, 88), (195, y + 3, 810, 102), border_radius=6)
            image = fish.source_image
            ratio = min(120 / image.get_width(), 82 / image.get_height())
            thumb = pygame.transform.smoothscale(image, (max(1, round(image.get_width() * ratio)), max(1, round(image.get_height() * ratio))))
            screen.blit(thumb, thumb.get_rect(center=(275, y + 54)))
            name = fish.label
            screen.blit(font.render(f'{name} {index + 1}', True, 'white'), (360, y + 24))
            screen.blit(font.render(f'Taille : {fish.size_scale:.0%}', True, 'white'), (520, y + 20))
            pygame.draw.line(screen, (110, 160, 180), (slider.left, slider.centery), (slider.right, slider.centery), 5)
            pygame.draw.circle(screen, (255, 220, 100), (round(slider.x + (fish.size_scale - 0.05) / 1.95 * slider.width), slider.centery), 9)
            button(duplicate, 'Dupliquer')
            button(delete, 'Supprimer', (160, 65, 65))
        screen.set_clip(previous_clip)
        screen.blit(font.render('Molette : defiler | Ctrl+S : sauvegarder les modifications', True, (215, 230, 240)), (192, 616))


def main():
    pygame.init()
    fullscreen = False
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED)
    fullscreen_button = pygame.Rect(15, 650, 180, 34)
    pygame.display.set_caption('Prairie des animaux')
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
    interactions = Interactions()
    manager = AquariumManager()
    add_button = pygame.Rect(SCREEN_WIDTH - 410, 38, 195, 32)
    choices = [(cls.label, cls, pygame.Rect(250+(i%3)*240,200+(i//3)*60,220,48))
               for i,cls in enumerate(ANIMAL_TYPES.values())]
    choosing = False
    clock = pygame.time.Clock()
    running = True
    dirty = False
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            toggle_fullscreen = event.type == pygame.KEYDOWN and event.key == pygame.K_F11
            controls_visible = not choosing and not manager.open and not VIEW.open
            if controls_visible and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                toggle_fullscreen = toggle_fullscreen or fullscreen_button.collidepoint(event.pos)
            if toggle_fullscreen:
                fullscreen = not fullscreen
                screen = pygame.display.set_mode(
                    (SCREEN_WIDTH, SCREEN_HEIGHT),
                    pygame.SCALED | (pygame.FULLSCREEN if fullscreen else 0),
                )
                continue
            if not manager.open and not choosing:
                consumed, changed = VIEW.handle(event, fishes, interactions)
                dirty = dirty or changed
                if consumed:
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
                    animal.on_ground()
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
                        status = 'Prairie sauvegardee'
                    except (OSError, ValueError, cv2.error) as error:
                        status = 'Echec de sauvegarde : ' + str(error)
                    status_until = pygame.time.get_ticks() + 6000
        VIEW.update(dt, manager.open or choosing or VIEW.open)
        world = VIEW.background(draw_prairie, pygame.time.get_ticks())
        if manager.open or choosing or VIEW.open:
            dt = 0
        interactions.update(fishes, dt)
        for fish in sorted(fishes, key=lambda animal: animal.ground_y):
            fish.update(dt)
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
            pygame.draw.rect(screen, (20, 48, 65), (230, 135, 740, 520), border_radius=12)
            screen.blit(font.render('Quel animal veux-tu scanner ?', True, 'white'), (410, 160))
            for label, cls, rect in choices:
                pygame.draw.rect(screen, (35, 110, 145), rect, border_radius=8)
                text = font.render(label, True, 'white')
                screen.blit(text, text.get_rect(center=rect.center))
            screen.blit(font.render('Dessin de profil : tete a gauche, pattes en bas.', True, 'white'), (375, 570))
            screen.blit(font.render('Oiseaux : bec a gauche, ailes visibles.', True, 'white'), (405, 595))
            screen.blit(font.render('Echap ou clic a cote : annuler', True, 'white'), (440, 625))
        pygame.display.flip()
    pygame.quit()


# ==========================================================
# DEMARRAGE
# ==========================================================

if __name__ == "__main__":
    main()
