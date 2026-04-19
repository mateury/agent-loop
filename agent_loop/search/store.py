"""SQLite session store with FTS5 full-text search.

Stores every user/assistant turn and provides cross-session recall.
Uses FTS5 shadow table with triggers — zero app-level sync code.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from agent_loop.search.query import has_cjk, sanitize_fts5_query

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    chat_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    title TEXT,
    message_count INTEGER DEFAULT 0,
    model TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


class SessionStore:
    """SQLite-backed conversation store with FTS5 search."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def start_session(
        self,
        session_id: str,
        chat_id: str,
        model: str | None = None,
        title: str | None = None,
    ):
        """Record a new session."""
        now = datetime.now().isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO sessions
                   (id, chat_id, started_at, title, model)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, chat_id, now, title, model),
            )

    def add_message(self, session_id: str, role: str, content: str):
        """Append a message to a session.

        FTS5 index is updated automatically via triggers.
        """
        now = datetime.now().isoformat()
        with self._conn() as c:
            # Ensure session exists (session may have been auto-created by Claude)
            c.execute(
                """INSERT OR IGNORE INTO sessions (id, chat_id, started_at)
                   VALUES (?, '', ?)""",
                (session_id, now),
            )
            c.execute(
                """INSERT INTO messages (session_id, role, content, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (session_id, role, content, now),
            )
            c.execute(
                """UPDATE sessions
                   SET message_count = message_count + 1,
                       ended_at = ?
                   WHERE id = ?""",
                (now, session_id),
            )

    def end_session(self, session_id: str):
        """Mark a session as ended."""
        now = datetime.now().isoformat()
        with self._conn() as c:
            c.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (now, session_id))

    def search(
        self,
        query: str,
        limit: int = 20,
        exclude_session: str | None = None,
    ) -> list[dict]:
        """FTS5 full-text search across all messages.

        Args:
            query: Natural-language query (will be sanitized).
            limit: Max messages to return.
            exclude_session: Skip messages from this session (typically current one).

        Returns:
            List of dicts with session_id, role, content, timestamp, rank.
        """
        results: list[dict] = []
        with self._conn() as c:
            if has_cjk(query):
                # LIKE fallback for CJK (FTS5 default tokenizer splits them)
                sql = """
                    SELECT m.session_id, m.role, m.content, m.timestamp, 0 AS rank
                    FROM messages m
                    WHERE m.content LIKE ?
                """
                params = [f"%{query}%"]
                if exclude_session:
                    sql += " AND m.session_id != ?"
                    params.append(exclude_session)
                sql += " ORDER BY m.timestamp DESC LIMIT ?"
                params.append(limit)
                rows = c.execute(sql, params).fetchall()
            else:
                sanitized = sanitize_fts5_query(query)
                if not sanitized:
                    return []

                sql = """
                    SELECT m.session_id, m.role, m.content, m.timestamp,
                           bm25(messages_fts) AS rank
                    FROM messages_fts
                    JOIN messages m ON m.id = messages_fts.rowid
                    WHERE messages_fts MATCH ?
                """
                params: list = [sanitized]
                if exclude_session:
                    sql += " AND m.session_id != ?"
                    params.append(exclude_session)
                sql += " ORDER BY rank LIMIT ?"
                params.append(limit)
                try:
                    rows = c.execute(sql, params).fetchall()
                except sqlite3.OperationalError as e:
                    log.warning("FTS5 query failed: %s (query=%r)", e, sanitized)
                    return []

            for row in rows:
                results.append(dict(row))
        return results

    def get_session_messages(self, session_id: str) -> list[dict]:
        """Load all messages from a session in order."""
        with self._conn() as c:
            rows = c.execute(
                """SELECT role, content, timestamp FROM messages
                   WHERE session_id = ? ORDER BY id""",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_sessions(self, limit: int = 10, chat_id: str | None = None) -> list[dict]:
        """List recent sessions with metadata."""
        with self._conn() as c:
            if chat_id:
                sql = """SELECT * FROM sessions WHERE chat_id = ?
                         ORDER BY started_at DESC LIMIT ?"""
                params = [chat_id, limit]
            else:
                sql = "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?"
                params = [limit]
            rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def truncate_around_matches(
        self,
        session_id: str,
        query: str,
        window_chars: int = 10_000,
    ) -> str:
        """Load a session transcript, truncated to a window covering the most query-term hits.

        Adopted from Hermes — finds the span with the highest density of query terms.
        """
        messages = self.get_session_messages(session_id)
        if not messages:
            return ""

        transcript = "\n\n".join(
            f"[{m['role']}] {m['content']}" for m in messages
        )

        if len(transcript) <= window_chars:
            return transcript

        # Find term positions
        terms = [t for t in re.split(r"\s+", query.lower()) if len(t) > 2]
        if not terms:
            return transcript[:window_chars]

        lower_tr = transcript.lower()
        positions: list[int] = []
        for term in terms:
            start = 0
            while True:
                idx = lower_tr.find(term, start)
                if idx == -1:
                    break
                positions.append(idx)
                start = idx + len(term)

        if not positions:
            return transcript[:window_chars]

        # Find the window with the most positions (sliding window of size window_chars)
        positions.sort()
        best_start = 0
        best_count = 0
        for start in positions:
            end = start + window_chars
            count = sum(1 for p in positions if start <= p < end)
            if count > best_count:
                best_count = count
                best_start = max(0, start - window_chars // 4)  # Give some context before

        best_end = min(len(transcript), best_start + window_chars)
        prefix = "...\n" if best_start > 0 else ""
        suffix = "\n..." if best_end < len(transcript) else ""
        return prefix + transcript[best_start:best_end] + suffix

    def stats(self) -> dict:
        """Get database statistics."""
        with self._conn() as c:
            sessions = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            messages = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return {
            "sessions": sessions,
            "messages": messages,
            "db_size_mb": self.db_path.stat().st_size / 1024 / 1024 if self.db_path.exists() else 0,
        }
