"""
Persistence layer.

Uses a single `documents` table:

    id           TEXT PRIMARY KEY   -- document_id from the URL, e.g. "meeting-notes"
    content      TEXT               -- full current text of the document
    version      INTEGER            -- monotonically increasing edit counter
    updated_by   TEXT               -- username of whoever made the last edit
    updated_at   TIMESTAMPTZ        -- when that edit landed

We keep the whole document as one text blob rather than per-character ops.
That's what makes Last-Write-Wins (LWW) a reasonable choice here instead of
Operational Transform (OT) -- see README.md for the full reasoning.
"""

import os
from typing import Optional

import asyncpg

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@db:5432/collabnotes"
)

pool: Optional[asyncpg.Pool] = None


async def init_db() -> None:
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


async def close_db() -> None:
    if pool is not None:
        await pool.close()


async def get_document(document_id: str) -> dict:
    """Fetch a document, creating an empty row for it if it doesn't exist yet."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, content, version, updated_by, updated_at "
            "FROM documents WHERE id = $1",
            document_id,
        )
        if row is None:
            await conn.execute(
                """
                INSERT INTO documents (id, content, version)
                VALUES ($1, '', 0)
                ON CONFLICT (id) DO NOTHING
                """,
                document_id,
            )
            row = await conn.fetchrow(
                "SELECT id, content, version, updated_by, updated_at "
                "FROM documents WHERE id = $1",
                document_id,
            )
        return dict(row)


async def save_document(
    document_id: str, content: str, version: int, updated_by: str
) -> dict:
    """Overwrite the document with a new version. This IS the LWW step:
    whichever edit reaches this function last simply wins, no merging."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE documents
            SET content = $2, version = $3, updated_by = $4, updated_at = now()
            WHERE id = $1
            RETURNING id, content, version, updated_by, updated_at
            """,
            document_id,
            content,
            version,
            updated_by,
        )
        return dict(row)
