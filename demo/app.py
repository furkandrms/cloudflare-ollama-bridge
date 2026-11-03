"""
Local demo chat UI for cloudflare-ollama-bridge.

Talks to an Ollama server running on Colab, exposed through a Cloudflare
quick tunnel URL (see notebooks/colab_ollama_tunnel.ipynb), exactly as if
it were running on localhost.

Run with:
    uvicorn demo.app:app --reload --port 8000
or:
    python demo/app.py
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

load_dotenv()

APP_DIR = os.path.dirname(__file__)

app = FastAPI(title="cloudflare-ollama-bridge demo")
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# The UI lets the viewer type in any "server_url" and the backend makes a
# request to it on their behalf — a classic SSRF shape (the viewer could
# otherwise point this server at an internal service or a cloud metadata
# endpoint). Restrict outbound requests to what this app is actually for:
# a Cloudflare quick-tunnel host, or a local Ollama instance.
ALLOWED_HOST_RE = re.compile(
    r"^([a-z0-9-]+\.trycloudflare\.com|localhost|127\.0\.0\.1)$"
)
MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")


class ChatRequest(BaseModel):
    message: str
    server_url: str | None = None
    model: str | None = None


class InvalidTarget(ValueError):
    pass


def resolve_target(req: ChatRequest) -> tuple[str, str]:
    server_url = (req.server_url or os.environ.get("MODEL_SERVER_URL", "")).strip().rstrip("/")
    model = (req.model or os.environ.get("MODEL_NAME", "qwen3:8b")).strip()

    if not server_url:
        raise InvalidTarget("No MODEL_SERVER_URL set. Paste your Cloudflare tunnel URL above.")

    parsed = urlparse(server_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not ALLOWED_HOST_RE.match(host):
        raise InvalidTarget(
            "Refused: server URL must be a *.trycloudflare.com tunnel, "
            "or localhost/127.0.0.1 — got "
            f"{host or '(none)'!r}."
        )

    if not MODEL_NAME_RE.match(model):
        raise InvalidTarget("Refused: model name contains unexpected characters.")

    return server_url, model


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_server_url": os.environ.get("MODEL_SERVER_URL", ""),
            "default_model": os.environ.get("MODEL_NAME", "qwen3:8b"),
        },
    )


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        server_url, model = resolve_target(req)
    except InvalidTarget as exc:
        return StreamingResponse(iter([f"[error] {exc}".encode()]), media_type="text/plain")

    async def stream_response():
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{server_url}/api/generate",
                    json={"model": model, "prompt": req.message, "stream": True},
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        yield f"[error] {response.status_code}: {body.decode(errors='replace')}".encode()
                        return
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token.encode()
                        if chunk.get("done"):
                            break
        except httpx.ConnectError:
            yield b"[error] Could not reach the model server. Is the Colab notebook still running?"
        except httpx.TimeoutException:
            yield b"[error] Request timed out. The tunnel's quick-tunnel limit is ~120s per request."

    return StreamingResponse(stream_response(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("demo.app:app", host="127.0.0.1", port=8000, reload=True)
