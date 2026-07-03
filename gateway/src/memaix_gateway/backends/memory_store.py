# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite-backed memory store with git history for memaix vaults.

Active state lives in {vault}/.memaix.db (notes + FTS5).
History lives in a git repo at the vault root.
Git commits are run synchronously inside write_lock so the returned
snapshot-id is always a real commit hash usable with revert().

TODO(perf): batch async git commits via a queue.Queue + background thread
      once benchmarks show write latency is a problem.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path


class MemoryStore:
    """Per-vault note store.  One instance per resolved vault path (singleton)."""

    _instances: dict[Path, "MemoryStore"] = {}
    _class_lock = threading.Lock()

    def __init__(self, vault: Path) -> None:
        self.vault = vault.resolve()
        self.db_path = self.vault / ".memaix.db"
        self.memory_dir = self.vault / "memory"
        self.write_lock = threading.RLock()
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._conn = self._open_db()
        self._ensure_git()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def for_vault(cls, vault: Path) -> "MemoryStore":
        key = vault.resolve()
        with cls._class_lock:
            if key not in cls._instances:
                cls._instances[key] = cls(key)
            return cls._instances[key]

    @classmethod
    def _clear_instances(cls) -> None:
        """For testing only — reset singleton registry."""
        with cls._class_lock:
            cls._instances.clear()

    # ------------------------------------------------------------------
    # DB setup
    # ------------------------------------------------------------------

    def _open_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY,
                path       TEXT UNIQUE NOT NULL,
                content    TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                path, content, tokenize='porter unicode61'
            );
            """
        )
        conn.commit()
        return conn

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _git_env(self) -> dict:
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "memaix"
        env["GIT_AUTHOR_EMAIL"] = "memaix@localhost"
        env["GIT_COMMITTER_NAME"] = "memaix"
        env["GIT_COMMITTER_EMAIL"] = "memaix@localhost"
        return env

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            cwd=str(self.vault),
            env=self._git_env(),
            capture_output=True,
            text=True,
        )

    def _ensure_git(self) -> None:
        if (self.vault / ".git").exists():
            return
        self._run(["git", "init"])
        gi = self.vault / ".gitignore"
        if not gi.exists():
            gi.write_text(".memaix.db\n")
        elif ".memaix.db" not in gi.read_text():
            with gi.open("a") as fh:
                fh.write("\n.memaix.db\n")
        self._run(["git", "add", ".gitignore"])
        self._run(["git", "commit", "-m", "chore: init memaix vault"])

    def _current_hash(self) -> str:
        r = self._run(["git", "log", "-1", "--format=%H"])
        return r.stdout.strip()

    def _git_commit(self, paths: list[str], message: str) -> str:
        for p in paths:
            self._run(["git", "add", "--", p])
        self._run(["git", "commit", "-m", message])
        return self._current_hash()

    # flush() is a no-op here (operations are synchronous).
    # Kept for API compatibility with any future async variant.
    def flush(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def read(self, path: str) -> str | None:
        row = self._conn.execute(
            "SELECT content FROM notes WHERE path = ?", (path,)
        ).fetchone()
        return row["content"] if row else None

    def list_all(self) -> list[str]:
        rows = self._conn.execute("SELECT path FROM notes ORDER BY path").fetchall()
        return [r["path"] for r in rows]

    def get_updated_at(self, path: str) -> str | None:
        row = self._conn.execute("SELECT updated_at FROM notes WHERE path = ?", (path,)).fetchone()
        return row["updated_at"] if row else None

    def search(self, query: str) -> list[dict]:
        """FTS5 full-text search.  Returns [{path, snippet}]."""
        try:
            rows = self._conn.execute(
                "SELECT path, snippet(notes_fts, 1, '', '', '...', 15) AS snip "
                "FROM notes_fts WHERE notes_fts MATCH ?",
                (query,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"path": r["path"], "snippet": r["snip"]} for r in rows]

    def history(self, path: str | None = None, limit: int = 20) -> list[dict]:
        """Git log.  Returns [{hash, author, date, message}] newest-first."""
        fmt = "--format=%H\x1f%an\x1f%ai\x1f%s"
        if path:
            rel = str(Path("memory") / path)
            r = self._run(["git", "log", f"-{limit}", fmt, "--", rel])
        else:
            r = self._run(["git", "log", f"-{limit}", fmt])
        if r.returncode != 0:
            return []
        out: list[dict] = []
        for line in r.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\x1f", 3)
            if len(parts) < 4:
                continue
            out.append(
                {
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                }
            )
        return out

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def write(self, path: str, content: str, author: str) -> str:
        """Write note to disk + SQLite + git.  Returns git commit hash."""
        now = datetime.now(timezone.utc).isoformat()
        with self.write_lock:
            target = self.memory_dir / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            self._conn.execute(
                "INSERT INTO notes (path, content, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(path) DO UPDATE SET"
                " content=excluded.content, updated_at=excluded.updated_at",
                (path, content, now),
            )
            # Keep standalone FTS in sync
            self._conn.execute("DELETE FROM notes_fts WHERE path = ?", (path,))
            self._conn.execute(
                "INSERT INTO notes_fts(path, content) VALUES (?, ?)", (path, content)
            )
            self._conn.commit()
            rel = str(Path("memory") / path)
            return self._git_commit([rel], f"memaix: write {path} by {author}")

    def append(self, path: str, text: str, author: str) -> str:
        """Append text to note (creating if absent).  Returns git commit hash."""
        existing = self.read(path) or ""
        sep = "\n" if existing and not existing.endswith("\n") else ""
        return self.write(path, existing + sep + text, author)

    def revert(self, commit: str) -> str:
        """Create a new commit that undoes *commit*.  Returns new commit hash."""
        # Only accept a plain git object hash. This blocks argument injection
        # (a value like "-x" being parsed as a git flag) and stray refspecs.
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit):
            raise ValueError(f"invalid commit hash: {commit!r}")
        with self.write_lock:
            r = self._run(["git", "revert", "--no-edit", commit])
            if r.returncode != 0:
                raise RuntimeError(f"git revert failed: {r.stderr.strip()}")
            return self._current_hash()
