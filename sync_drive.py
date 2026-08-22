from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

IMAGES_DIR = Path("images")
MANIFEST = Path("images.json")
KNOWN_IDS = Path("known_drive_ids.txt")
DRIVE_FOLDER_URL = os.environ.get(
    "DRIVE_FOLDER_URL",
    "https://drive.google.com/drive/folders/1gIXVgKN1j50Tf-6Z_eSA8gYI2JwylmnR",
)
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


def drive_id(url: str) -> str | None:
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("id")
    if query_id:
        return query_id[0]
    match = re.search(r"/d/([^/]+)", parsed.path)
    if match:
        return match.group(1)
    return None


def list_drive_images() -> list[dict[str, str]]:
    # gdown 6.1+ can inspect a public folder as JSON without downloading it.
    cmd = ["gdown", DRIVE_FOLDER_URL, "--folder", "--json", "--quiet"]
    result = subprocess.run(cmd, check=True, text=True, capture_output=True)
    entries = json.loads(result.stdout)

    images: list[dict[str, str]] = []
    for entry in entries:
        url = str(entry.get("url", ""))
        path = str(entry.get("path", ""))
        file_id = drive_id(url)
        extension = Path(path).suffix.lower()
        if file_id and extension in IMAGE_EXTENSIONS:
            images.append({"id": file_id, "url": url, "path": path, "ext": extension})

    images.sort(key=lambda x: x["path"].lower())
    return images


def download_file(url: str, destination: Path) -> None:
    subprocess.run(
        ["gdown", url, "-O", str(destination), "--quiet"],
        check=True,
        text=True,
    )


def rebuild_manifest() -> int:
    hosted = [
        p for p in IMAGES_DIR.iterdir()
        if p.is_file() and NAME_RE.match(p.name)
    ]
    hosted.sort(key=image_number)
    manifest = [
        {"index": image_number(path), "alias": path.name, "path": f"images/{path.name}"}
        for path in hosted
    ]
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(hosted)


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    known_ids = set()
    if KNOWN_IDS.exists():
        known_ids = {line.strip() for line in KNOWN_IDS.read_text(encoding="utf-8").splitlines() if line.strip()}

    existing = [p for p in IMAGES_DIR.iterdir() if p.is_file() and NAME_RE.match(p.name)]
    max_number = max((image_number(p) for p in existing), default=0)
    known_hashes = {sha256(p) for p in existing}

    drive_images = list_drive_images()
    new_entries = [entry for entry in drive_images if entry["id"] not in known_ids]
    print(f"Drive images listed: {len(drive_images)}")
    print(f"New Drive IDs found: {len(new_entries)}")

    added = 0
    duplicates = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for entry in new_entries:
            temp_file = tmpdir / f"download{entry['ext']}"
            download_file(entry["url"], temp_file)
            digest = sha256(temp_file)

            if digest in known_hashes:
                duplicates += 1
                known_ids.add(entry["id"])
                print(f"SKIP duplicate content: {entry['path']}")
                continue

            max_number += 1
            destination = IMAGES_DIR / f"img-{max_number:03d}{entry['ext']}"
            temp_file.replace(destination)
            known_hashes.add(digest)
            known_ids.add(entry["id"])
            added += 1
            print(f"ADD {entry['path']} -> {destination.name}")

    KNOWN_IDS.write_text("\n".join(sorted(known_ids)) + "\n", encoding="utf-8")
    total = rebuild_manifest()
    print(f"New images added: {added}")
    print(f"Duplicate-content IDs recorded: {duplicates}")
    print(f"Total hosted images: {total}")


if __name__ == "__main__":
    main()
