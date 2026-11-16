"""Core API: save conversations, chunk + embed them, hybrid search."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .db import connect
from .embed import Embedder

CHUNK_CHARS = 1200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Message:
    role: str
    content: str
    created_at: str | None = None


@dataclass
class Conversation:
    messages: list[Message]
    title: str = ""
    source: str = "manual"
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_now)


@dataclass
class Hit:
    conversation_id: str
    title: str
    snippet: str
    score: float


def chunk_messages(messages: list[Message], limit: int = CHUNK_CHARS) -> list[str]:
    """Group consecutive messages into ~limit-char chunks; split very long messages."""
    chunks: list[str] = []
    buf = ""
    for m in messages:
        text = f"{m.role}: {m.content.strip()}"
        pieces = [text[i : i + limit] for i in range(0, len(text), limit)] or [""]
        for piece in pieces:
            if buf and len(buf) + len(piece) + 1 > limit:
                chunks.append(buf)
                buf = ""
            buf = f"{buf}\n{piece}" if buf else piece
    if buf:
        chunks.append(buf)
    return chunks


def _fts_query(q: str) -> str | None:
    # trigram tokenizer needs >=3 chars per term; quote each term to avoid FTS syntax errors
    terms = [t.replace('"', '""') for t in q.split() if len(t) >= 3]
    return " OR ".join(f'"{t}"' for t in terms) or None


class Vault:
    def __init__(self, path: str | Path | None = None, embedder: Embedder | None = None):
        self.conn: sqlite3.Connection = connect(path)
        self.embedder = embedder

    # ---- write -----------------------------------------------------------
    def save(self, conv: Conversation, replace: bool = True) -> str:
        c = self.conn
        exists = c.execute("SELECT 1 FROM conversations WHERE id=?", (conv.id,)).fetchone()
        if exists and not replace:
            return conv.id
        with c:
            c.execute("DELETE FROM conversations WHERE id=?", (conv.id,))
            c.execute(
                "INSERT INTO conversations(id,title,source,tags,created_at,saved_at) VALUES (?,?,?,?,?,?)",
                (conv.id, conv.title, conv.source, ",".join(conv.tags), conv.created_at, _now()),
            )
            c.executemany(
                "INSERT INTO messages(conversation_id,position,role,content,created_at) VALUES (?,?,?,?,?)",
                [(conv.id, i, m.role, m.content, m.created_at) for i, m in enumerate(conv.messages)],
            )
            chunks = chunk_messages(conv.messages)
            if conv.title:
                chunks = [f"title: {conv.title}\n{chunks[0]}" if chunks else f"title: {conv.title}"] + chunks[1:]
            vecs = self._embed(chunks)
            model = self.embedder.model if self.embedder and vecs is not None else None
            c.executemany(
                "INSERT INTO chunks(conversation_id,text,embedding,model) VALUES (?,?,?,?)",
                [
                    (conv.id, t, vecs[i].tobytes() if vecs is not None else None, model)
                    for i, t in enumerate(chunks)
                ],
            )
        return conv.id

    def delete(self, conversation_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
        return cur.rowcount > 0

    def tag(self, conversation_id: str, tags: list[str]) -> None:
        self.update(conversation_id, tags=tags)

    def update(self, conversation_id: str, title: str | None = None, tags: list[str] | None = None) -> bool:
        sets, args = [], []
        if title is not None:
            sets.append("title=?")
            args.append(title)
        if tags is not None:
            sets.append("tags=?")
            args.append(",".join(t.strip() for t in tags if t.strip()))
        if not sets:
            return self.conn.execute("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)).fetchone() is not None
        with self.conn:
            cur = self.conn.execute(f"UPDATE conversations SET {', '.join(sets)} WHERE id=?", (*args, conversation_id))
        return cur.rowcount > 0

    def tag_counts(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for (tags,) in self.conn.execute("SELECT tags FROM conversations"):
            for t in tags.split(","):
                if t:
                    counts[t] = counts.get(t, 0) + 1
        return sorted(counts.items(), key=lambda x: (-x[1], x[0]))

    def _embed(self, texts: list[str]) -> np.ndarray | None:
        if not self.embedder or not texts:
            return None
        v = self.embedder.embed(texts).astype(np.float32)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

    # ---- read ------------------------------------------------------------
    def get(self, conversation_id: str) -> Conversation | None:
        row = self.conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not row:
            return None
        msgs = [
            Message(r["role"], r["content"], r["created_at"])
            for r in self.conn.execute(
                "SELECT role,content,created_at FROM messages WHERE conversation_id=? ORDER BY position",
                (conversation_id,),
            )
        ]
        return Conversation(
            messages=msgs,
            title=row["title"],
            source=row["source"],
            tags=[t for t in row["tags"].split(",") if t],
            id=row["id"],
            created_at=row["created_at"],
        )

    def list(self, limit: int = 50, tag: str | None = None, source: str | None = None) -> list[sqlite3.Row]:
        sql = (
            "SELECT id,title,source,tags,created_at,"
            "(SELECT substr(content,1,200) FROM messages m WHERE m.conversation_id=conversations.id "
            "ORDER BY position LIMIT 1) AS snippet FROM conversations WHERE 1=1"
        )
        args: list = []
        if tag:
            sql += " AND (','||tags||',') LIKE ?"
            args.append(f"%,{tag},%")
        if source:
            sql += " AND source=?"
            args.append(source)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return self.conn.execute(sql, args).fetchall()

    def search(self, query: str, k: int = 5) -> list[Hit]:
        """Hybrid search: BM25 full-text + cosine similarity, merged with reciprocal rank fusion."""
        ranks: dict[int, float] = {}

        fq = _fts_query(query)
        if fq:
            rows = self.conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 50",
                (fq,),
            ).fetchall()
            for r, row in enumerate(rows):
                ranks[row[0]] = ranks.get(row[0], 0) + 1 / (60 + r)

        # trigram FTS can't match 1-2 char terms (common in Chinese/Japanese); use LIKE for those
        for term in [t for t in query.split() if len(t) < 3]:
            rows = self.conn.execute(
                "SELECT id FROM chunks WHERE text LIKE ? ORDER BY id DESC LIMIT 50", (f"%{term}%",)
            ).fetchall()
            for r, row in enumerate(rows):
                ranks[row[0]] = ranks.get(row[0], 0) + 1 / (60 + r)

        if self.embedder:
            rows = self.conn.execute(
                "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL AND model=?",
                (self.embedder.model,),
            ).fetchall()
            if rows:
                q = self._embed([query])[0]
                mat = np.frombuffer(b"".join(r["embedding"] for r in rows), dtype=np.float32).reshape(len(rows), -1)
                sims = mat @ q
                for r, idx in enumerate(np.argsort(-sims)[:50]):
                    cid = rows[idx]["id"]
                    ranks[cid] = ranks.get(cid, 0) + 1 / (60 + r)

        if not ranks:
            return []
        best: dict[str, Hit] = {}
        for chunk_id, score in sorted(ranks.items(), key=lambda x: -x[1]):
            row = self.conn.execute(
                "SELECT c.conversation_id, c.text, v.title FROM chunks c "
                "JOIN conversations v ON v.id=c.conversation_id WHERE c.id=?",
                (chunk_id,),
            ).fetchone()
            if row and row["conversation_id"] not in best:
                best[row["conversation_id"]] = Hit(row["conversation_id"], row["title"], row["text"][:400], score)
            if len(best) >= k:
                break
        return list(best.values())

    def reembed(self) -> int:
        """Recompute embeddings for all chunks with the current embedder."""
        if not self.embedder:
            raise RuntimeError("no embedder configured")
        rows = self.conn.execute("SELECT id, text FROM chunks").fetchall()
        with self.conn:
            for i in range(0, len(rows), 64):
                batch = rows[i : i + 64]
                vecs = self._embed([r["text"] for r in batch])
                self.conn.executemany(
                    "UPDATE chunks SET embedding=?, model=? WHERE id=?",
                    [(vecs[j].tobytes(), self.embedder.model, r["id"]) for j, r in enumerate(batch)],
                )
        return len(rows)

    def close(self) -> None:
        self.conn.close()
