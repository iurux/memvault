# memvault

Save the AI conversations you actually care about into a **local SQLite vault**, then search them by keyword or meaning. Your data never leaves your machine.

- 🔌 **MCP server**: say "save this" in Claude Desktop (or any MCP client) and it lands in your vault; ask "what did we figure out about X?" and it searches it
- 📥 **Importers** for official Claude and ChatGPT `conversations.json` exports
- 🔎 **Hybrid search**: SQLite FTS5 (trigram, works for Chinese/Japanese) + local embeddings, merged with reciprocal rank fusion
- 💬 **Local chat** against Ollama (or any OpenAI-compatible endpoint) with retrieval from the vault
- 🪶 One file database, three dependencies, no server to run

```
┌──────────────┐   MCP (stdio)   ┌──────────────────────────────────┐
│Claude Desktop│ ──────────────▶ │ memvault                         │
└──────────────┘                 │  save / search / get / list      │
┌──────────────┐                 │                                  │
│ memvault chat│ ──────────────▶ │  SQLite: conversations, messages │
│  (Ollama)    │                 │          chunks + FTS5 + vectors │
└──────────────┘                 └──────────────┬───────────────────┘
  exports ──▶ memvault import                   │ embeddings (optional)
                                                ▼
                                          Ollama /api/embed
```

## Install

```bash
git clone https://github.com/<you>/memvault && cd memvault
pip install -e .

# optional, for semantic search and local chat
ollama pull nomic-embed-text
ollama pull qwen3:8b
```

Without Ollama everything still works with keyword search only.

## Use it from Claude Desktop

Add this to `claude_desktop_config.json` (see [`examples/`](examples/claude_desktop_config.json)) and restart:

```json
{
  "mcpServers": {
    "memvault": { "command": "memvault", "args": ["serve"] }
  }
}
```

Tools exposed: `save_conversation`, `save_note`, `search_memory`, `get_conversation`, `list_conversations`.

Then just talk: *"save this conversation to memvault, tag it opt"* or *"search my vault for the Spokane biometrics plan"*.

## Web UI

`memvault ui` starts a local REST API on `http://127.0.0.1:8765` (localhost only, never exposed to the network).

```bash
memvault ui                                   # API only; point your frontend at it
memvault ui --static ../memvault-ui/dist      # also serve a built frontend at http://127.0.0.1:8765
```

| method | path | |
|---|---|---|
| GET | `/api/health` | status and embedding model |
| GET | `/api/conversations?limit=&tag=&source=` | list with snippets |
| GET | `/api/conversations/{id}` | full conversation |
| PATCH | `/api/conversations/{id}` | `{title?, tags?}` |
| DELETE | `/api/conversations/{id}` | |
| GET | `/api/search?q=&k=` | hybrid search |
| GET | `/api/tags` | `[{tag, count}]` |
| POST | `/api/notes` | `{title, content, tags}` |

CORS allows `localhost:5173`/`8080` (Vite dev servers) and Lovable preview domains. Add others with `--origin https://example.com` or `MEMVAULT_CORS_ORIGINS`.

## CLI

```bash
memvault import ~/Downloads/conversations.json --tag archive   # Claude or ChatGPT export
memvault search "biometrics reschedule"
memvault list --tag opt
memvault show <id>
memvault chat                   # local model + retrieval; /save inside to keep the session
memvault reembed                # after switching embedding models
```

## Configuration

| env var | default | |
|---|---|---|
| `MEMVAULT_DB` | `~/.memvault/vault.db` | database path |
| `MEMVAULT_EMBEDDER` | `ollama` | `ollama` or `none` |
| `MEMVAULT_EMBED_MODEL` | `nomic-embed-text` | any Ollama embedding model |
| `OLLAMA_HOST` | `http://localhost:11434` | |
| `MEMVAULT_CHAT_URL` | `http://localhost:11434/v1` | any OpenAI-compatible endpoint |
| `MEMVAULT_CHAT_MODEL` | `qwen3:8b` | |
| `MEMVAULT_CHAT_KEY` | | API key if the endpoint needs one |

## Schema

```sql
conversations(id, title, source, tags, created_at, saved_at)
messages(conversation_id, position, role, content, created_at)
chunks(conversation_id, text, embedding BLOB, model)   -- + chunks_fts (FTS5 trigram)
```

It's plain SQLite, so you can query it directly: `sqlite3 ~/.memvault/vault.db`.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Roadmap

- [ ] `sqlite-vec` index for large vaults (current brute-force cosine is fine to ~100k chunks)
- [x] Local REST API for a web UI
- [ ] Web UI (browse, tag, edit)
- [ ] Auto-summaries and topic clustering
- [ ] Encrypted vault option

## License

MIT
