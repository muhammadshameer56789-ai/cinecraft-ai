"""Projects are stored server-side and tied to an anonymous browser session (no accounts).
Every query is scoped by owner, so one session can never read another's projects."""
import json
import re
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from app import config
from app.services.manual import clean
from app.services.presets import AUTO_ID, PRESETS


class ProjectError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


def clean_name(name) -> str:
    n = re.sub(r"[\x00-\x1f\x7f]", "", str(name or "")).strip()[:80]
    if not n:
        raise ProjectError("Give the project a name.")
    return n


def clean_settings(preset, intensity, adjustments) -> tuple[str, float, dict]:
    if preset != AUTO_ID and preset not in PRESETS:
        raise ProjectError("Unknown style.", 422)
    try:
        i = float(intensity)
    except (TypeError, ValueError):
        raise ProjectError("Intensity must be a number.", 422)
    if not 0 <= i <= 100:
        raise ProjectError("Intensity must be between 0 and 100.", 422)
    return preset, i, clean(adjustments)


class ProjectStore:
    def __init__(self, db_path: Path | None = None, root: Path | None = None):
        self.db_path = Path(db_path or config.DB_PATH)
        self.root = Path(root or config.PROJECT_DIR)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.execute("""CREATE TABLE IF NOT EXISTS projects(
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, stem TEXT NOT NULL, ext TEXT NOT NULL,
                preset TEXT NOT NULL, intensity REAL NOT NULL, adjustments TEXT NOT NULL,
                width INTEGER, height INTEGER, created REAL NOT NULL, updated REAL NOT NULL)""")
            self._db.execute("CREATE INDEX IF NOT EXISTS ix_owner ON projects(owner)")

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["adjustments"] = json.loads(d["adjustments"])
        d.pop("owner", None)
        d["expires"] = d["updated"] + config.PROJECT_RETENTION_DAYS * 86400
        return d

    def create(self, owner, name, data: bytes, ext, stem, preset, intensity, adjustments, width, height) -> dict:
        name = clean_name(name)
        preset, intensity, adj = clean_settings(preset, intensity, adjustments)
        with self._lock:
            n = self._db.execute("SELECT COUNT(*) FROM projects WHERE owner=?", (owner,)).fetchone()[0]
            if n >= config.MAX_PROJECTS_PER_SESSION:
                raise ProjectError(f"You can keep up to {config.MAX_PROJECTS_PER_SESSION} projects. Delete one first.", 409)
            pid, now = uuid.uuid4().hex, time.time()
            folder = self.root / pid
            folder.mkdir(parents=True)
            (folder / f"original.{ext}").write_bytes(data)
            with self._db:
                self._db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (pid, owner, name, stem, ext, preset, intensity, json.dumps(adj), width, height, now, now))
        return self.get(owner, pid)

    def list(self, owner) -> list[dict]:
        with self._lock:
            return [self._row(r) for r in self._db.execute("SELECT * FROM projects WHERE owner=? ORDER BY updated DESC", (owner,))]

    def get(self, owner, pid) -> dict:
        with self._lock:
            r = self._db.execute("SELECT * FROM projects WHERE id=? AND owner=?", (pid, owner)).fetchone()
        if r is None:
            raise ProjectError("Project not found.", 404)  # same answer whether it exists or belongs to someone else
        return self._row(r)

    def update(self, owner, pid, name=None, preset=None, intensity=None, adjustments=None) -> dict:
        cur = self.get(owner, pid)
        new_name = clean_name(name) if name is not None else cur["name"]
        p, i, adj = clean_settings(preset if preset is not None else cur["preset"],
                                   intensity if intensity is not None else cur["intensity"],
                                   adjustments if adjustments is not None else cur["adjustments"])
        with self._lock, self._db:
            self._db.execute("UPDATE projects SET name=?, preset=?, intensity=?, adjustments=?, updated=? WHERE id=? AND owner=?",
                             (new_name, p, i, json.dumps(adj), time.time(), pid, owner))
        return self.get(owner, pid)

    def delete(self, owner, pid) -> None:
        self.get(owner, pid)
        with self._lock, self._db:
            self._db.execute("DELETE FROM projects WHERE id=? AND owner=?", (pid, owner))
        shutil.rmtree(self.root / pid, ignore_errors=True)

    def original(self, owner, pid) -> tuple[bytes, dict]:
        p = self.get(owner, pid)
        return (self.root / pid / f"original.{p['ext']}").read_bytes(), p

    def purge_expired(self) -> int:
        cutoff = time.time() - config.PROJECT_RETENTION_DAYS * 86400
        with self._lock:
            ids = [r[0] for r in self._db.execute("SELECT id FROM projects WHERE updated < ?", (cutoff,))]
            with self._db:
                self._db.execute("DELETE FROM projects WHERE updated < ?", (cutoff,))
        for pid in ids:
            shutil.rmtree(self.root / pid, ignore_errors=True)
        return len(ids)
