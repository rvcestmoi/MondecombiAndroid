import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from aquarium.world_library import WorldLibrary


class View:
    def __init__(self):
        self.x, self.y = 0, 350
        self.options = {}

    def settings(self):
        return self.options

    def restore(self, settings):
        self.options = settings.copy()

    def clamp_camera(self):
        pass


class WorldLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_repeated_restarts_keep_one_archive_and_restore_state(self):
        with tempfile.TemporaryDirectory() as directory:
            view = View()
            view.options = {'screens': 3}
            view.x = 42
            preview = pygame.Surface((300, 175))
            library = WorldLibrary(directory)
            self.assertFalse(library.resume(view, []))
            library.name = 'Mon monde'
            library.save(view, [], preview)
            original = library.current
            for _ in range(4):
                library, view = WorldLibrary(directory), View()
                self.assertTrue(library.resume(view, []))
                self.assertEqual(library.current, original)
                self.assertEqual(library.name, 'Mon monde')
                self.assertEqual(view.options, {'screens': 3})
                self.assertEqual(view.x, 42)
                library.save(view, [], preview)
            self.assertEqual(len(list(Path(directory).glob('*.zip'))), 1)

    def test_migration_and_selection_of_an_older_world(self):
        with tempfile.TemporaryDirectory() as directory:
            view, preview = View(), pygame.Surface((300, 175))
            library = WorldLibrary(directory)
            library.save(view, [], preview)
            first = library.current
            library.current = None
            library.save(view, [], preview)
            second = library.current
            os.utime(first, (100, 100))
            os.utime(second, (200, 200))
            (Path(directory) / 'current.txt').unlink()
            library = WorldLibrary(directory)
            library.resume(view, [])
            self.assertEqual(library.current, second)
            library.load(first, view, [])
            restarted = WorldLibrary(directory)
            restarted.resume(view, [])
            self.assertEqual(restarted.current, first)
            self.assertEqual(len(list(Path(directory).glob('*.zip'))), 2)


if __name__ == '__main__':
    unittest.main()
