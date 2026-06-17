"""
Audit Growth Express — FastAPI backend with SSE streaming.
"""

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

# Add backend dir to path so auditor import works
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auditor import run_audit


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Audit Growth Express",
    description="Audite une URL entreprise et renvoie un audit growth en streaming SSE.",
    version="1.0.0",
    lifespan=lifespan,
)


async def sse_generator(url: str, email: str):
    """Generator that yields SSE-formatted lines from the audit."""
    async for event in run_audit(url, email):
        event_type = event["type"]
        data = event["data"]

        if event_type == "progress":
            yield f"event: progress\ndata: {data}\n\n"
        elif event_type == "result":
            yield f"event: result\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        elif event_type == "error":
            yield f"event: error\ndata: {data}\n\n"


@app.get("/api/audit")
async def api_audit(
    request: Request,
    url: str = Query(..., description="URL ou nom de l'entreprise"),
    email: str = Query("", description="Email optionnel du recruteur"),
):
    """
    GET /api/audit?url=spotify.com&email=recruiter@example.com

    Returns SSE stream with events: progress, result, error.
    """
    return StreamingResponse(
        sse_generator(url, email),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Serve static frontend ──────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str, request: Request):
    """Serve index.html for any non-API path (SPA-style catch-all)."""
    file_path = REPO_ROOT / full_path
    if file_path.is_file() and file_path.suffix in {".html", ".css", ".js", ".png", ".jpg", ".svg", ".ico", ".json", ".webmanifest"}:
        return FileResponse(str(file_path))
    # Default to index.html
    index = REPO_ROOT / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"error": "not found"}


if __name__ == "__main__":
    import uvicorn
    # Load .env if present
    _dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_dotenv_path):
        with open(_dotenv_path) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line.startswith("#") or "=" not in _line:
                    continue
                _k, _v = _line.split("=", 1)
                _k = _k.strip()
                _v = _v.strip()
                if _k == "PORT" and _v:
                    os.environ.setdefault("PORT", _v)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)