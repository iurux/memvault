"""Local REST API for the web UI. Run with `memvault ui`."""

from __future__ import annotations

import inspect
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .vault import Conversation, Message, Vault

DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
]
# Lovable previews and deployments
DEFAULT_ORIGIN_REGEX = r"https://([a-z0-9-]+\.)*(lovable\.app|lovable\.dev|lovableproject\.com)"


def _tags(raw: str) -> list[str]:
    return [t for t in raw.split(",") if t]


def _summary(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "source": row["source"],
        "tags": _tags(row["tags"]),
        "created_at": row["created_at"],
        "snippet": (row["snippet"] or "").strip(),
    }


def _int(value: str | None, default: int, lo: int = 1, hi: int = 1000) -> int:
    try:
        return max(lo, min(hi, int(value))) if value is not None else default
    except ValueError:
        return default


def _err(status: int, msg: str) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


def create_app(
    vault: Vault,
    static_dir: str | Path | None = None,
    allow_origins: list[str] | None = None,
) -> Starlette:
    async def health(request: Request):
        return JSONResponse({"ok": True, "embedder": vault.embedder.model if vault.embedder else None})

    async def list_conversations(request: Request):
        q = request.query_params
        rows = vault.list(limit=_int(q.get("limit"), 200, hi=5000), tag=q.get("tag"), source=q.get("source"))
        return JSONResponse([_summary(r) for r in rows])

    async def get_conversation(request: Request):
        c = vault.get(request.path_params["id"])
        if not c:
            return _err(404, "not found")
        return JSONResponse(
            {
                "id": c.id,
                "title": c.title,
                "source": c.source,
                "tags": c.tags,
                "created_at": c.created_at,
                "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at} for m in c.messages],
            }
        )

    async def patch_conversation(request: Request):
        try:
            body = await request.json()
        except ValueError:
            return _err(400, "invalid JSON")
        title, tags = body.get("title"), body.get("tags")
        if title is not None and not isinstance(title, str):
            return _err(400, "title must be a string")
        if tags is not None and not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
            return _err(400, "tags must be a list of strings")
        if not vault.update(request.path_params["id"], title=title, tags=tags):
            return _err(404, "not found")
        return await get_conversation(request)

    async def delete_conversation(request: Request):
        if not vault.delete(request.path_params["id"]):
            return _err(404, "not found")
        return Response(status_code=204)

    async def search(request: Request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return JSONResponse([])
        hits = vault.search(q, k=_int(request.query_params.get("k"), 20, hi=100))
        return JSONResponse(
            [
                {"conversation_id": h.conversation_id, "title": h.title, "snippet": h.snippet, "score": h.score}
                for h in hits
            ]
        )

    async def tags(request: Request):
        return JSONResponse([{"tag": t, "count": n} for t, n in vault.tag_counts()])

    async def create_note(request: Request):
        try:
            body = await request.json()
        except ValueError:
            return _err(400, "invalid JSON")
        content = body.get("content")
        if not isinstance(content, str) or not content.strip():
            return _err(400, "content is required")
        tags_ = body.get("tags") or []
        if not (isinstance(tags_, list) and all(isinstance(t, str) for t in tags_)):
            return _err(400, "tags must be a list of strings")
        cid = vault.save(
            Conversation(
                messages=[Message("note", content)],
                title=str(body.get("title") or content.strip().splitlines()[0][:60]),
                source="manual",
                tags=tags_,
            )
        )
        return JSONResponse({"id": cid}, status_code=201)

    routes = [
        Route("/api/health", health),
        Route("/api/conversations", list_conversations),
        Route("/api/conversations/{id}", get_conversation, methods=["GET"]),
        Route("/api/conversations/{id}", patch_conversation, methods=["PATCH"]),
        Route("/api/conversations/{id}", delete_conversation, methods=["DELETE"]),
        Route("/api/search", search),
        Route("/api/tags", tags),
        Route("/api/notes", create_note, methods=["POST"]),
    ]

    if static_dir:
        static = Path(static_dir).expanduser().resolve()
        index = static / "index.html"

        async def spa_fallback(request: Request):
            # client-side routes (e.g. /c/123) all serve index.html
            return FileResponse(index)

        routes += [
            Mount("/assets", StaticFiles(directory=static / "assets"), name="assets")
            if (static / "assets").is_dir()
            else Route("/assets/{p:path}", spa_fallback),
            Route("/{path:path}", _static_or_index(static, index)),
        ]

    cors: dict = {
        "allow_origins": allow_origins if allow_origins is not None else DEFAULT_ORIGINS,
        "allow_origin_regex": DEFAULT_ORIGIN_REGEX,
        "allow_methods": ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["*"],
    }
    # lets an https site (e.g. a Lovable preview) call localhost in Chromium; newer Starlette only
    if "allow_private_network" in inspect.signature(CORSMiddleware.__init__).parameters:
        cors["allow_private_network"] = True
    middleware = [Middleware(CORSMiddleware, **cors)]
    return Starlette(routes=routes, middleware=middleware)


def _static_or_index(static: Path, index: Path):
    async def handler(request: Request):
        rel = request.path_params.get("path", "")
        f = (static / rel).resolve()
        if rel and f.is_file() and static in f.parents:
            return FileResponse(f)
        return FileResponse(index)

    return handler


def serve(
    vault: Vault,
    host: str = "127.0.0.1",
    port: int = 8765,
    static_dir: str | None = None,
    origins: list[str] | None = None,
) -> None:
    import uvicorn

    extra = [o for o in os.environ.get("MEMVAULT_CORS_ORIGINS", "").split(",") if o]
    allow = (origins or DEFAULT_ORIGINS) + extra
    app = create_app(vault, static_dir=static_dir, allow_origins=allow)
    where = f"http://{host}:{port}"
    print(f"memvault API on {where}/api" + (f"  ·  UI on {where}" if static_dir else ""))
    uvicorn.run(app, host=host, port=port, log_level="warning")
