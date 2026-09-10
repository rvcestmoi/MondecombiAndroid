"""Visible progress while loading; inactive during normal gameplay."""
from contextlib import contextmanager
import time

import pygame


_title = None
_label = ''
_last_draw = 0


def report_progress(label=None, fraction=0):
    global _label, _last_draw
    if _title is None:
        return
    if pygame.event.get(pygame.QUIT):
        pygame.quit()
        raise SystemExit
    now = time.monotonic()
    changed = label is not None and label != _label
    if label is not None:
        _label = label
    if not changed and now - _last_draw < .05:
        return
    _last_draw = now
    screen = pygame.display.get_surface()
    screen.fill((20, 48, 65))
    font = pygame.font.Font(None, 32)
    cx, cy = screen.get_rect().center
    for text, y in ((_title, cy - 75), (_label, cy - 25)):
        rendered = font.render(text, True, 'white')
        screen.blit(rendered, rendered.get_rect(center=(cx, y)))
    bar = pygame.Rect(cx - 220, cy + 20, 440, 16)
    pygame.draw.rect(screen, (40, 80, 100), bar, border_radius=6)
    fill = bar.copy()
    fill.width = max(1, round(bar.width * max(0, min(1, fraction))))
    pygame.draw.rect(screen, (90, 210, 155), fill, border_radius=6)
    pygame.display.flip()


@contextmanager
def loading_screen(title):
    global _title, _label, _last_draw
    previous = (_title, _label, _last_draw)
    _title, _label, _last_draw = title, '', 0
    try:
        report_progress('Préparation…')
        yield
    finally:
        _title, _label, _last_draw = previous
