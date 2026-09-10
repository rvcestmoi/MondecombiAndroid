"""Disposable animation banks, shared by identical drawings and skeletons."""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np
import pygame


CACHE_DIR = Path(__file__).resolve().parent / '.animation_cache'
# Increment whenever the skinning algorithm or animation templates change.
RENDER_VERSION = 1
MEMORY_LIMIT = 64 * 1024 * 1024
DISK_LIMIT = 128 * 1024 * 1024
_BANKS = OrderedDict()


def bank_bytes(bank):
    frames, neutral, _ = bank
    return sum(f.get_pitch() * f.get_height() for f in (*frames, neutral))


def remember(key, bank):
    _BANKS[key] = bank
    _BANKS.move_to_end(key)
    while _BANKS and sum(bank_bytes(b) for b in _BANKS.values()) > MEMORY_LIMIT:
        _BANKS.popitem(last=False)


def load_bank(path):
    with np.load(path, allow_pickle=False) as data:
        rgba, padding = data['rgba'], data['padding']
        if (rgba.dtype != np.uint8 or rgba.ndim != 4 or rgba.shape[0] != 33 or
                rgba.shape[3] != 4 or not all(1 <= v <= 1024 for v in rgba.shape[1:3]) or
                padding.shape != (2,) or not np.issubdtype(padding.dtype, np.integer) or
                np.any(padding < 0) or np.any(padding * 2 >= rgba.shape[1:3][::-1])):
            raise ValueError('Cache d’animation invalide')
        size = (rgba.shape[2], rgba.shape[1])
        frames = [pygame.image.frombuffer(pixels.tobytes(), size, 'RGBA').copy() for pixels in rgba]
        return frames[:-1], frames[-1], padding.copy()


def save_bank(path, bank):
    frames, neutral, padding = bank
    width, height = neutral.get_size()
    rgba = np.stack([np.frombuffer(pygame.image.tostring(f, 'RGBA'), np.uint8)
                     .reshape(height, width, 4) for f in (*frames, neutral)])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            np.savez_compressed(file, rgba=rgba, padding=padding)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    # Only evict generated banks from our dedicated cache directory.
    paths = sorted(path.parent.glob('*.npz'), key=lambda p: p.stat().st_mtime, reverse=True)
    used = 0
    for candidate in paths:
        if len(candidate.stem) != 64 or any(c not in '0123456789abcdef' for c in candidate.stem):
            continue
        used += candidate.stat().st_size
        if used > DISK_LIMIT:
            candidate.unlink(missing_ok=True)


def animation_bank(image, rig, build):
    metadata = json.dumps([RENDER_VERSION, image.get_size(), rig], sort_keys=True).encode()
    digest = hashlib.sha256(metadata)
    digest.update(pygame.image.tostring(image, 'RGBA'))
    key = digest.hexdigest()
    if key in _BANKS:
        _BANKS.move_to_end(key)
        return _BANKS[key]
    path = CACHE_DIR / (key + '.npz')
    try:
        bank = load_bank(path)
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        bank = build()
        try:
            save_bank(path, bank)
        except OSError:
            # A read-only/full cache must not prevent an animal from loading.
            pass
    remember(key, bank)
    return bank
