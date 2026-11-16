"""Command line interface: memvault <command>."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import embed, importers
from .vault import Vault


def _vault(args) -> Vault:
    emb = None if args.no_embed else embed.from_env()
    return Vault(args.db or os.environ.get("MEMVAULT_DB"), embedder=emb)


def cmd_import(args) -> None:
    v = _vault(args)
    n = 0
    for conv in importers.load(args.file):
        if args.tag:
            conv.tags = args.tag
        v.save(conv, replace=args.replace)
        n += 1
        if n % 25 == 0:
            print(f"  {n}...", file=sys.stderr)
    print(f"imported {n} conversations" + ("" if v.embedder else " (keyword index only; no embedder)"))


def cmd_search(args) -> None:
    hits = _vault(args).search(args.query, k=args.k)
    if args.json:
        print(json.dumps([h.__dict__ for h in hits], ensure_ascii=False, indent=2))
        return
    for h in hits:
        print(f"[{h.conversation_id}] {h.title}\n  {h.snippet[:240].replace(chr(10), ' ')}\n")
    if not hits:
        print("no results")


def cmd_list(args) -> None:
    mode = "only" if args.archived else ("include" if args.all else "exclude")
    for r in _vault(args).list(limit=args.limit, tag=args.tag, source=args.source, archived=mode):
        flag = " [archived]" if r["archived_at"] else ""
        print(f"{r['created_at'][:10]}  {r['source']:<8} {r['id']:<44} {r['title']}{flag}")


def cmd_show(args) -> None:
    c = _vault(args).get(args.id)
    if not c:
        sys.exit("not found")
    print(f"# {c.title}\n")
    for m in c.messages:
        print(f"**{m.role}**: {m.content}\n")


def cmd_archive(args) -> None:
    v = _vault(args)
    results = [v.archive(i, not args.undo) for i in args.ids]  # apply to every id, no short-circuit
    ok = all(results)
    print(("unarchived" if args.undo else "archived") if ok else "some ids not found")


def cmd_delete(args) -> None:
    print("deleted" if _vault(args).delete(args.id) else "not found")


def cmd_reembed(args) -> None:
    v = _vault(args)
    if not v.embedder:
        sys.exit("no embedder available (is Ollama running? `ollama pull nomic-embed-text`)")
    print(f"re-embedded {v.reembed()} chunks with {v.embedder.model}")


def cmd_serve(args) -> None:
    if args.db:
        os.environ["MEMVAULT_DB"] = args.db
    from .mcp_server import main

    main()


def cmd_ui(args) -> None:
    from .api import serve

    serve(_vault(args), host=args.host, port=args.port, static_dir=args.static, origins=args.origin)


def cmd_chat(args) -> None:
    from .chat import run

    run(_vault(args), model=args.model, rag=not args.no_rag)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="memvault", description="Your conversations, in a local database.")
    p.add_argument("--db", help="path to vault.db (default ~/.memvault/vault.db or $MEMVAULT_DB)")
    p.add_argument("--no-embed", action="store_true", help="skip embeddings, keyword search only")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("import", help="import a Claude or ChatGPT conversations.json export")
    s.add_argument("file")
    s.add_argument("--tag", nargs="*", help="tags to attach to every imported conversation")
    s.add_argument("--replace", action="store_true", help="overwrite conversations already imported")
    s.set_defaults(fn=cmd_import)

    s = sub.add_parser("search", help="hybrid keyword + semantic search")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("list", help="list saved conversations")
    s.add_argument("--limit", type=int, default=30)
    s.add_argument("--tag")
    s.add_argument("--source")
    s.add_argument("--archived", action="store_true", help="show archived only")
    s.add_argument("--all", action="store_true", help="include archived")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("archive", help="archive conversations (hidden from list and search, not deleted)")
    s.add_argument("ids", nargs="+")
    s.add_argument("--undo", action="store_true", help="unarchive instead")
    s.set_defaults(fn=cmd_archive)

    s = sub.add_parser("show", help="print a conversation as markdown")
    s.add_argument("id")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("delete", help="permanently delete a conversation")
    s.add_argument("id")
    s.set_defaults(fn=cmd_delete)

    s = sub.add_parser("reembed", help="recompute embeddings (after switching models)")
    s.set_defaults(fn=cmd_reembed)

    s = sub.add_parser("serve", help="run the MCP server over stdio")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("ui", help="run the local REST API for the web UI")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--static", help="also serve a built frontend (e.g. ../memvault-ui/dist)")
    s.add_argument("--origin", action="append", help="extra allowed CORS origin (repeatable)")
    s.set_defaults(fn=cmd_ui)

    s = sub.add_parser("chat", help="terminal chat with a local model + vault retrieval")
    s.add_argument("--model")
    s.add_argument("--no-rag", action="store_true")
    s.set_defaults(fn=cmd_chat)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
