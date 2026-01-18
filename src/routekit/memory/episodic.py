"""Episodic memory with SQLite backend."""

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from routekit.core.memory import Memory


class EpisodicMemory(Memory):
    """Episodic memory with SQLite-backed persistent store.

    Stores episodes in a SQLite database with:
    - id: Unique episode ID
    - ts: Timestamp
    - content: Episode content (JSON)
    - metadata: Additional metadata (JSON)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialize episodic memory.

        Args:
            db_path: Path to SQLite database file (defaults to .routekit/episodic.db)
        """
        if db_path is None:
            db_path = Path(".routekit") / "episodic.db"
        elif isinstance(db_path, str):
            db_path = Path(db_path)

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode for better concurrent access and file locking on Windows
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ts ON episodes(ts)
                """
            )
            conn.commit()

    async def get(self, key: str) -> Any:
        """Get episode by ID.

        Args:
            key: Episode ID

        Returns:
            Episode data or None if not found
        """
        import asyncio

        # SQLite operations are synchronous, but we need async interface
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_sync, key)

    def _get_sync(self, key: str) -> Any:
        """Synchronous get operation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, ts, content, metadata FROM episodes WHERE id = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "ts": row["ts"],
                    "content": json.loads(row["content"]),
                    "metadata": json.loads(row["metadata"]),
                }
        return None

    async def set(self, key: str, value: Any) -> None:
        """Store episode by ID.

        Args:
            key: Episode ID
            value: Episode data (dict with content and optional metadata)
        """
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._set_sync, key, value)

    def _set_sync(self, key: str, value: Any) -> None:
        """Synchronous set operation."""
        if not isinstance(value, dict):
            value = {"content": value}

        content = value.get("content", {})
        metadata = value.get("metadata", {})

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO episodes (id, ts, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (key, time.time(), json.dumps(content), json.dumps(metadata)),
            )
            conn.commit()

    async def append(self, event: dict[str, Any]) -> None:
        """Append an event as a new episode.

        Args:
            event: Event dictionary to append
        """
        import asyncio

        episode_id = str(uuid.uuid4())
        content = event.get("content", event)
        metadata = event.get("metadata", {})

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._set_sync, episode_id, {"content": content, "metadata": metadata}
        )

    async def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Search episodes by content (simple substring search for MVP).

        Args:
            query: Search query
            k: Number of results to return

        Returns:
            List of matching episodes
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query, k)

    def _search_sync(self, query: str, k: int) -> list[dict[str, Any]]:
        """Synchronous search operation."""
        results = []
        query_lower = query.lower()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT id, ts, content, metadata FROM episodes ORDER BY ts DESC")
            for row in cursor:
                content_str = json.dumps(row["content"]).lower()
                if query_lower in content_str:
                    results.append(
                        {
                            "id": row["id"],
                            "ts": row["ts"],
                            "content": json.loads(row["content"]),
                            "metadata": json.loads(row["metadata"]),
                        }
                    )
                    if len(results) >= k:
                        break

        return results

    async def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent episodes.

        Args:
            limit: Maximum number of episodes to return

        Returns:
            List of recent episodes
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_recent_sync, limit)

    def _get_recent_sync(self, limit: int) -> list[dict[str, Any]]:
        """Synchronous get_recent operation."""
        results = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, ts, content, metadata FROM episodes ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
            for row in cursor:
                results.append(
                    {
                        "id": row["id"],
                        "ts": row["ts"],
                        "content": json.loads(row["content"]),
                        "metadata": json.loads(row["metadata"]),
                    }
                )
        return results

    def close(self) -> None:
        """Close any open database connections.

        On Windows, SQLite can hold file locks briefly after connections close.
        This method forces SQLite to release locks by opening and closing a connection.
        """
        import gc
        import sys
        import time

        try:
            # Force garbage collection to ensure any lingering connections are cleaned up
            gc.collect()
            # Open and immediately close a connection to ensure locks are released
            # Use a short timeout to avoid hanging
            with sqlite3.connect(str(self.db_path), timeout=1.0) as conn:
                # Checkpoint WAL to ensure all data is written and locks are released
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except sqlite3.Error:
                    # WAL checkpoint may fail if not in WAL mode, ignore
                    pass
                # Execute a simple query to ensure connection is fully established
                conn.execute("SELECT 1")
                # On Windows, SQLite needs a moment to release file locks
                if sys.platform == "win32":
                    time.sleep(0.05)
        except (sqlite3.Error, OSError, TimeoutError):
            # Ignore errors during cleanup - file may already be closed or locked
            pass
