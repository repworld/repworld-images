from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

IMAGES_DIR = Path("images")
INCOMING_DIR = Path("incoming")
MANIFEST = Path("images.json")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".bmp"}
NAME_RE = re.compile(r"^img-(\d+)(\.[^.]+)$", re.IGNORECASE)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def image_number(path: Path) -> int:
    match = NAME_RE.match(path.name)
    return int(match.group(1)) if match else 10**9


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    existing = [
        p for p in IMAGES_DIR.iterdir()
        if p.is_file() and NAME_RE.match(p.name)
    ]
    existing.sort(key=image_number)

    known_hashes: dict[str, Path] = {}
    max_number = 0
    for path in existing:
        max_number = max(max_number, image_number(path))
        known_hashes[sha256(path)] = path

    incoming = sorted(
        (
            p for p in INCOMING_DIR.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ),
        key=lambda p: (p.name.lower(), str(p).lower()),
    )

    added = 0
    skipped = 0
    for source in incoming:
        digest = sha256(source)
        if digest in known_hashes:
            skipped += 1
            continue

        max_number += 1
        extension = source.suffix.lower()
        destination = IMAGES_DIR / f"img-{max_number:03d}{extension}"
        shutil.copy2(source, destination)
        known_hashes[digest] = destination
        added += 1
        print(f"ADD {source.name} -> {destination.name}")

    hosted = [
        p for p in IMAGES_DIR.iterdir()
        if p.is_file() and NAME_RE.match(p.name)
    ]
    hosted.sort(key=image_number)

    manifest = [
        {
            "index": image_number(path),
            "alias": path.name,
            "path": f"images/{path.name}",
        }
        for path in hosted
    ]

    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Drive images scanned: {len(incoming)}")
    print(f"New images added: {added}")
    print(f"Already hosted / skipped: {skipped}")
    print(f"Total hosted images: {len(hosted)}")


if __name__ == "__main__":
    main()
