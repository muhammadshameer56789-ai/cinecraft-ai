"""Temporary storage using generated ids only. No client-supplied names or paths touch the disk."""
import os
import re
import shutil
import time
import uuid

from app import config

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _dir():
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return config.STORAGE_DIR


def new_id() -> str:
    return uuid.uuid4().hex


def valid_id(image_id: str) -> bool:
    return bool(_ID_RE.match(image_id or ""))


def save_original(image_id: str, data: bytes, ext: str) -> None:
    folder = _dir() / image_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"original.{ext}").write_bytes(data)


def find_original(image_id: str):
    if not valid_id(image_id):
        return None
    folder = _dir() / image_id
    if not folder.is_dir():
        return None
    for p in folder.glob("original.*"):
        try:
            os.utime(folder)  # refresh retention clock while the image is in use
        except OSError:
            pass
        return p
    return None


def delete(image_id: str) -> bool:
    if not valid_id(image_id):
        return False
    folder = _dir() / image_id
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
        return True
    return False


def cleanup_expired() -> int:
    cutoff = time.time() - config.RETENTION_MINUTES * 60
    removed = 0
    for folder in _dir().iterdir():
        if folder.is_dir() and valid_id(folder.name) and folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed


def save_json(image_id: str, name: str, obj) -> None:
    import json
    if valid_id(image_id) and (_dir() / image_id).is_dir():
        (_dir() / image_id / f"{name}.json").write_text(json.dumps(obj))


def load_json(image_id: str, name: str):
    import json
    if not valid_id(image_id):
        return None
    f = _dir() / image_id / f"{name}.json"
    return json.loads(f.read_text()) if f.is_file() else None


def safe_stem(filename) -> str:
    """Sanitised display name used only for export filenames; never used as a path."""
    import os
    import re
    stem = os.path.splitext(os.path.basename(str(filename or "photo")))[0]
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-_")[:40]
    return stem or "photo"


def owner_ok(image_id: str, owner: str) -> bool:
    """An image is only visible to the browser session that uploaded it."""
    meta = load_json(image_id, "meta") or {}
    return bool(owner) and meta.get("owner") == owner


def register_copy(data: bytes, ext: str, stem: str, owner: str) -> str:
    image_id = new_id()
    save_original(image_id, data, ext)
    save_json(image_id, "meta", {"stem": stem, "owner": owner})
    return image_id
