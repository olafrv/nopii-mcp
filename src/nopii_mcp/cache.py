"""Conversion cache: a SQLite index plus markdown files named by content hash.

    cache/nopii.db              which file has which hash, and each hash's status
    cache/raw/<sha256>.md       Docling output (unredacted, never sent to Claude)
    cache/redacted/<sha256>.md  what Claude receives

Naming by hash means a renamed, moved or duplicated file is converted only once.
Several servers (Claude Desktop, Claude Code) can share one cache: SQLite handles
concurrent access, and the "claim" below lets only one process convert a hash.
"""

import hashlib
import os
import sqlite3
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from . import convert, redact

HEARTBEAT = 30  # seconds between "still converting" updates from the converting process
STALE_AFTER = 120  # seconds without a heartbeat before another process may take over (e.g. after a crash)

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, sha256 TEXT);
CREATE TABLE IF NOT EXISTS documents (sha256 TEXT PRIMARY KEY, status TEXT, error TEXT, updated REAL);
"""


class Cache:
    def __init__(self, cache_dir: Path):
        self.raw = cache_dir / "raw"
        self.redacted = cache_dir / "redacted"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.redacted.mkdir(parents=True, exist_ok=True)
        self.db_path = cache_dir / "nopii.db"
        self._worker = ThreadPoolExecutor(max_workers=1)  # one conversion at a time per process
        self._jobs: dict[str, Future] = {}
        self._lock = threading.Lock()
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        try:
            with db:  # commits on success, rolls back on error
                yield db
        finally:
            db.close()

    def known_hash(self, path: Path) -> str | None:
        """The file's hash if it was seen before and hasn't changed since (no hashing)."""
        stat = path.stat()
        with self._db() as db:
            row = db.execute(
                "SELECT sha256 FROM files WHERE path = ? AND size = ? AND mtime_ns = ?",
                (str(path), stat.st_size, stat.st_mtime_ns),
            ).fetchone()
        return row[0] if row else None

    def hash_file(self, path: Path) -> str:
        if sha := self.known_hash(path):
            return sha
        stat = path.stat()
        with path.open("rb") as f:
            sha = hashlib.file_digest(f, "sha256").hexdigest()
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?)",
                (str(path), stat.st_size, stat.st_mtime_ns, sha),
            )
        return sha

    def status(self, sha: str) -> tuple[str | None, str | None]:
        """("done" | "converting" | "error" | None, error message)."""
        with self._db() as db:
            row = db.execute("SELECT status, error FROM documents WHERE sha256 = ?", (sha,)).fetchone()
        return row if row else (None, None)

    def read(self, sha: str) -> str:
        return (self.redacted / f"{sha}.md").read_text(encoding="utf-8")

    def start(self, path: Path, sha: str) -> Future | None:
        """Start converting in the background. None if another process is already on it."""
        with self._lock:
            job = self._jobs.get(sha)
            if job and not job.done():
                return job
            if not self._claim(sha):
                return None
            job = self._jobs[sha] = self._worker.submit(self._convert, path, sha)
            return job

    def _claim(self, sha: str) -> bool:
        """Atomically mark the hash as "converting". False if done or taken by someone else."""
        now = time.time()
        with self._db() as db:
            cursor = db.execute(
                """INSERT INTO documents VALUES (?, 'converting', NULL, ?)
                   ON CONFLICT(sha256) DO UPDATE SET status = 'converting', error = NULL, updated = ?
                   WHERE status = 'error' OR (status = 'converting' AND updated < ?)""",
                (sha, now, now, now - STALE_AFTER),
            )
            return cursor.rowcount == 1

    def _convert(self, path: Path, sha: str) -> None:
        stop = threading.Event()
        threading.Thread(target=self._heartbeat, args=(sha, stop), daemon=True).start()
        try:
            raw = self.raw / f"{sha}.md"
            markdown = raw.read_text(encoding="utf-8") if raw.exists() else convert.to_markdown(path)
            _write(raw, markdown)
            _write(self.redacted / f"{sha}.md", redact.redact(markdown))
            self._finish(sha, "done", None)
        except Exception as e:
            self._finish(sha, "error", f"{type(e).__name__}: {e}")
            raise
        finally:
            stop.set()

    def _heartbeat(self, sha: str, stop: threading.Event) -> None:
        while not stop.wait(HEARTBEAT):
            with self._db() as db:
                db.execute(
                    "UPDATE documents SET updated = ? WHERE sha256 = ? AND status = 'converting'",
                    (time.time(), sha),
                )

    def _finish(self, sha: str, status: str, error: str | None) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE documents SET status = ?, error = ?, updated = ? WHERE sha256 = ?",
                (status, error, time.time(), sha),
            )


def _write(path: Path, text: str) -> None:
    """Write via a temp file and rename, so readers never see a half-written file."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)
