"""
Client Memory Store — per-client persistent memory for the pipeline.

Inspired by Hermes Agent's memory architecture:
- Entries are key-value pairs organized by type
- Memory is loaded as a frozen snapshot at pipeline start
- New learnings are written during/after pipeline execution
- Memory improves output quality over time

Storage: SQLite table (not files — we're on Railway with a volume-mounted DB).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Memory types
BRAND_VOICE = "brand_voice"
STYLE_PREFERENCES = "style_preferences"
PAST_CONTENT = "past_content"
LEARNINGS = "learnings"
DESIGN_SYSTEM = "design_system"
ASSET_CATALOG = "asset_catalog"
BUSINESS_INTEL = "business_intel"

VALID_TYPES = {BRAND_VOICE, STYLE_PREFERENCES, PAST_CONTENT, LEARNINGS, DESIGN_SYSTEM, ASSET_CATALOG, BUSINESS_INTEL}


def init_memory_table(conn) -> None:
    """Create the client_memory table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS client_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            memory_type TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(client_id, memory_type, key)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_client_memory_client
        ON client_memory(client_id, memory_type)
    """)
    conn.commit()


class ClientMemoryStore:
    """Per-client memory with SQLite persistence.

    Usage:
        store = ClientMemoryStore(db_connect_fn)
        memory = store.load_snapshot(client_id)  # frozen dict for prompt injection
        store.save(client_id, "learnings", "prefers-short-paragraphs", "Client rejected long paragraphs in March review")
    """

    def __init__(self, connect_fn):
        """connect_fn: callable that returns a sqlite3.Connection (e.g., db._connect)"""
        self._connect = connect_fn

    def load_all(self, client_id: int) -> list[dict]:
        """Load all memory entries for a client."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM client_memory WHERE client_id = ? ORDER BY memory_type, key",
                (client_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def has_entries(self, client_id: int, memory_type: str) -> bool:
        """Check if any entries exist for a client + memory type."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM client_memory WHERE client_id = ? AND memory_type = ?",
                (client_id, memory_type)
            ).fetchone()
            return row[0] > 0

    def load_by_type(self, client_id: int, memory_type: str) -> list[dict]:
        """Load memory entries of a specific type."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM client_memory WHERE client_id = ? AND memory_type = ? ORDER BY key",
                (client_id, memory_type)
            ).fetchall()
            return [dict(r) for r in rows]

    def load_snapshot(self, client_id: int) -> str:
        """Load all memory as a formatted string for system prompt injection.

        This is the 'frozen snapshot' pattern from Hermes — loaded once at pipeline
        start and injected into agent prompts. Not updated mid-pipeline.
        """
        entries = self.load_all(client_id)
        if not entries:
            return ""

        sections = {}
        for entry in entries:
            mtype = entry["memory_type"]
            if mtype not in sections:
                sections[mtype] = []
            sections[mtype].append(f"- **{entry['key']}**: {entry['value']}")

        parts = []
        type_labels = {
            BRAND_VOICE: "Brand Voice & Tone",
            STYLE_PREFERENCES: "Style Preferences",
            PAST_CONTENT: "Previously Generated Content",
            LEARNINGS: "Agent Learnings",
            DESIGN_SYSTEM: "Design System",
            ASSET_CATALOG: "Asset Catalog",
        }
        for mtype, items in sections.items():
            label = type_labels.get(mtype, mtype)
            parts.append(f"### {label}\n" + "\n".join(items))

        return "\n\n".join(parts)

    def save(self, client_id: int, memory_type: str, key: str, value: str) -> None:
        """Save or update a memory entry (upsert)."""
        if memory_type not in VALID_TYPES:
            raise ValueError(f"Invalid memory type: {memory_type}. Must be one of {VALID_TYPES}")

        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO client_memory (client_id, memory_type, key, value, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(client_id, memory_type, key) DO UPDATE SET
                     value = excluded.value,
                     updated_at = excluded.updated_at""",
                (client_id, memory_type, key, value, now, now)
            )
            conn.commit()

    def delete(self, client_id: int, memory_type: str, key: str) -> bool:
        """Delete a specific memory entry."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM client_memory WHERE client_id = ? AND memory_type = ? AND key = ?",
                (client_id, memory_type, key)
            )
            conn.commit()
            return cur.rowcount > 0

    def save_past_content_summary(self, client_id: int, page_type: str, title: str, keyword: str) -> None:
        """Record a summary of generated content (for avoiding repetition and building internal links)."""
        key = f"{page_type}:{keyword}"
        value = json.dumps({"title": title, "keyword": keyword, "page_type": page_type,
                            "generated_at": datetime.now(timezone.utc).isoformat()})
        self.save(client_id, PAST_CONTENT, key, value)

    def save_learning(self, client_id: int, key: str, observation: str) -> None:
        """Record an agent learning about a client."""
        self.save(client_id, LEARNINGS, key, observation)
