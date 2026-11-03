"""
Minimal terminal client for cloudflare-ollama-bridge — no web UI, no
FastAPI, just a direct connection check / one-shot or interactive chat
against the Ollama server exposed by the Colab notebook's tunnel.

Usage:
    python demo/cli.py                      # interactive chat
    python demo/cli.py "are you working?"   # one-shot prompt, print and exit

Reads MODEL_SERVER_URL / MODEL_NAME from .env (see .env.example), or
pass --url / --model to override.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv


def generate(server_url: str, model: str, prompt: str, timeout: float = 120) -> str:
    response = requests.post(
        f"{server_url.rstrip('/')}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["response"]


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="one-shot prompt; omit for interactive chat")
    parser.add_argument("--url", default=os.environ.get("MODEL_SERVER_URL", ""), help="tunnel URL (default: $MODEL_SERVER_URL)")
    parser.add_argument("--model", default=os.environ.get("MODEL_NAME", "qwen3:8b"), help="model tag (default: $MODEL_NAME or qwen3:8b)")
    args = parser.parse_args()

    if not args.url:
        print("No server URL set. Pass --url or set MODEL_SERVER_URL in .env.", file=sys.stderr)
        return 1

    if args.prompt:
        try:
            print(generate(args.url, args.model, args.prompt))
        except requests.RequestException as exc:
            print(f"Request failed: {exc}", file=sys.stderr)
            return 1
        return 0

    print(f"Connected to {args.url} (model: {args.model}). Ctrl-C or empty line to quit.\n")
    while True:
        try:
            prompt = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            return 0
        try:
            print(f"{args.model}>", generate(args.url, args.model, prompt), "\n")
        except requests.RequestException as exc:
            print(f"[error] {exc}\n", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
