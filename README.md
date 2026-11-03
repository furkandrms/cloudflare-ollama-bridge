# 🌉 cloudflare-ollama-bridge

Turn Google Colab's **free T4 GPU** into a remote [Ollama](https://ollama.com) server you can call from your own laptop — no GPU required on your end.

[Ollama](https://ollama.com) running on Colab + a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) quick tunnel + any model from the [Ollama library](https://ollama.com/library) (Qwen, Llama, Mistral, Gemma, ...). Includes a local FastAPI demo chat UI (with or without Docker) and a plain terminal CLI, so you can see it working end-to-end in under 10 minutes.

```
┌──────────────┐        cloudflared tunnel        ┌───────────────────┐
│  Colab (GPU) │ ───────────────────────────────▶ │  your machine      │
│  ollama serve│  https://xxxx.trycloudflare.com  │  demo chat UI /    │
│  qwen3:8b    │ ◀─────────────────────────────── │  your own app      │
└──────────────┘                                   └───────────────────┘
```

## Why this exists

Running a decent local LLM (7–8B+ parameters) at usable speed needs a GPU most people don't have. Colab gives everyone a free T4 — but it's a notebook, not a server you can hit from outside. This repo pulls Ollama up inside Colab and punches a temporary public hole to it with Cloudflare's free "quick tunnel," so you get a GPU-backed Ollama endpoint reachable from anywhere, for $0.

Useful for:
- Building/testing an LLM agent without owning a GPU (students, class projects, side projects)
- Benchmarking a local model (Qwen, Llama, Mistral) against an API model (Claude, GPT) without renting cloud GPU time
- Quick weekend demos

Not meant for: a production service with real users, or anything handling sensitive data (see [Limitations & security](#limitations--security)).

## Quickstart

### Step 1 — start the model server on Colab

1. Open [`notebooks/colab_ollama_tunnel.ipynb`](notebooks/colab_ollama_tunnel.ipynb) in Google Colab (or click the badge below).
2. `Runtime → Change runtime type → T4 GPU`.
3. Set `MODEL_NAME` in the second cell to any [Ollama model](https://ollama.com/library) tag (defaults to `qwen3:8b`).
4. Run all cells in order, top to bottom. The tunnel cell prints a public URL like:
   ```
   https://barn-watching-established-outlined.trycloudflare.com
   ```
5. *(Optional but recommended for anything longer than a quick test)* Run the last code cell too — it starts a background watchdog that keeps the model warm and auto-restarts Ollama/the tunnel if either crashes. See [Keep-alive watchdog](#keep-alive-watchdog).

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/furkandrms/cloudflare-ollama-bridge/blob/main/notebooks/colab_ollama_tunnel.ipynb)

### Step 2 — clone the repo and configure it

```bash
git clone https://github.com/furkandrms/cloudflare-ollama-bridge.git
cd cloudflare-ollama-bridge
cp .env.example .env
```

Edit `.env` and paste in the tunnel URL from Step 1:

```ini
MODEL_SERVER_URL=https://barn-watching-established-outlined.trycloudflare.com
MODEL_NAME=qwen3:8b
```

### Step 3 — run the local demo

Pick one:

**With Docker (recommended — no local Python setup needed):**

```bash
docker compose up --build
```

**Without Docker:**

```bash
python -m venv .venv && source .venv/bin/activate   # or use uv/conda
pip install -r requirements.txt
uvicorn demo.app:app --reload --port 8000
```

Either way, open **http://localhost:8000** — a small chat UI appears. Type a message and it streams back a response generated on Colab's GPU. You can also override the tunnel URL and model name directly in the page (both are restricted server-side to Cloudflare tunnel hosts, see [Limitations & security](#limitations--security)).

**Or skip the web UI entirely** and use the terminal client:

```bash
pip install -r requirements.txt   # if you haven't already
python demo/cli.py                    # interactive chat
python demo/cli.py "are you working?" # one-shot prompt, prints and exits
```

### Step 4 — use it in your own code instead

```python
import os, requests
from dotenv import load_dotenv

load_dotenv()
server_url = os.environ["MODEL_SERVER_URL"]
model = os.environ.get("MODEL_NAME", "qwen3:8b")

response = requests.post(
    f"{server_url}/api/generate",
    json={"model": model, "prompt": "hello, are you working?", "stream": False},
    timeout=60,
)
print(response.json()["response"])
```

Or with LangChain, completely transparently:

```python
from langchain_ollama import ChatOllama

llm = ChatOllama(base_url=server_url, model=model, temperature=0)
```

## Keep-alive watchdog

Left alone, this setup degrades in three specific ways:

| Problem | Cause |
|---|---|
| Colab disconnects after ~90 min idle | Free-tier idle timeout |
| First reply after a pause is slow | Ollama unloads the model from GPU memory after ~5 min unused |
| Requests start hanging / `Error 524` | `ollama serve`'s `llama-server` child process crashed or got orphaned |

The notebook's optional last cell runs a background thread that, every 60 seconds, pings the model (keeping it warm in GPU memory and counting as runtime activity) and restarts `ollama serve` / `cloudflared` if either has died. It is a **best-effort mitigation**, not a guarantee — it cannot survive you closing the Colab tab, Colab's hard ~12h session cap, or the platform reclaiming the GPU.

## Limitations & security

This is a free, fast way to get a GPU endpoint — it is **not** production infrastructure.

| Limitation | Detail |
|---|---|
| **Tunnel URL is temporary** | Cloudflare's free quick tunnel hands out a new random URL every time it starts. A stable URL needs a free Cloudflare account + a *named* tunnel. |
| **~120s fixed request timeout** | The quick tunnel cuts off any single HTTP response past ~120s. Long generations (large models, "thinking" modes) can hit this. |
| **Colab session can drop** | Closing the tab, long idle time, or hitting Colab's free quota stops the server — you'll need to rerun the cells and get a new URL. |
| **`OLLAMA_ORIGINS=*` on the Colab side** | Anyone who has the tunnel URL can call your model. Fine for a demo with no sensitive data behind it, not fine for anything else — don't put secrets or private data through this setup. |

**On the demo app's own security:** the chat UI lets you type in a server URL and model name, and the backend makes a request to whatever you typed. Taken at face value, that's a textbook [SSRF](https://owasp.org/www-community/attacks/Server_Side_Request_Forgery) shape — a caller could otherwise point the server at an internal service or a cloud metadata endpoint. `demo/app.py` closes that off: it only allows `*.trycloudflare.com` hosts, `localhost`, or `127.0.0.1`, over `http`/`https`, and validates the model name against a safe character set — everything else is rejected before any outbound request is made. The demo also binds to `127.0.0.1` only (not `0.0.0.0`) and ships with no authentication, so don't expose it beyond your own machine without adding both.

### Alternatives, if you outgrow this

| Option | When |
|---|---|
| Colab Pro/Pro+ | Longer sessions, stronger GPUs (A100/V100) |
| Your own GPU | Apple Silicon Macs run Ollama well with Metal — no tunnel needed |
| Cloudflare named tunnel | Want a stable URL (needs a free Cloudflare account) |
| ngrok, Pinggy, etc. | Alternative tunnel tools, similar setup |
| RunPod, Lambda, Vast.ai | Serious/sustained load — paid, hourly, but reliable |

## Troubleshooting: real errors you'll hit

These are the actual failures encountered building this, in the order you'll likely see them.

### `zstd` missing during Ollama install

```
ERROR: This version requires zstd for extraction. Please install zstd and try again
```

Colab's base image is minimal and doesn't ship `zstd`, which Ollama's install script needs. Fix — install it first:

```bash
apt-get -qq update && apt-get -qq install -y zstd
curl -fsSL https://ollama.com/install.sh | sh
```

### `403 Forbidden` once the tunnel is up

Ollama only binds `127.0.0.1` by default, and checks the `Host` header on incoming requests as a DNS-rebinding protection — only `localhost`/`127.0.0.1` is allowed. Requests through the tunnel carry `Host: xxxx.trycloudflare.com`, which gets rejected. Fix — relax both:

```python
env["OLLAMA_HOST"] = "0.0.0.0:11434"
env["OLLAMA_ORIGINS"] = "*"
```

`OLLAMA_ORIGINS=*` is not something you'd want in production — fine for a throwaway demo tunnel.

### Orphaned `llama-server` process → `Error 524` timeouts

The sneakiest one. After restarting cells a few times, even a trivial prompt would hang for a full 2 minutes and fail:

```
Error 524: A timeout occurred
The origin web server did not return a complete response within the
120-second Proxy Read Timeout window.
```

**Diagnosis:** `nvidia-smi` showed 5+ GB still held by a `llama-server` process, but `ollama ps` listed no running model.

**Cause:** `ollama serve` spawns `llama-server` as a child process. Killing the parent with `pkill -f "ollama serve"` doesn't match the child — it's left orphaned, still holding GPU memory. The next `ollama serve` you start then can't properly take over and requests hang indefinitely until Cloudflare's fixed ~120s tunnel timeout kills them with a 524.

**Fix:** kill both explicitly before restarting:

```python
subprocess.run(["pkill", "-f", "ollama serve"])
subprocess.run(["pkill", "-f", "llama-server"])
```

Or, cleanest: `Runtime → Restart session` in Colab, which clears every orphaned process. The notebook's watchdog cell (see above) now does this automatically if either process dies mid-session.

## Repo layout

```
notebooks/colab_ollama_tunnel.ipynb   # run this on Colab — starts Ollama, the tunnel, and the watchdog
demo/app.py                           # FastAPI server for the local demo chat UI
demo/cli.py                           # plain terminal client, no web UI needed
demo/templates/, demo/static/         # demo UI assets
Dockerfile, docker-compose.yml        # containerized way to run the demo
.env.example                          # MODEL_SERVER_URL / MODEL_NAME
requirements.txt
```

## License

[MIT](LICENSE)
