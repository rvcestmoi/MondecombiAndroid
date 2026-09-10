"""Copy desktop worlds into Android assets; original archives are never modified.

Usage from any directory: python android/tools/sync_worlds.py
Only intended for development builds containing the author's example drawings.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile


def main():
    android = Path(__file__).resolve().parents[1]
    source = android.parent / "mondes"
    destination = android / "app/src/main/assets/worlds"
    destination.mkdir(parents=True, exist_ok=True)
    current = (source / "current.txt").read_text(encoding="utf-8").strip()
    entries = []
    for path in sorted(source.glob("*.zip")):
        with zipfile.ZipFile(path) as archive:
            meta = json.loads(archive.read("world.json"))
            if meta["version"] != 1:
                raise ValueError(f"Unknown world version in {path.name}")
            count = 0
            for habitat, manifest in (("mer", "aquarium"), ("prairie", "prairie")):
                with zipfile.ZipFile(io.BytesIO(archive.read(habitat + ".zip"))) as population:
                    count += len(json.loads(population.read(manifest + ".json"))["fishes"])
        shutil.copyfile(path, destination / path.name)
        entries.append(dict(file=path.name, name=meta["name"], animals=count,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    if current not in {entry["file"] for entry in entries}:
        raise ValueError("The current world is missing from the library")
    (destination / "index.json").write_text(
        json.dumps(dict(default=current, worlds=entries), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"{len(entries)} worlds copied; default: {current}")
    print(f"{sum(e['animals'] for e in entries)} animals across the library")


if __name__ == "__main__":
    main()
