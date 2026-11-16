"""Minimal terminal chat against any OpenAI-compatible endpoint (Ollama by default), with RAG from the vault."""

from __future__ import annotations

import os

import httpx

from .vault import Conversation, Message, Vault

HELP = """commands:
  /save [title]   save this conversation to the vault
  /search <q>     search the vault
  /norag          toggle memory retrieval
  /quit           exit"""


def _complete(messages: list[dict], model: str, base_url: str, api_key: str | None) -> str:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    r = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json={"model": model, "messages": messages},
        headers=headers,
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def run(vault: Vault, model: str | None = None, rag: bool = True) -> None:
    model = model or os.environ.get("MEMVAULT_CHAT_MODEL", "qwen3:8b")
    base_url = os.environ.get("MEMVAULT_CHAT_URL", "http://localhost:11434/v1")
    api_key = os.environ.get("MEMVAULT_CHAT_KEY")
    history: list[Message] = []
    print(f"memvault chat · model={model} · rag={'on' if rag else 'off'}\n{HELP}\n")

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line == "/quit":
            return
        if line == "/norag":
            rag = not rag
            print(f"rag={'on' if rag else 'off'}")
            continue
        if line.startswith("/search "):
            for h in vault.search(line[8:]):
                print(f"- [{h.conversation_id}] {h.title}\n  {h.snippet[:200]!r}")
            continue
        if line.startswith("/save"):
            title = line[5:].strip() or (history[0].content[:60] if history else "untitled")
            cid = vault.save(Conversation(messages=history, title=title, source="chat"))
            print(f"saved as {cid}")
            continue

        history.append(Message("user", line))
        system = "You are a helpful local assistant."
        if rag:
            hits = vault.search(line, k=3)
            if hits:
                ctx = "\n\n".join(f"[{h.title}]\n{h.snippet}" for h in hits)
                system += f"\n\nRelevant notes from the user's saved conversations:\n{ctx}"
        msgs = [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.content} for m in history
        ]
        try:
            reply = _complete(msgs, model, base_url, api_key)
        except httpx.HTTPError as e:
            history.pop()
            print(f"[error] {e}")
            continue
        history.append(Message("assistant", reply))
        print(f"\nai> {reply}\n")
