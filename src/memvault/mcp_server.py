"""MCP server: lets Claude Desktop (or any MCP client) save to and search your local vault."""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from . import embed
from .vault import Conversation, Message, Vault

server = MCPServer(
    "memvault",
    instructions=(
        "A local, user-owned memory vault. Only call save_conversation when the user explicitly "
        "asks to save or remember something. Use search_memory when the user refers to past "
        "conversations or saved notes."
    ),
)

_vault: Vault | None = None


def vault() -> Vault:
    global _vault
    if _vault is None:
        _vault = Vault(os.environ.get("MEMVAULT_DB"), embedder=embed.from_env())
    return _vault


@server.tool()
def save_conversation(title: str, messages: list[dict], tags: list[str] | None = None) -> str:
    """Save a conversation (or an excerpt) to the local vault.

    messages: list of {"role": "user"|"assistant", "content": "..."} in order.
    tags: optional labels, e.g. ["work", "recipes"].
    """
    conv = Conversation(
        messages=[Message(m.get("role", "user"), m.get("content", "")) for m in messages],
        title=title,
        source="mcp",
        tags=tags or [],
    )
    cid = vault().save(conv)
    return f"saved {len(conv.messages)} messages as {cid}"


@server.tool()
def save_note(title: str, content: str, tags: list[str] | None = None) -> str:
    """Save a single note or summary to the local vault."""
    cid = vault().save(
        Conversation(messages=[Message("note", content)], title=title, source="mcp", tags=tags or [])
    )
    return f"saved note {cid}"


@server.tool()
def search_memory(query: str, k: int = 5) -> list[dict]:
    """Search saved conversations by keywords and meaning. Returns the best matching snippets."""
    return [
        {"id": h.conversation_id, "title": h.title, "snippet": h.snippet, "score": round(h.score, 4)}
        for h in vault().search(query, k)
    ]


@server.tool()
def get_conversation(conversation_id: str) -> dict:
    """Fetch the full text of a saved conversation by id."""
    c = vault().get(conversation_id)
    if not c:
        return {"error": "not found"}
    return {
        "id": c.id,
        "title": c.title,
        "tags": c.tags,
        "created_at": c.created_at,
        "messages": [{"role": m.role, "content": m.content} for m in c.messages],
    }


@server.tool()
def list_conversations(limit: int = 20, tag: str | None = None) -> list[dict]:
    """List recently saved conversations, optionally filtered by tag."""
    return [dict(r) for r in vault().list(limit=limit, tag=tag)]


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
