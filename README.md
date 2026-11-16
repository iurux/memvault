# memvault

Save the AI conversations you care about into a local SQLite database, then browse and search them. Nothing leaves your machine.

- **Save from Claude Desktop** via MCP: "save this to memvault, tag it recipes"
- **Import** your Claude or ChatGPT history exports
- **Search** by keyword or meaning (works with Chinese/Japanese too)
- **Web UI** ([memvault-ui](https://github.com/iurux/memvault-ui)) to browse, edit, star, tag, archive and delete

## Install

Requires Python 3.10+ and [Bun](https://bun.sh) (or Node 20+).

```bash
mkdir -p ~/code && cd ~/code

# backend
git clone https://github.com/iurux/memvault.git
pip install -e ./memvault

# frontend
git clone https://github.com/iurux/memvault-ui.git
cd memvault-ui && bun install
```

Optional, for semantic search: install [Ollama](https://ollama.com) and run `ollama pull nomic-embed-text`. Without it, search is keyword only.

## Run

Two processes, in two terminals:

```bash
memvault ui                                        # API on 127.0.0.1:8765
cd ~/code/memvault-ui && bun run dev -- --port 4173   # UI
```

Open http://localhost:4173.

## Use it as an app

1. **Start at login** so you never have to run the commands above: follow [docs/macos-autostart.md](docs/macos-autostart.md) (one copy-paste).
2. **Add it to your Dock** with http://localhost:4173 open:
   - Chrome: ⋮ → Cast, save and share → Install page as app
   - Safari: File → Add to Dock

It opens in its own window, shows up in Spotlight and Launchpad, and always shows your latest local data.

## Connect Claude Desktop

Find the full path with `which memvault`, then add to `claude_desktop_config.json` (Settings → Developer → Edit Config) and restart Claude:

```json
{
  "mcpServers": {
    "memvault": { "command": "/full/path/to/memvault", "args": ["serve"] }
  }
}
```

Now you can say "save this conversation to memvault", "search my vault for …", "add today's update to my groceries note" or "star that note".

## Import history

Export from claude.ai (Settings → Privacy → Export data) or ChatGPT (Settings → Data controls → Export), then:

```bash
memvault import ~/Downloads/conversations.json
```

Running it again later only adds what's new.

## Update

```bash
cd ~/code/memvault && git pull && pip install -e .
cd ~/code/memvault-ui && git pull && bun install
```

- **UI**: reloads by itself, just refresh the window.
- **Backend**: restart it. If you set up autostart: `launchctl kickstart -k gui/$(id -u)/memvault.api`. Otherwise stop `memvault ui` with Ctrl+C and run it again.
- Your database is upgraded automatically; nothing to migrate by hand.

## CLI

```bash
memvault search "sourdough"        memvault list [--tag x] [--archived]
memvault show <id>                 memvault archive <id> [--undo]
memvault star <id> [--undo]       memvault delete <id>
memvault reembed                   # after changing embedding model
```

## Your data

Everything is in `~/.memvault/vault.db` (change with `MEMVAULT_DB`). It's plain SQLite: back it up by copying the file. The API only listens on `127.0.0.1`.

## Development

```bash
pip install -e ".[dev]" && pytest && ruff check .
```

MIT License
