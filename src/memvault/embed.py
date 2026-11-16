"""Embedding backends. Embeddings are optional: without one, search falls back to full-text."""

from __future__ import annotations

import os
from typing import Protocol

import httpx
import numpy as np


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class OllamaEmbedder:
    """Calls a local Ollama server (https://ollama.com). Run `ollama pull nomic-embed-text` first."""

    def __init__(self, model: str = "nomic-embed-text", host: str | None = None, timeout: float = 60.0):
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.timeout = timeout

    def embed(self, texts: list[str]) -> np.ndarray:
        r = httpx.post(
            f"{self.host}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return np.asarray(r.json()["embeddings"], dtype=np.float32)


def from_env() -> Embedder | None:
    """MEMVAULT_EMBEDDER=ollama (default) | none."""
    kind = os.environ.get("MEMVAULT_EMBEDDER", "ollama").lower()
    if kind == "none":
        return None
    model = os.environ.get("MEMVAULT_EMBED_MODEL", "nomic-embed-text")
    emb = OllamaEmbedder(model=model)
    try:
        emb.embed(["ping"])
    except (httpx.HTTPError, KeyError, ValueError):
        return None  # Ollama not running: degrade to keyword search
    return emb
