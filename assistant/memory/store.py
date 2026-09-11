from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Tier = Literal["profile", "skill", "episode"]


@dataclass
class MemoryItem:
    id: int
    tier: Tier
    key: str
    value: str
    meta: dict[str, Any]
    created_at: str
    updated_at: str


class MemoryStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            raise RuntimeError(f"memory store unavailable: {e}") from e

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  tier TEXT NOT NULL,
                  key TEXT NOT NULL,
                  value TEXT NOT NULL,
                  meta TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(tier, key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  body TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def write(
        self,
        tier: Tier,
        key: str,
        value: str,
        *,
        confirmed: bool,
        meta: dict[str, Any] | None = None,
    ) -> MemoryItem | None:
        if not confirmed:
            return None
        key = (key or "").strip()
        value = (value or "").strip()
        if not key or not value:
            raise ValueError("empty key/value")
        if len(key) > 200 or len(value) > 10_000:
            raise ValueError("payload too large")
        if tier not in ("profile", "skill", "episode"):
            raise ValueError("invalid tier")
        if tier == "episode":
            return self.append_episode(value, confirmed=confirmed)

        meta = meta or {}
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory (tier, key, value, meta, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(tier, key) DO UPDATE SET
                  value=excluded.value,
                  meta=excluded.meta,
                  updated_at=excluded.updated_at
                """,
                (tier, key, value, json.dumps(meta), now, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM memory WHERE tier=? AND key=?", (tier, key)
            ).fetchone()
        return self._row_to_item(row)

    def append_episode(self, body: str, *, confirmed: bool) -> MemoryItem | None:
        if not confirmed:
            return None
        body = (body or "").strip()
        if not body:
            raise ValueError("empty episode")
        if len(body) > 10_000:
            raise ValueError("payload too large")
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO episodes (body, created_at) VALUES (?, ?)", (body, now)
            )
            conn.commit()
            eid = cur.lastrowid
        return MemoryItem(
            id=int(eid),
            tier="episode",
            key=f"episode:{eid}",
            value=body,
            meta={},
            created_at=now,
            updated_at=now,
        )

    def get(self, tier: Tier, key: str) -> MemoryItem | None:
        if tier == "episode":
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory WHERE tier=? AND key=?", (tier, key)
            ).fetchone()
        return self._row_to_item(row) if row else None

    def list_tier(self, tier: Tier) -> list[MemoryItem]:
        if tier == "episode":
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, body, created_at FROM episodes ORDER BY id ASC"
                ).fetchall()
            return [
                MemoryItem(
                    id=int(r["id"]),
                    tier="episode",
                    key=f"episode:{r['id']}",
                    value=r["body"],
                    meta={},
                    created_at=r["created_at"],
                    updated_at=r["created_at"],
                )
                for r in rows
            ]
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory WHERE tier=? ORDER BY key ASC", (tier,)
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def forget(self, tier: Tier, key: str, *, confirmed: bool) -> bool:
        if not confirmed:
            return False
        if tier == "episode":
            # forget by episode id in key episode:N
            if not key.startswith("episode:"):
                return False
            eid = int(key.split(":", 1)[1])
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM episodes WHERE id=?", (eid,))
                conn.commit()
                return cur.rowcount > 0
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM memory WHERE tier=? AND key=?", (tier, key)
            )
            conn.commit()
            return cur.rowcount > 0

    def recall_text(self, query: str) -> str | None:
        q = query.strip().lower()
        for item in self.list_tier("profile"):
            if q in item.key.lower() or q in item.value.lower() or item.key.lower() in q:
                return item.value
        for item in self.list_tier("skill"):
            if q in item.key.lower() or q in item.value.lower():
                return item.value
        return None

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=int(row["id"]),
            tier=row["tier"],  # type: ignore[arg-type]
            key=row["key"],
            value=row["value"],
            meta=json.loads(row["meta"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
