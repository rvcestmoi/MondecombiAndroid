import copy
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import numpy as np
import pygame

from aquarium import aquarium as sea, animaux_terrestres as land
from aquarium import animation_cache
from aquarium.animal_rig import (KINDS, Skin, default_rig, edit_rig, gait_rate,
                                 pose, rig_frame, template, validate_rig)
from aquarium.monde_combine import CombinedView
from aquarium.world_library import WorldLibrary


def drawing(kind, size=(180, 150)):
    """Colored body and limbs make deformation and alpha errors visible."""
    image = pygame.Surface(size, pygame.SRCALPHA)
    nodes = template(kind)
    points = [tuple(round(p * size[j]) for j, p in enumerate(n[2])) for n in nodes]
    for i, (_, parent, _, role, _) in enumerate(nodes):
        if parent >= 0:
            color = {'body': (230, 145, 70), 'leg': (80, 190, 110),
                     'wing': (80, 140, 230), 'tail': (210, 90, 170)}[role]
            pygame.draw.line(image, color, points[parent], points[i], 18 if role == 'body' else 9)
            pygame.draw.circle(image, color, points[i], 9 if role == 'body' else 4)
    return image


class RigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1200, 700))
        cls.cache_directory = tempfile.TemporaryDirectory()
        cls.cache_patch = patch.object(animation_cache, 'CACHE_DIR', Path(cls.cache_directory.name))
        cls.cache_patch.start()
        animation_cache._BANKS.clear()

    @classmethod
    def tearDownClass(cls):
        animation_cache._BANKS.clear()
        cls.cache_patch.stop()
        cls.cache_directory.cleanup()
        pygame.quit()

    def test_all_species_have_valid_periodic_length_preserving_skeletons(self):
        self.assertEqual(KINDS, set(land.ANIMAL_TYPES) | {'poisson', 'meduse', 'crabe', 'etoile', 'tortue'})
        for kind in sorted(KINDS):
            with self.subTest(kind=kind):
                rig = validate_rig(default_rig(kind), kind)
                for phase in (0, .2, .5, .8):
                    rest, animated = pose(rig, (200, 170), phase)
                    self.assertTrue(np.isfinite(animated).all())
                    for i, (_, parent, _, _, _) in enumerate(template(kind)):
                        if parent >= 0:
                            self.assertAlmostEqual(np.linalg.norm(rest[i] - rest[parent]),
                                                   np.linalg.norm(animated[i] - animated[parent]), places=4)
                np.testing.assert_allclose(pose(rig, (200, 170), 0)[1], pose(rig, (200, 170), 1)[1], atol=1e-6)

    def test_skin_preserves_rest_texture_and_joint_edits_change_animation(self):
        image = drawing('chat', (90, 75))
        rig = default_rig('chat')
        skin = Skin(image, rig)
        neutral = skin.render(skin.vertices, np.array([2, 2]))
        original = pygame.surfarray.array3d(image)
        np.testing.assert_array_equal(original, pygame.surfarray.array3d(neutral)[2:-2, 2:-2])
        np.testing.assert_array_equal(pygame.surfarray.array_alpha(image), pygame.surfarray.array_alpha(neutral)[2:-2, 2:-2])
        rig['joints']['Patte 1 2'] = [.18, .68]
        edited = Skin(image, rig)
        self.assertGreater(np.max(np.abs(edited.vertices_at(.7) - skin.vertices_at(.7))), 1)
        frames, _, padding = edited.frames(8)
        self.assertGreater(len({pygame.image.tostring(f, 'RGBA') for f in frames}), 1)
        self.assertGreater(padding.min(), 0)
        self.assertEqual(pygame.surfarray.array_alpha(frames[0])[0, 0], 0)

    def test_rejects_invalid_or_collapsed_joints(self):
        for value in ([float('nan'), .3], [2, .4], ['a', .1], [.5]):
            rig = default_rig('chat')
            rig['joints']['Tête'] = value
            with self.assertRaises(ValueError):
                validate_rig(rig, 'chat')
        rig = default_rig('chat')
        rig['joints']['Tête'] = rig['joints']['Cou']
        with self.assertRaises(ValueError):
            validate_rig(rig, 'chat')
        with self.assertRaises(ValueError):
            validate_rig(default_rig('chat'), 'chien')

    def test_every_animal_builds_draws_and_keeps_rig_when_resized(self):
        classes = list(land.ANIMAL_TYPES.values()) + [sea.Fish, sea.Jellyfish, sea.Crab, sea.Starfish, sea.Turtle]
        screen = pygame.display.get_surface()
        for cls in classes:
            with self.subTest(kind=cls.kind):
                animal = cls(drawing(cls.kind), rig=default_rig(cls.kind))
                original = copy.deepcopy(animal.rig)
                cache = animal._rig_cache
                for scale in (.05, .7, 2):
                    animal.set_size(scale)
                    self.assertIs(animal._rig_cache, cache)
                    self.assertEqual(animal.rig, original)
                    for direction in (-1, 1):
                        animal.direction = direction
                        animal.update(.02)
                        animal.draw(screen)
                frames = animal.jelly_frames if cls is sea.Jellyfish else animal.frames_left
                self.assertNotEqual(pygame.image.tostring(frames[0], 'RGBA'), pygame.image.tostring(frames[8], 'RGBA'))
                if cls.kind == 'chat':
                    animal.rest = 1
                    self.assertIs(rig_frame(animal, frames[0]), animal.rig_neutral[1])
                    rate = gait_rate(animal, 1.7)
                    animal.set_size(1)
                    self.assertGreater(gait_rate(animal, 1.7), rate)

    def test_save_reload_and_clone_preserve_custom_rig_and_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            for module, cls in ((sea, sea.Turtle), (land, land.Cat)):
                with self.subTest(kind=cls.kind):
                    rig = default_rig(cls.kind)
                    rig['joints']['Tête'] = [.12, .17]
                    animal = cls(drawing(cls.kind), rig=rig)
                    animal.set_size(.65)
                    clone = type(animal)(animal.source_image, rig=animal.rig)
                    clone.rig['joints']['Tête'][0] = .2
                    self.assertEqual(animal.rig, rig)
                    legacy = cls(drawing(cls.kind))
                    path = Path(directory) / (cls.kind + '.zip')
                    module.save_aquarium([animal, legacy], path)
                    loaded = module.load_aquarium(path)
                    self.assertEqual(loaded[0].rig, rig)
                    self.assertEqual(loaded[0].size_scale, .65)
                    self.assertIsNone(loaded[1].rig)
                    # Archives from before this feature contain no rig key.
                    with zipfile.ZipFile(path) as archive:
                        files = {name: archive.read(name) for name in archive.namelist()}
                    metadata = 'aquarium.json' if module is sea else 'prairie.json'
                    data = json.loads(files[metadata])
                    for record in data['fishes']:
                        record.pop('rig')
                    files[metadata] = json.dumps(data).encode()
                    with zipfile.ZipFile(path, 'w') as archive:
                        for name, content in files.items():
                            archive.writestr(name, content)
                    self.assertTrue(all(a.rig is None for a in module.load_aquarium(path)))

    def test_combined_world_restart_restores_rig(self):
        with tempfile.TemporaryDirectory() as directory:
            habitats = [SimpleNamespace(name='prairie', module=land,
                         animals=[land.Cat(drawing('chat'), rig=default_rig('chat'))],
                         interactions=SimpleNamespace(pairs=[]),
                         manager=SimpleNamespace(scroll=0, dragging=None))]
            library = WorldLibrary(directory)
            library.save(CombinedView(), habitats, pygame.Surface((300, 175)))
            habitats[0].animals = []
            WorldLibrary(directory).resume(CombinedView(), habitats)
            self.assertEqual(habitats[0].animals[0].rig, default_rig('chat'))
            self.assertEqual(len(list(Path(directory).glob('*.zip'))), 1)

    def test_editor_drag_validate_and_cancel(self):
        image = drawing('chat', (180, 150))
        initial = default_rig('chat')
        # The editor fits this image to a 612 x 510 rectangle at (159, 110).
        head = (round(159 + .13 * 612), round(110 + .25 * 510))
        destination = (head[0] + 40, head[1] + 20)
        events = [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=head),
                  pygame.event.Event(pygame.MOUSEMOTION, pos=destination),
                  pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=destination),
                  pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)]
        with patch('pygame.event.get', return_value=events):
            result = edit_rig(image, 'chat', initial)
        self.assertNotEqual(result['joints']['Tête'], initial['joints']['Tête'])
        self.assertEqual(initial, default_rig('chat'))
        with patch('pygame.event.get', return_value=[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]):
            self.assertIsNone(edit_rig(image, 'chat', initial))

    def test_scan_checkbox_optional_for_both_habitats(self):
        key = lambda k: pygame.event.Event(pygame.KEYDOWN, key=k)
        click = lambda pos: pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
        for module, kind in ((sea, 'poisson'), (land, 'chat')):
            for checked in (False, True):
                with self.subTest(module=module.__name__, checked=checked):
                    camera = SimpleNamespace(isOpened=lambda: True,
                        read=lambda: (True, np.full((480, 640, 3), 255, np.uint8)), release=lambda: None)
                    crop_events = ([click((900, 60))] if checked else []) + [click((400, 250)),
                        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(600, 450)), key(pygame.K_RETURN)]
                    batches = [[key(pygame.K_SPACE)], crop_events, [key(pygame.K_RETURN)]]
                    pixels = np.full((80, 100, 4), 255, np.uint8)
                    with patch.object(module.cv2, 'VideoCapture', return_value=camera), \
                         patch.object(module, 'extract_fish', return_value=pixels), \
                         patch.object(module, 'edit_rig', return_value=default_rig(kind)) as editor, \
                         patch('pygame.event.get', side_effect=batches):
                        scanned, rig = module.scan_fish(kind)
                    self.assertIs(scanned, pixels)
                    self.assertEqual(rig, default_rig(kind) if checked else None)
                    self.assertEqual(editor.call_count, int(checked))

    def test_skeleton_click_opens_editor_without_an_extra_enter(self):
        key = lambda k: pygame.event.Event(pygame.KEYDOWN, key=k)
        click = lambda pos: pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
        for module, kind in ((sea, 'poisson'), (land, 'chat')):
            for stage in ('crop', 'preview', 'cancel_retry', 'cancel_without_rig'):
                with self.subTest(module=module.__name__, stage=stage):
                    camera = SimpleNamespace(isOpened=lambda: True,
                        read=lambda: (True, np.full((480, 640, 3), 255, np.uint8)), release=lambda: None)
                    crop = [click((400, 250)),
                            pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(600, 450))]
                    if stage != 'crop':
                        crop.append(key(pygame.K_RETURN))
                    batches = [[key(pygame.K_SPACE)], crop, [click((900, 60))]]
                    results = [default_rig(kind)]
                    if stage.startswith('cancel'):
                        results.insert(0, None)
                        batches.append([click((900, 60)) if stage == 'cancel_retry' else key(pygame.K_RETURN)])
                    pixels = np.full((80, 100, 4), 255, np.uint8)
                    with patch.object(module.cv2, 'VideoCapture', return_value=camera), \
                         patch.object(module, 'extract_fish', return_value=pixels), \
                         patch.object(module, 'edit_rig', side_effect=results) as editor, \
                         patch('pygame.event.get', side_effect=batches):
                        scanned, rig = module.scan_fish(kind)
                    self.assertIs(scanned, pixels)
                    self.assertEqual(rig, None if stage == 'cancel_without_rig' else default_rig(kind))
                    self.assertEqual(editor.call_count, 2 if stage == 'cancel_retry' else 1)


if __name__ == '__main__':
    unittest.main()
