"""Importers for official chat exports.

- Claude:  Settings -> Privacy -> Export data  -> conversations.json
- ChatGPT: Settings -> Data controls -> Export -> conversations.json
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from .vault import Conversation, Message


def _ts(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return datetime.fromtimestamp(x, tz=timezone.utc).isoformat(timespec="seconds")
    return str(x)


def detect(data: list) -> str:
    if data and isinstance(data[0], dict):
        if "chat_messages" in data[0]:
            return "claude"
        if "mapping" in data[0]:
            return "chatgpt"
    raise ValueError("unrecognized export format (expected Claude or ChatGPT conversations.json)")


def claude_export(data: list) -> Iterator[Conversation]:
    for c in data:
        msgs = []
        for m in c.get("chat_messages", []):
            text = m.get("text") or "\n".join(
                p.get("text", "") for p in m.get("content", []) if p.get("type") == "text"
            )
            if text.strip():
                role = "user" if m.get("sender") == "human" else "assistant"
                msgs.append(Message(role, text, _ts(m.get("created_at"))))
        if msgs:
            yield Conversation(
                messages=msgs,
                title=c.get("name") or "",
                source="claude",
                tags=list(c.get("tags") or []),
                id=f"claude-{c['uuid']}",
                created_at=_ts(c.get("created_at")) or msgs[0].created_at or "",
            )


def chatgpt_export(data: list) -> Iterator[Conversation]:
    for c in data:
        mapping = c.get("mapping", {})
        # walk from the current leaf back to the root to get the visible branch
        node_id, chain = c.get("current_node"), []
        while node_id and node_id in mapping:
            chain.append(mapping[node_id])
            node_id = mapping[node_id].get("parent")
        msgs = []
        for node in reversed(chain):
            m = node.get("message") or {}
            role = (m.get("author") or {}).get("role")
            parts = (m.get("content") or {}).get("parts") or []
            text = "\n".join(p for p in parts if isinstance(p, str))
            if role in ("user", "assistant") and text.strip():
                msgs.append(Message(role, text, _ts(m.get("create_time"))))
        if msgs:
            cid = c.get("conversation_id") or c.get("id") or c.get("title", "")
            yield Conversation(
                messages=msgs,
                title=c.get("title") or "",
                source="chatgpt",
                id=f"chatgpt-{cid}",
                created_at=_ts(c.get("create_time")) or "",
            )


def load(path: str | Path) -> Iterator[Conversation]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    kind = detect(data)
    return claude_export(data) if kind == "claude" else chatgpt_export(data)
