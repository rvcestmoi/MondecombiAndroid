import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import numpy as np
import pygame

from aquarium import animation_cache as cache, animaux_terrestres as land
from aquarium.animal_rig import Skin, default_rig
from aquarium.loading import loading_screen, report_progress
from aquarium.monde_combine import CombinedView, load_initial_world
from aquarium.test_animal_rig import drawing


class AnimationCacheTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((1200, 700))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        override = patch.object(cache, 'CACHE_DIR', self.folder / 'cache')
        override.start()
        self.addCleanup(override.stop)
        cache._BANKS.clear()

    def tearDown(self):
        cache._BANKS.clear()
        pygame.quit()

    def test_real_duplicate_and_disk_reload_do_not_recalculate_skin(self):
        start = time.perf_counter()
        animal = land.Cat(drawing('chat'), rig=default_rig('chat'))
        cold = time.perf_counter() - start
        animal.set_size(.65)
        animals = [animal]
        manager = land.AquariumManager()
        manager.open = True
        click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                   pos=manager.row_controls(0)[1].center)
        path = self.folder / 'prairie.zip'
        land.save_aquarium(animals, path)
        with patch.object(Skin, 'frames', side_effect=AssertionError('Unexpected recalculation')):
            start = time.perf_counter()
            manager.handle(click, animals, SimpleNamespace(pairs=[]))
            duplicate = time.perf_counter() - start
            self.assertEqual(len(animals), 2)
            self.assertIs(animal._rig_cache[1], animals[1]._rig_cache[1])
            self.assertIsNot(animal.rig, animals[1].rig)
            cache._BANKS.clear()  # Simulate a fresh process: only disk cache remains.
            start = time.perf_counter()
            loaded = land.load_aquarium(path)[0]
            reload = time.perf_counter() - start
        self.assertEqual(loaded.rig, animal.rig)
        self.assertEqual(loaded.size_scale, animal.size_scale)
        for before, after in zip(animal.frames_left, loaded.frames_left):
            self.assertEqual(pygame.image.tostring(before, 'RGBA'), pygame.image.tostring(after, 'RGBA'))
        print(f'\nMeasured: first build {cold:.3f}s; duplicate {duplicate:.3f}s; disk reload {reload:.3f}s')

    def test_cache_invalidation_corruption_and_unwritable_directory(self):
        image = pygame.Surface((10, 10), pygame.SRCALPHA)
        image.fill((80, 160, 230, 255))
        bank = ([image] * 32, image, np.array([1, 1]))
        build = Mock(return_value=bank)
        rig = default_rig('chat')
        cache.animation_bank(image, rig, build)
        cache.animation_bank(image.copy(), rig, build)
        self.assertEqual(build.call_count, 1)
        rig['joints']['Tête'][0] += .02
        cache.animation_bank(image, rig, build)
        self.assertEqual(build.call_count, 2)
        image.set_at((0, 0), (250, 0, 0, 255))
        cache.animation_bank(image, rig, build)
        self.assertEqual(build.call_count, 3)
        with patch.object(cache, 'RENDER_VERSION', cache.RENDER_VERSION + 1):
            cache.animation_bank(image, rig, build)
        self.assertEqual(build.call_count, 4)
        for path in cache.CACHE_DIR.glob('*.npz'):
            path.write_bytes(b'invalid cache')
        cache._BANKS.clear()
        cache.animation_bank(image, rig, build)
        self.assertEqual(build.call_count, 5)
        cache._BANKS.clear()
        with patch.object(cache, 'load_bank', side_effect=OSError), \
             patch.object(cache, 'save_bank', side_effect=PermissionError):
            self.assertIs(cache.animation_bank(image, rig, build), bank)

    def test_cache_memory_and_disk_limits(self):
        image = pygame.Surface((10, 10), pygame.SRCALPHA)
        bank = ([image] * 32, image, np.array([1, 1]))
        with patch.object(cache, 'MEMORY_LIMIT', cache.bank_bytes(bank)), \
             patch.object(cache, 'DISK_LIMIT', 1):
            for kind in ('chat', 'chien'):
                cache.animation_bank(image, default_rig(kind), lambda: bank)
            self.assertEqual(len(cache._BANKS), 1)
            self.assertEqual(list(cache.CACHE_DIR.glob('*.npz')), [])

    def test_startup_uses_active_world_without_loading_legacy_populations(self):
        module = SimpleNamespace(load_aquarium=Mock(return_value=[]), SAVE_PATH=self.folder / 'old.zip')
        habitat = SimpleNamespace(module=module, path=self.folder / 'legacy.zip', name='mer', animals=[])
        library = SimpleNamespace(resume=Mock(return_value=True), name='Actif')
        self.assertEqual(load_initial_world(CombinedView(), [habitat], library), 'Monde repris : Actif')
        module.load_aquarium.assert_not_called()
        library.resume.return_value = False
        with patch('aquarium.monde_combine.SETTINGS_PATH', self.folder / 'settings.json'):
            load_initial_world(CombinedView(), [habitat], library)
        module.load_aquarium.assert_called_once()
        module.load_aquarium.reset_mock()
        library.resume.side_effect = ValueError('bad archive')
        with self.assertRaises(ValueError):
            load_initial_world(CombinedView(), [habitat], library)
        module.load_aquarium.assert_not_called()

    def test_loading_screen_is_shown_before_work(self):
        with patch('pygame.display.flip') as flip:
            with loading_screen('Chargement du monde'):
                flip.assert_called_once()
                report_progress('Animal 1/2 : chat', .5)
                self.assertEqual(flip.call_count, 2)
            report_progress('Invisible', 1)
            self.assertEqual(flip.call_count, 2)


if __name__ == '__main__':
    unittest.main()
