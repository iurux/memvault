"""MCP server: lets Claude Desktop (or any MCP client) save to and search your local vault."""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from . import embed
from .vault import Conversation, Message, Vault

server = MCPServer(
    "memvault",
    instructions=(
        "A local, user-owned memory vault. Only save, edit, star, archive or delete when the user "
        "explicitly asks. Use search_memory when the user refers to past conversations or saved "
        "notes. To change an existing entry, find its id with search_memory or list_conversations, "
        "read it with get_conversation, then call edit_note or update_conversation. Prefer editing "
        "an existing note over saving a near-duplicate."
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
def edit_note(conversation_id: str, content: str, mode: str = "replace") -> str:
    """Change the text of a saved note or conversation.

    mode="replace": the entry becomes a single note with this content (use for rewriting a note).
    mode="append": add this content as a new note at the end (use for adding an update).
    Title, tags, star and archive state are kept.
    """
    v = vault()
    c = v.get(conversation_id)
    if not c:
        return "not found"
    if mode == "append":
        msgs = c.messages + [Message("note", content)]
    elif mode == "replace":
        msgs = [Message("note", content)]
    else:
        return 'mode must be "replace" or "append"'
    v.set_messages(conversation_id, msgs)
    return f"{'appended to' if mode == 'append' else 'updated'} {conversation_id}"


@server.tool()
def update_conversation(
    conversation_id: str,
    title: str | None = None,
    tags: list[str] | None = None,
    starred: bool | None = None,
    archived: bool | None = None,
) -> str:
    """Change a saved entry's title, tags (replaces the whole list), star or archive state.
    Starred entries are pinned to the top; archived ones are hidden from lists and search."""
    v = vault()
    if not v.update(conversation_id, title=title, tags=tags):
        return "not found"
    if starred is not None:
        v.star(conversation_id, starred)
    if archived is not None:
        v.archive(conversation_id, archived)
    return f"updated {conversation_id}"


@server.tool()
def delete_conversation(conversation_id: str) -> str:
    """Permanently delete a saved entry. Only call after the user has confirmed; prefer archiving."""
    return "deleted" if vault().delete(conversation_id) else "not found"


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
        "archived": c.archived_at is not None,
        "starred": c.starred_at is not None,
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
