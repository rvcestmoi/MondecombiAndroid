"""Editable 2D skeletons and cached, textured skeletal animation.

Joint coordinates are normalized in the original scan. The skeleton drives a
triangle mesh with automatic bone weights; the drawing remains the texture.
No camera, display or file is opened at import time.
"""
import copy
import json
import math

import cv2
import numpy as np
import pygame

try:
    from .animation_cache import animation_bank
    from .loading import report_progress
except ImportError:
    from animation_cache import animation_bank
    from loading import report_progress


BIRDS = {'perroquet', 'pigeon', 'moineau', 'aigle'}
QUADRUPEDS = {'chat', 'chien', 'lapin', 'vache', 'cochon', 'mouton',
              'cheval', 'lion', 'elephant', 'girafe', 'zebre', 'rhinoceros'}
KINDS = QUADRUPEDS | BIRDS | {'poule', 'poisson', 'meduse', 'crabe', 'etoile', 'tortue'}
STRENGTH = {'elephant': .55, 'rhinoceros': .6, 'vache': .65,
            'girafe': .7, 'cheval': 1.15, 'zebre': 1.1, 'lapin': 1.2,
            'aigle': .65, 'moineau': 1.15}
COLORS = {'body': (255, 210, 90), 'leg': (90, 225, 160),
          'wing': (105, 185, 255), 'tail': (230, 145, 250)}


def template(kind):
    """Return ordered joints: name, parent index, point, role, cycle offset."""
    if kind not in KINDS:
        raise ValueError('Type d’animal sans squelette : ' + str(kind))
    nodes = []

    def add(name, parent, point, role='body', phase=0):
        parent_index = next((i for i, n in enumerate(nodes) if n[0] == parent), -1)
        nodes.append((name, parent_index, point, role, phase))

    def chain(name, parent, points, role, phase=0):
        for i, point in enumerate(points):
            joint = f'{name} {i + 1}'
            add(joint, parent, point, role, phase)
            parent = joint

    if kind in {'meduse', 'etoile', 'crabe'}:
        add('Centre', None, (.5, .4 if kind != 'etoile' else .5))
        if kind == 'etoile':
            for i in range(5):
                angle = -math.pi / 2 + i * math.tau / 5
                points = [(.5 + r * math.cos(angle), .5 + r * math.sin(angle)) for r in (.22, .44)]
                chain(f'Bras {i + 1}', 'Centre', points, 'tail', i * .2)
        elif kind == 'meduse':
            add('Cloche gauche', 'Centre', (.18, .32), 'wing')
            add('Cloche droite', 'Centre', (.82, .32), 'wing', .5)
            for i in range(5):
                x = .22 + i * .14
                chain(f'Tentacule {i + 1}', 'Centre', [(x, .55), (x, .73), (x, .94)], 'tail', i * .13)
        else:
            for side in range(2):
                for i in range(4):
                    x = .38 if side == 0 else .62
                    end = .07 if side == 0 else .93
                    chain(f'Patte {side * 4 + i + 1}', 'Centre',
                          [(x, .43 + i * .065), ((x + end) / 2, .52 + i * .075),
                           (end, .62 + i * .085)], 'leg', (i + side) % 2 * .5)
                chain(f'Pince {side + 1}', 'Centre',
                      [(.25 if side == 0 else .75, .26), (.12 if side == 0 else .88, .10)], 'wing', side * .5)
        return nodes

    add('Bassin', None, (.66, .43))
    add('Dos', 'Bassin', (.48, .40))
    add('Poitrine', 'Dos', (.32, .42))
    neck = (.27, .22) if kind == 'girafe' else (.25, .32)
    head = (.22, .07) if kind == 'girafe' else (.13, .25)
    add('Cou', 'Poitrine', neck)
    add('Tête', 'Cou', head)
    chain('Queue', 'Bassin', [(.82, .43), (.96, .35)], 'tail')
    if kind == 'poisson':
        chain('Nageoire dorsale', 'Dos', [(.52, .24), (.65, .10)], 'wing')
        chain('Nageoire ventrale', 'Poitrine', [(.39, .65), (.52, .78)], 'wing', .5)
    elif kind in BIRDS:
        chain('Aile proche', 'Poitrine', [(.47, .29), (.68, .11), (.91, .08)], 'wing')
        chain('Aile éloignée', 'Dos', [(.52, .54), (.72, .70), (.9, .78)], 'wing', .5)
        chain('Patte repliée', 'Bassin', [(.59, .65), (.74, .69)], 'tail', .5)
    else:
        count = 2 if kind == 'poule' else 4
        for i in range(count):
            front = i < 2 and count == 4
            x = (.29 if front else .69) + (i % 2) * .075
            phase = (0 if i in (0, 3) else .5)
            if kind == 'lapin':
                phase = .45 if front else 0
            if count == 2:
                phase = i * .5
                x = .49 + i * .14
            points = [(x, .51), (x + .03, .72), (x - .04, .94)]
            role = 'leg'
            if kind == 'tortue':
                points = [(x, .46), (x + .04, .64), (x + .15, .80)]
                role = 'wing'
            chain(f'Patte {i + 1}', 'Poitrine' if front else 'Bassin', points, role, phase)
        if kind == 'elephant':
            chain('Trompe', 'Tête', [(.07, .48), (.10, .73)], 'tail', .3)
        if kind == 'poule':
            chain('Aile', 'Dos', [(.54, .53), (.72, .56)], 'wing')
    return nodes


def default_rig(kind):
    return dict(version=1, kind=kind, head_left=True,
                joints={n[0]: list(n[2]) for n in template(kind)})


def validate_rig(data, kind):
    if data is None:
        return None
    if not isinstance(data, dict) or data.get('version') != 1 or data.get('kind') != kind:
        raise ValueError('Squelette incompatible avec cet animal')
    expected = default_rig(kind)
    joints = data.get('joints')
    if not isinstance(joints, dict) or joints.keys() != expected['joints'].keys():
        raise ValueError('Articulations du squelette invalides')
    if not isinstance(data.get('head_left'), bool):
        raise ValueError('Orientation du squelette invalide')
    for name, point in joints.items():
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError('Position d’articulation invalide')
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in point):
            raise ValueError('Les articulations doivent rester dans le dessin')
    nodes = template(kind)
    for name, parent, _, _, _ in nodes:
        if parent >= 0:
            other = nodes[parent][0]
            if math.dist(joints[name], joints[other]) < .005:
                raise ValueError('Écarte les articulations : ' + name)
    return copy.deepcopy(data)


def rotate(vector, angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([c * vector[0] - s * vector[1], s * vector[0] + c * vector[1]])


def pose(rig, size, phase):
    """Forward kinematics, with two-bone IK for feet and fixed bone lengths."""
    nodes = template(rig['kind'])
    rest = np.array([rig['joints'][n[0]] for n in nodes], dtype=np.float64) * size
    result = rest.copy()
    angles = np.zeros(len(nodes))
    kind = rig['kind']
    strength = STRENGTH.get(kind, 1)
    for i, (name, parent, _, role, offset) in enumerate(nodes):
        if parent < 0:
            continue
        wave = math.sin(math.tau * (phase + offset))
        angle = 0
        if role == 'tail':
            angle = .13 * wave
            if kind == 'poisson':
                angle = .25 * math.sin(math.tau * phase - i * .55)
            elif kind == 'etoile':
                angle = .09 * wave
        elif role == 'wing':
            angle = (.48 if kind in BIRDS else .20) * wave * strength
        angles[i] = angles[parent] + angle
        result[i] = result[parent] + rotate(rest[i] - rest[parent], angles[i])

    for i, (name, parent, _, role, offset) in enumerate(nodes):
        if role != 'leg' or not name.endswith(' 3'):
            continue
        knee, hip = parent, nodes[parent][1]
        upper = np.linalg.norm(rest[knee] - rest[hip])
        lower = np.linalg.norm(rest[i] - rest[knee])
        cycle = (phase + offset) % 1
        stride = (upper + lower) * .19 * strength
        # A long stance and a short lifted return keep feet near the ground.
        if cycle < .6:
            dx, lift = stride * (2 * cycle / .6 - 1), 0
        else:
            swing = (cycle - .6) / .4
            dx, lift = stride * (1 - 2 * swing), stride * .8 * math.sin(math.pi * swing)
        target = rest[i] + result[hip] - rest[hip] + [dx if rig['head_left'] else -dx, -lift]
        delta = target - result[hip]
        distance = np.linalg.norm(delta)
        distance_clamped = max(abs(upper - lower) + 1e-5, min(upper + lower - 1e-5, distance))
        axis = delta / max(distance, 1e-8)
        along = (upper ** 2 - lower ** 2 + distance_clamped ** 2) / (2 * distance_clamped)
        bend = math.sqrt(max(0, upper ** 2 - along ** 2))
        original = rest[i] - rest[hip]
        bend_sign = np.sign(original[0] * (rest[knee] - rest[hip])[1] - original[1] * (rest[knee] - rest[hip])[0]) or 1
        result[knee] = result[hip] + axis * along + np.array([-axis[1], axis[0]]) * bend * bend_sign
        result[i] = result[hip] + axis * distance_clamped
    return rest, result


class Skin:
    """A small regular triangle mesh, skinned to the nearest bones."""
    def __init__(self, image, rig):
        self.rig = validate_rig(rig, rig['kind'])
        self.size = np.array(image.get_size())
        self.nodes = template(rig['kind'])
        self.bones = [(n[1], i) for i, n in enumerate(self.nodes) if n[1] >= 0]
        self.rest, _ = pose(rig, self.size, 0)
        w, h = self.size
        self.rgba = np.frombuffer(pygame.image.tostring(image, 'RGBA'), np.uint8).reshape(h, w, 4)
        # Premultiplied alpha avoids dark/white fringes at moving outlines.
        self.texture = self.rgba.astype(np.float32) / 255
        self.texture[:, :, :3] *= self.texture[:, :, 3:4]
        self.alpha = np.ascontiguousarray(self.texture[:, :, 3])
        gx = np.linspace(0, w - 1, max(3, min(45, int(w / 6) + 2)))
        gy = np.linspace(0, h - 1, max(3, min(45, int(h / 6) + 2)))
        xx, yy = np.meshgrid(gx, gy)
        self.vertices = np.stack((xx.ravel(), yy.ravel()), axis=1)
        self.triangles = []
        for y in range(len(gy) - 1):
            for x in range(len(gx) - 1):
                a = y * len(gx) + x
                b, c, d = a + 1, a + len(gx), a + len(gx) + 1
                self.triangles.extend([(a, b, d), (a, d, c)])
        visible = []
        for indices in self.triangles:
            triangle = self.vertices[list(indices)]
            left, top = np.maximum(0, np.floor(triangle.min(axis=0)).astype(int) - 1)
            right, bottom = np.minimum(self.size, np.ceil(triangle.max(axis=0)).astype(int) + 2)
            if self.rgba[top:bottom, left:right, 3].any():
                visible.append(indices)
        self.triangles = visible
        distances = []
        for parent, child in self.bones:
            a, b = self.rest[parent], self.rest[child]
            vector = b - a
            t = np.clip((self.vertices - a) @ vector / max(vector @ vector, 1e-8), 0, 1)
            distances.append(np.linalg.norm(self.vertices - (a + t[:, None] * vector), axis=1))
        distances = np.array(distances).T
        weights = 1 / (distances + 1) ** 6
        # Restrict blending to the three nearest bones.
        nearest = np.argsort(distances, axis=1)[:, :3]
        mask = np.zeros_like(weights)
        np.put_along_axis(mask, nearest, 1, axis=1)
        weights *= mask
        self.weights = weights / weights.sum(axis=1, keepdims=True)

    def vertices_at(self, phase):
        _, posed = pose(self.rig, self.size, phase)
        vertices = np.zeros_like(self.vertices)
        for b, (parent, child) in enumerate(self.bones):
            old = self.rest[child] - self.rest[parent]
            new = posed[child] - posed[parent]
            angle = math.atan2(new[1], new[0]) - math.atan2(old[1], old[0])
            c, s = math.cos(angle), math.sin(angle)
            rotation = np.array([[c, -s], [s, c]])
            transformed = (self.vertices - self.rest[parent]) @ rotation.T + posed[parent]
            vertices += transformed * self.weights[:, b:b + 1]
        return vertices

    def render(self, vertices, padding):
        w, h = (self.size + padding * 2).astype(int)
        map_x = np.full((h, w), -1, np.float32)
        map_y = np.full((h, w), -1, np.float32)
        coverage = np.zeros((h, w), np.float32)
        target = vertices + padding
        for indices in self.triangles:
            dst = target[list(indices)].astype(np.float32)
            src = self.vertices[list(indices)].astype(np.float32)
            x0, y0 = np.maximum(0, np.floor(dst.min(axis=0)).astype(int))
            x1, y1 = np.minimum([w - 1, h - 1], np.ceil(dst.max(axis=0)).astype(int))
            if x1 < x0 or y1 < y0:
                continue
            a, b = dst[1] - dst[0], dst[2] - dst[0]
            det = a[0] * b[1] - a[1] * b[0]
            if abs(det) < 1e-5:
                continue
            yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            dx, dy = xx - dst[0, 0], yy - dst[0, 1]
            u = (dx * b[1] - dy * b[0]) / det
            v = (a[0] * dy - a[1] * dx) / det
            inside = (u >= -1e-4) & (v >= -1e-4) & (u + v <= 1.0001)
            source = src[0] + u[:, :, None] * (src[1] - src[0]) + v[:, :, None] * (src[2] - src[0])
            alpha = cv2.remap(self.alpha, source[:, :, 0].astype(np.float32),
                              source[:, :, 1].astype(np.float32), cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT)
            # A folded triangle's transparent background must never erase a
            # visible limb. Keep the most covered sample at overlaps.
            occupied = coverage[y0:y1 + 1, x0:x1 + 1]
            inside &= (alpha > 0) & (alpha >= occupied)
            occupied[inside] = alpha[inside]
            map_x[y0:y1 + 1, x0:x1 + 1][inside] = source[:, :, 0][inside]
            map_y[y0:y1 + 1, x0:x1 + 1][inside] = source[:, :, 1][inside]
        rgba = cv2.remap(self.texture, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        np.divide(rgba[:, :, :3], rgba[:, :, 3:4], out=rgba[:, :, :3], where=rgba[:, :, 3:4] > 1e-6)
        pixels = np.rint(np.clip(rgba * 255, 0, 255)).astype(np.uint8)
        pixels[pixels[:, :, 3] == 0] = 0
        return pygame.image.frombuffer(pixels.tobytes(), (w, h), 'RGBA').copy()

    def frames(self, count=32):
        poses = [self.vertices_at(i / count) for i in range(count)]
        bounds = np.concatenate(poses + [self.vertices])
        extra = np.maximum(-bounds.min(axis=0), bounds.max(axis=0) - self.size)
        padding = np.ceil(np.maximum(2, extra + 2)).astype(int)
        frames = []
        for index, p in enumerate(poses):
            if pygame.display.get_init():
                pygame.event.pump()
            frames.append(self.render(p, padding))
            report_progress(fraction=(index + 1) / count)
        return frames, self.render(self.vertices, padding), padding


def rebuild_rigged(animal):
    """Called before each species' legacy frame builder; False preserves it."""
    if getattr(animal, 'rig', None) is None:
        return False
    kind = animal.kind
    limits = ((145, 105) if kind in BIRDS else (200, 180) if kind in QUADRUPEDS | {'poule'}
              else {'poisson': (180, 240), 'meduse': (150, 200), 'crabe': (160, 110),
                    'etoile': (130, 130), 'tortue': (190, 150)}[kind])
    image = animal.source_image
    ratio = min(limits[0] / image.get_width(), limits[1] / image.get_height())
    base_size = tuple(max(2, round(v * ratio)) for v in image.get_size())
    key = (id(image), json.dumps(animal.rig, sort_keys=True))
    cached = getattr(animal, '_rig_cache', None)
    if cached is None or cached[0] != key:
        base = pygame.transform.smoothscale(image, base_size)
        bank = animation_bank(base, animal.rig, lambda: Skin(base, animal.rig).frames())
        animal._rig_cache = (key, bank)
    frames, neutral, padding = animal._rig_cache[1]
    size = tuple(max(2, round(v * animal.size_scale)) for v in base_size)
    scaled_padding = np.maximum(1, np.round(padding * animal.size_scale)).astype(int)
    frame_size = tuple(map(int, np.array(size) + 2 * scaled_padding))
    if frame_size != frames[0].get_size():
        frames = [pygame.transform.smoothscale(f, frame_size) for f in frames]
        neutral = pygame.transform.smoothscale(neutral, frame_size)
    padding = scaled_padding
    if not animal.rig['head_left'] and kind not in {'meduse', 'crabe', 'etoile'}:
        frames = [pygame.transform.flip(f, True, False) for f in frames]
        neutral = pygame.transform.flip(neutral, True, False)
    animal.frames_left = frames
    animal.frames_right = [pygame.transform.flip(f, True, False) for f in frames]
    animal.jelly_frames = animal.star_frames = frames
    animal.crab_frames = [frames[i * 32 // 24] for i in range(24)]
    animal.rig_neutral = [neutral, pygame.transform.flip(neutral, True, False)]
    animal.rig_padding = tuple(map(int, padding))
    animal.width, animal.height = size
    return True


def rig_frame(animal, legacy):
    if getattr(animal, 'rig', None) is None:
        return legacy
    active = animal.behavior.active
    mode = active[1] if active else None
    resting = ((getattr(animal, 'rest', 0) > 0 or getattr(animal, 'pause_time', 0) > 0)
               and active is None and animal.social_target is None)
    if resting or mode in {'glide', 'rest', 'graze', 'sniff', 'peck', 'chew'}:
        flipped = animal.direction > 0 and animal.kind not in {'meduse', 'crabe', 'etoile'}
        return animal.rig_neutral[int(flipped)]
    return legacy


def gait_rate(animal, legacy, speed=None):
    """Match stance travel to world movement, including resized drawings."""
    if getattr(animal, 'rig', None) is None:
        return legacy
    if animal.kind in BIRDS:
        return {'aigle': 1.15, 'perroquet': 2.3, 'pigeon': 2.8, 'moineau': 3.8}[animal.kind]
    nodes = template(animal.kind)
    points = np.array([animal.rig['joints'][n[0]] for n in nodes]) * [animal.width, animal.height]
    lengths = []
    for i, (name, parent, _, role, _) in enumerate(nodes):
        if role == 'leg' and name.endswith(' 3'):
            hip = nodes[parent][1]
            lengths.append(np.linalg.norm(points[i] - points[parent]) + np.linalg.norm(points[parent] - points[hip]))
    if not lengths:
        return legacy
    stride = float(np.mean(lengths)) * .19 * STRENGTH.get(animal.kind, 1)
    speed = abs(speed if speed is not None else getattr(animal, 'walk_speed', 42))
    return min(6, speed * .6 / max(1, 2 * stride))


def edit_rig(image, kind, initial=None):
    """Modal editor. None returns to scan preview without adding an animal."""
    screen = pygame.display.get_surface()
    font = pygame.font.Font(None, 25)
    small = pygame.font.Font(None, 21)
    clock = pygame.time.Clock()
    rig = validate_rig(initial, kind) if initial is not None else default_rig(kind)
    nodes = template(kind)
    width, height = screen.get_size()
    area = pygame.Rect(25, 110, width - 320, height - 190)
    scale = min(area.width / image.get_width(), area.height / image.get_height())
    shown = pygame.transform.smoothscale(image, tuple(max(1, round(v * scale)) for v in image.get_size()))
    rect = shown.get_rect(center=area.center)
    panel_x = width - 275
    buttons = {name: pygame.Rect(panel_x, y, 250, 38) for name, y in
               [('Aperçu animé', 130), ('Inverser le squelette', 180), ('Réinitialiser', 230),
                ('Valider', height - 120), ('Retour au cadrage', height - 70)]}
    selected, dragging, playing = None, False, False
    cached, message, elapsed = None, '', 0.0

    def point(name):
        x, y = rig['joints'][name]
        return (round(rect.x + x * rect.width), round(rect.y + y * rect.height))

    def preview():
        nonlocal cached, message
        try:
            validate_rig(rig, kind)
            if cached is None:
                screen.blit(font.render('Calcul de l’animation…', True, 'white'), (panel_x, 290))
                pygame.display.flip()
                ratio = min(200 / image.get_width(), 180 / image.get_height())
                source = pygame.transform.smoothscale(image, tuple(max(2, round(v * ratio)) for v in image.get_size()))
                cached = Skin(source, rig).frames(24)[0]
            message = ''
            return True
        except ValueError as error:
            message = str(error)
            return False

    while True:
        elapsed += clock.tick(30) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(event)
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None
            action = None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                action = 'Valider'
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                action = 'Aperçu animé'
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                action = next((name for name, box in buttons.items() if box.collidepoint(event.pos)), None)
                if action is None and not playing and rect.collidepoint(event.pos):
                    closest = min(rig['joints'], key=lambda name: math.dist(point(name), event.pos))
                    if math.dist(point(closest), event.pos) <= 18:
                        selected, dragging = closest, True
            if event.type == pygame.MOUSEMOTION and dragging and selected:
                rig['joints'][selected] = [max(0, min(1, (event.pos[0] - rect.x) / rect.width)),
                                           max(0, min(1, (event.pos[1] - rect.y) / rect.height))]
                cached = None
            if event.type == pygame.MOUSEBUTTONUP:
                dragging = False
            if action == 'Retour au cadrage':
                return None
            if action == 'Valider':
                try:
                    return validate_rig(rig, kind)
                except ValueError as error:
                    message = str(error)
            elif action == 'Aperçu animé':
                playing = False if playing else preview()
            elif action == 'Inverser le squelette':
                for p in rig['joints'].values():
                    p[0] = 1 - p[0]
                rig['head_left'] = not rig['head_left']
                cached, playing = None, False
            elif action == 'Réinitialiser':
                rig, cached, playing, selected = default_rig(kind), None, False, None
        screen.fill((20, 48, 65))
        screen.blit(font.render('Squelette : ' + kind, True, 'white'), (25, 22))
        screen.blit(font.render('Déplace les points sur les articulations du dessin. Espace : aperçu / édition.', True, 'white'), (25, 55))
        pygame.draw.rect(screen, (48, 76, 90), area, border_radius=8)
        if playing and cached:
            frame = cached[int(elapsed * (1.2 if kind == 'etoile' else 2) * len(cached)) % len(cached)]
            ratio = min(area.width / frame.get_width(), area.height / frame.get_height()) * .85
            frame = pygame.transform.smoothscale(frame, tuple(max(1, round(v * ratio)) for v in frame.get_size()))
            screen.blit(frame, frame.get_rect(center=area.center))
        else:
            screen.blit(shown, rect)
            for name, parent, _, role, _ in nodes:
                color = COLORS[role]
                if parent >= 0:
                    pygame.draw.line(screen, (15, 25, 35), point(nodes[parent][0]), point(name), 6)
                    pygame.draw.line(screen, color, point(nodes[parent][0]), point(name), 3)
                pygame.draw.circle(screen, (15, 25, 35), point(name), 8)
                pygame.draw.circle(screen, 'white' if name == selected else color, point(name), 5)
            if selected:
                screen.blit(font.render(selected, True, 'white'), (panel_x, 290))
        for name, box in buttons.items():
            pygame.draw.rect(screen, (45, 135, 100) if name == 'Valider' else (40, 105, 145), box, border_radius=6)
            label = 'Modifier les points' if name == 'Aperçu animé' and playing else name
            text = font.render(label, True, 'white')
            screen.blit(text, text.get_rect(center=box.center))
        for i, (label, color) in enumerate([('Dos, cou, tête', COLORS['body']), ('Pattes : base, genou, pied', COLORS['leg']),
                                           ('Ailes / nageoires', COLORS['wing']), ('Queue / bras / tentacules', COLORS['tail'])]):
            screen.blit(small.render(label, True, color), (panel_x, 335 + i * 26))
        screen.blit(small.render('Squelette prévu pour un dessin de profil.', True, 'white'), (25, height - 55))
        screen.blit(small.render(message, True, (255, 200, 125)), (25, height - 30))
        pygame.display.flip()
